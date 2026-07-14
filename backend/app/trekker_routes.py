

import csv
import hashlib
import io
import json
import uuid
from datetime import datetime, timezone, date

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from marshmallow import ValidationError

from .extensions import database_extension as db, flask_cache_extension as cache
from .models import (
    PlatformUserAccount,
    TrekkingRouteExpedition,
    ParticipantBookingRecord,
    UserPlatformRole,
    ExpeditionLifecycleStatus,
    BookingLifecycleStatus,
)
from .schemas import (
    TrekkerProfileUpdateRequestSchema,
    NewParticipantBookingRequestSchema,
    BookingCancellationRequestSchema,
    OpenExpeditionFilterQuerySchema,
    PasswordChangeRequestSchema,
)
from .tasks import (
    dispatch_booking_history_csv_export_task,
)

trekker_selfservice_blueprint = Blueprint(
    "trekker_selfservice_blueprint",
    __name__,
    url_prefix="/api/trekker"
)

_profile_update_schema = TrekkerProfileUpdateRequestSchema()
_new_booking_schema = NewParticipantBookingRequestSchema()
_cancellation_schema = BookingCancellationRequestSchema()
_open_expedition_filter_schema = OpenExpeditionFilterQuerySchema()
_password_change_schema = PasswordChangeRequestSchema()

def require_trekker_role(route_handler_function):

    from functools import wraps

    @wraps(route_handler_function)
    def trekker_role_enforcement_wrapper(*args, **kwargs):
        if get_jwt().get("platform_role") != UserPlatformRole.TREKKER.value:
            return jsonify({
                "authorisation_error": "This endpoint is accessible to Trekker accounts only.",
                "error_code": "INSUFFICIENT_ROLE"
            }), 403
        return route_handler_function(*args, **kwargs)
    return trekker_role_enforcement_wrapper

def _fetch_authenticated_trekker_account() -> PlatformUserAccount | None:

    current_user_email = get_jwt_identity()
    return PlatformUserAccount.query.filter_by(
        user_email_address=current_user_email
    ).first()

@trekker_selfservice_blueprint.route("/profile", methods=["GET"])
@jwt_required()
@require_trekker_role
def handle_get_trekker_own_profile():

    trekker_account = _fetch_authenticated_trekker_account()
    if trekker_account is None:
        return jsonify({"error": "Account not found.", "error_code": "ACCOUNT_NOT_FOUND"}), 404

    return jsonify({"trekker_profile": trekker_account.to_safe_public_dict()}), 200

@trekker_selfservice_blueprint.route("/profile", methods=["PATCH"])
@jwt_required()
@require_trekker_role
def handle_update_trekker_own_profile():

    trekker_account = _fetch_authenticated_trekker_account()
    if trekker_account is None:
        return jsonify({"error": "Account not found.", "error_code": "ACCOUNT_NOT_FOUND"}), 404

    try:
        validated_profile_updates = _profile_update_schema.load(
            request.get_json(force=True, silent=True) or {}
        )
    except ValidationError as schema_error:
        return jsonify({"validation_errors": schema_error.messages}), 400

    updatable_profile_fields = [
        "user_full_name",
        "user_contact_phone_number",
        "user_profile_bio_summary",
        "user_emergency_contact_name",
        "user_emergency_contact_phone",
    ]
    for field_name in updatable_profile_fields:
        incoming_field_value = validated_profile_updates.get(field_name)
        if incoming_field_value is not None:
            setattr(trekker_account, field_name, incoming_field_value)

    db.session.commit()

    return jsonify({
        "update_successful": True,
        "updated_profile": trekker_account.to_safe_public_dict()
    }), 200

@trekker_selfservice_blueprint.route("/profile/password", methods=["PUT"])
@jwt_required()
@require_trekker_role
def handle_trekker_password_change():

    trekker_account = _fetch_authenticated_trekker_account()
    if trekker_account is None:
        return jsonify({"error": "Account not found.", "error_code": "ACCOUNT_NOT_FOUND"}), 404

    try:
        validated_password_change = _password_change_schema.load(
            request.get_json(force=True, silent=True) or {}
        )
    except ValidationError as schema_error:
        return jsonify({"validation_errors": schema_error.messages}), 400

    if not trekker_account.verify_submitted_password(validated_password_change["current_password"]):
        return jsonify({
            "error": "Current password is incorrect.",
            "error_code": "INCORRECT_CURRENT_PASSWORD"
        }), 401

    trekker_account.set_hashed_password(validated_password_change["new_password"])
    db.session.commit()

    return jsonify({
        "password_changed": True,
        "message": "Your password has been updated successfully. Please log in again."
    }), 200

@trekker_selfservice_blueprint.route("/expeditions/open", methods=["GET"])
@jwt_required()
@require_trekker_role
def handle_explore_open_expeditions():

    try:
        validated_filter_params = _open_expedition_filter_schema.load(request.args.to_dict())
    except ValidationError as schema_error:
        return jsonify({"validation_errors": schema_error.messages}), 400

    filter_params_canonical_string = json.dumps(validated_filter_params, sort_keys=True, default=str)
    filter_hash_digest = hashlib.md5(filter_params_canonical_string.encode()).hexdigest()
    cache_key_prefix = current_app.config.get("CACHE_KEY_PREFIX_OPEN_TREKS", "trek_platform:open_treks:")
    redis_cache_key_for_this_filter = f"{cache_key_prefix}{filter_hash_digest}"

    cached_expedition_response = cache.get(redis_cache_key_for_this_filter)
    if cached_expedition_response is not None:
        current_app.logger.debug(f"Cache HIT for open treks key: {redis_cache_key_for_this_filter}")
        return jsonify(cached_expedition_response), 200

    current_app.logger.debug(f"Cache MISS for open treks key: {redis_cache_key_for_this_filter}")

    open_expeditions_query = TrekkingRouteExpedition.query.filter_by(
        current_expedition_lifecycle_status=ExpeditionLifecycleStatus.OPEN
    ).filter(
        TrekkingRouteExpedition.available_participant_slots_remaining > 0
    )

    if validated_filter_params.get("difficulty_level_filter"):
        from .models import ExpeditionDifficultyLevel
        open_expeditions_query = open_expeditions_query.filter_by(
            expedition_difficulty_level=ExpeditionDifficultyLevel(
                validated_filter_params["difficulty_level_filter"]
            )
        )

    if validated_filter_params.get("geographical_location_keyword"):
        location_search_pattern = f"%{validated_filter_params['geographical_location_keyword']}%"
        open_expeditions_query = open_expeditions_query.filter(
            TrekkingRouteExpedition.expedition_geographical_location.ilike(location_search_pattern)
        )

    if validated_filter_params.get("minimum_duration_days"):
        open_expeditions_query = open_expeditions_query.filter(
            TrekkingRouteExpedition.expedition_duration_in_days >=
            validated_filter_params["minimum_duration_days"]
        )

    if validated_filter_params.get("maximum_duration_days"):
        open_expeditions_query = open_expeditions_query.filter(
            TrekkingRouteExpedition.expedition_duration_in_days <=
            validated_filter_params["maximum_duration_days"]
        )

    if validated_filter_params.get("maximum_price_inr") is not None:
        open_expeditions_query = open_expeditions_query.filter(
            TrekkingRouteExpedition.expedition_price_per_person_inr <=
            validated_filter_params["maximum_price_inr"]
        )

    page_num = validated_filter_params.get("result_page_number", 1)
    per_page_count = validated_filter_params.get("results_per_page_limit", 12)

    paginated_open_expeditions = open_expeditions_query.order_by(
        TrekkingRouteExpedition.expedition_scheduled_start_date.asc()
    ).paginate(page=page_num, per_page=per_page_count, error_out=False)

    response_payload = {
        "open_expeditions": [e.to_public_summary_dict() for e in paginated_open_expeditions.items],
        "applied_filters": validated_filter_params,
        "pagination": {
            "current_page": paginated_open_expeditions.page,
            "total_pages": paginated_open_expeditions.pages,
            "total_open_expedition_count": paginated_open_expeditions.total,
            "results_per_page": per_page_count,
            "has_next_page": paginated_open_expeditions.has_next,
            "has_previous_page": paginated_open_expeditions.has_prev,
        },
        "cached_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    cache.set(redis_cache_key_for_this_filter, response_payload, timeout=300)

    return jsonify(response_payload), 200

@trekker_selfservice_blueprint.route("/expeditions/<int:expedition_record_id>", methods=["GET"])
@jwt_required()
@require_trekker_role
def handle_get_single_expedition_detail_for_trekker(expedition_record_id: int):

    accessible_statuses = [
        ExpeditionLifecycleStatus.OPEN,
        ExpeditionLifecycleStatus.APPROVED,
        ExpeditionLifecycleStatus.CLOSED,
        ExpeditionLifecycleStatus.COMPLETED,
    ]

    target_expedition = TrekkingRouteExpedition.query.filter(
        TrekkingRouteExpedition.trekking_route_expedition_id == expedition_record_id,
        TrekkingRouteExpedition.current_expedition_lifecycle_status.in_(accessible_statuses)
    ).first()

    if target_expedition is None:
        return jsonify({
            "error": "Expedition not found.",
            "error_code": "EXPEDITION_NOT_FOUND"
        }), 404

    return jsonify({"expedition_detail": target_expedition.to_public_summary_dict()}), 200

@trekker_selfservice_blueprint.route("/bookings", methods=["POST"])
@jwt_required()
@require_trekker_role
def handle_create_new_expedition_booking():

    trekker_account = _fetch_authenticated_trekker_account()
    if trekker_account is None:
        return jsonify({"error": "Account not found.", "error_code": "ACCOUNT_NOT_FOUND"}), 404

    try:
        validated_booking_data = _new_booking_schema.load(
            request.get_json(force=True, silent=True) or {}
        )
    except ValidationError as schema_error:
        return jsonify({"validation_errors": schema_error.messages}), 400

    target_expedition_id = validated_booking_data["booked_expedition_instance_id"]
    participants_count = validated_booking_data.get("number_of_participants_in_booking", 1)

    target_expedition = TrekkingRouteExpedition.query.get(target_expedition_id)
    if target_expedition is None:
        return jsonify({
            "error": f"No expedition found with id={target_expedition_id}.",
            "error_code": "EXPEDITION_NOT_FOUND"
        }), 404

    if target_expedition.current_expedition_lifecycle_status != ExpeditionLifecycleStatus.OPEN:
        return jsonify({
            "error": f"This expedition is not currently open for booking "
                     f"(status: {target_expedition.current_expedition_lifecycle_status.value}).",
            "error_code": "EXPEDITION_NOT_OPEN"
        }), 422

    if target_expedition.available_participant_slots_remaining < participants_count:
        return jsonify({
            "error": (
                f"Insufficient slots available. "
                f"Requested: {participants_count}, "
                f"Available: {target_expedition.available_participant_slots_remaining}."
            ),
            "error_code": "INSUFFICIENT_SLOTS_AVAILABLE"
        }), 409

    existing_booking = ParticipantBookingRecord.query.filter_by(
        booking_owner_trekker_id=trekker_account.user_account_id,
        booked_expedition_instance_id=target_expedition_id,
    ).first()

    if existing_booking is not None:
        if existing_booking.current_booking_lifecycle_status != BookingLifecycleStatus.CANCELLED:
            return jsonify({
                "error": "You already have an active booking for this expedition.",
                "error_code": "DUPLICATE_BOOKING_ATTEMPT",
                "existing_booking_reference": existing_booking.booking_confirmation_reference_code
            }), 409

        target_expedition.available_participant_slots_remaining -= participants_count

        booking_ref_code = (
            f"TRK-{target_expedition_id}-"
            f"{trekker_account.user_account_id}-"
            f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M')}"
        )

        existing_booking.current_booking_lifecycle_status = BookingLifecycleStatus.BOOKED
        existing_booking.booking_confirmation_reference_code = booking_ref_code
        existing_booking.number_of_participants_in_booking = participants_count
        existing_booking.trekker_special_requirements_note = validated_booking_data.get("trekker_special_requirements_note")
        existing_booking.booking_placed_at_utc = datetime.now(timezone.utc)
        existing_booking.booking_last_status_changed_at_utc = datetime.now(timezone.utc)

        new_booking_record = existing_booking
    else:
        target_expedition.available_participant_slots_remaining -= participants_count

        booking_ref_code = (
            f"TRK-{target_expedition_id}-"
            f"{trekker_account.user_account_id}-"
            f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M')}"
        )

        new_booking_record = ParticipantBookingRecord(
            booking_owner_trekker_id=trekker_account.user_account_id,
            booked_expedition_instance_id=target_expedition_id,
            current_booking_lifecycle_status=BookingLifecycleStatus.BOOKED,
            booking_confirmation_reference_code=booking_ref_code,
            number_of_participants_in_booking=participants_count,
            trekker_special_requirements_note=validated_booking_data.get("trekker_special_requirements_note"),
        )
        db.session.add(new_booking_record)

    if target_expedition.available_participant_slots_remaining == 0:
        target_expedition.current_expedition_lifecycle_status = ExpeditionLifecycleStatus.CLOSED
        current_app.logger.info(
            f"Expedition id={target_expedition_id} auto-closed: all slots filled."
        )

    db.session.commit()

    try:
        from .tasks import _send_smtp_email_notification
        email_body = f"""
        <html><body style="font-family: Arial, sans-serif; color: #333;">
        <div style="max-width: 600px; margin: auto; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
            <h2 style="color: #2E7D32;">🏕️ Booking Confirmation — {target_expedition.expedition_route_name}</h2>
            <p>Hello <strong>{trekker_account.user_full_name}</strong>,</p>
            <p>Your booking has been confirmed successfully!</p>
            <table style="width: 100%; border-collapse: collapse; margin: 16px 0;">
                <tr><td style="padding: 8px; background: #f5f5f5;"><strong>Trek Name</strong></td>
                    <td style="padding: 8px;">{target_expedition.expedition_route_name}</td></tr>
                <tr><td style="padding: 8px; background: #f5f5f5;"><strong>Location</strong></td>
                    <td style="padding: 8px;">{target_expedition.expedition_geographical_location}</td></tr>
                <tr><td style="padding: 8px; background: #f5f5f5;"><strong>Start Date</strong></td>
                    <td style="padding: 8px;">{target_expedition.expedition_scheduled_start_date}</td></tr>
                <tr><td style="padding: 8px; background: #f5f5f5;"><strong>Participants</strong></td>
                    <td style="padding: 8px;">{participants_count}</td></tr>
                <tr><td style="padding: 8px; background: #f5f5f5;"><strong>Booking Reference</strong></td>
                    <td style="padding: 8px;"><code>{booking_ref_code}</code></td></tr>
            </table>
            <p>Stay safe and enjoy your adventure! 🏔️</p>
        </div></body></html>
        """
        _send_smtp_email_notification(
            recipient_email_address=trekker_account.user_email_address,
            email_subject_line=f"🎉 Booking Confirmed: {target_expedition.expedition_route_name}",
            email_html_body=email_body
        )
    except Exception as email_err:
        current_app.logger.warning(f"Failed to send booking confirmation email: {email_err}")

    try:
        redis_client = cache.cache._write_client
        prefix = current_app.config.get("CACHE_KEY_PREFIX_OPEN_TREKS", "trek_platform:open_treks:")
        keys = redis_client.keys(f"{prefix}*")
        if keys:
            redis_client.delete(*keys)
    except Exception as cache_err:
        current_app.logger.warning(f"Cache invalidation failed after booking: {cache_err}")

    current_app.logger.info(
        f"Booking confirmed: {booking_ref_code} — "
        f"Trekker id={trekker_account.user_account_id} → "
        f"Expedition id={target_expedition_id}"
    )

    return jsonify({
        "booking_confirmed": True,
        "confirmation_reference_code": booking_ref_code,
        "booking_details": new_booking_record.to_full_detail_dict()
    }), 201

@trekker_selfservice_blueprint.route("/bookings/<int:booking_record_id>/cancel", methods=["PATCH"])
@jwt_required()
@require_trekker_role
def handle_cancel_own_expedition_booking(booking_record_id: int):

    trekker_account = _fetch_authenticated_trekker_account()
    if trekker_account is None:
        return jsonify({"error": "Account not found.", "error_code": "ACCOUNT_NOT_FOUND"}), 404

    target_booking = ParticipantBookingRecord.query.get(booking_record_id)
    if target_booking is None:
        return jsonify({
            "error": f"No booking found with id={booking_record_id}.",
            "error_code": "BOOKING_NOT_FOUND"
        }), 404

    if target_booking.booking_owner_trekker_id != trekker_account.user_account_id:
        return jsonify({
            "error": "You can only cancel your own bookings.",
            "error_code": "BOOKING_OWNERSHIP_MISMATCH"
        }), 403

    if target_booking.current_booking_lifecycle_status != BookingLifecycleStatus.BOOKED:
        return jsonify({
            "error": (
                f"Cannot cancel a booking with status "
                f"'{target_booking.current_booking_lifecycle_status.value}'. "
                "Only BOOKED reservations can be cancelled."
            ),
            "error_code": "BOOKING_NOT_CANCELLABLE"
        }), 422

    try:
        validated_cancellation_data = _cancellation_schema.load(
            request.get_json(force=True, silent=True) or {}
        )
    except ValidationError as schema_error:
        return jsonify({"validation_errors": schema_error.messages}), 400

    target_booking.current_booking_lifecycle_status = BookingLifecycleStatus.CANCELLED
    target_booking.cancellation_reason_description = validated_cancellation_data.get(
        "cancellation_reason_description"
    )

    linked_expedition = target_booking.booked_expedition_instance
    linked_expedition.available_participant_slots_remaining += (
        target_booking.number_of_participants_in_booking
    )

    if (
        linked_expedition.current_expedition_lifecycle_status == ExpeditionLifecycleStatus.CLOSED
        and linked_expedition.available_participant_slots_remaining > 0
    ):
        linked_expedition.current_expedition_lifecycle_status = ExpeditionLifecycleStatus.OPEN
        current_app.logger.info(
            f"Expedition id={linked_expedition.trekking_route_expedition_id} "
            f"auto-reopened after cancellation freed a slot."
        )

    db.session.commit()

    try:
        from .tasks import _send_smtp_email_notification
        email_body = f"""
        <html><body style="font-family: Arial, sans-serif; color: #333;">
        <div style="max-width: 600px; margin: auto; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
            <h2 style="color: #ef5350;">❌ Booking Cancelled — {linked_expedition.expedition_route_name}</h2>
            <p>Hello <strong>{trekker_account.user_full_name}</strong>,</p>
            <p>Your booking for the expedition <strong>{linked_expedition.expedition_route_name}</strong> has been cancelled successfully.</p>
            <table style="width: 100%; border-collapse: collapse; margin: 16px 0;">
                <tr><td style="padding: 8px; background: #f5f5f5;"><strong>Trek Name</strong></td>
                    <td style="padding: 8px;">{linked_expedition.expedition_route_name}</td></tr>
                <tr><td style="padding: 8px; background: #f5f5f5;"><strong>Booking Reference</strong></td>
                    <td style="padding: 8px;"><code>{target_booking.booking_confirmation_reference_code}</code></td></tr>
                <tr><td style="padding: 8px; background: #f5f5f5;"><strong>Cancellation Reason</strong></td>
                    <td style="padding: 8px;">{target_booking.cancellation_reason_description or 'No reason provided'}</td></tr>
            </table>
            <p>Your slot has been restored. We hope to see you on another trail soon! 🏔️</p>
        </div></body></html>
        """
        _send_smtp_email_notification(
            recipient_email_address=trekker_account.user_email_address,
            email_subject_line=f"Booking Cancelled: {linked_expedition.expedition_route_name}",
            email_html_body=email_body
        )
    except Exception as email_err:
        current_app.logger.warning(f"Failed to send booking cancellation email: {email_err}")

    try:
        redis_client = cache.cache._write_client
        prefix = current_app.config.get("CACHE_KEY_PREFIX_OPEN_TREKS", "trek_platform:open_treks:")
        keys = redis_client.keys(f"{prefix}*")
        if keys:
            redis_client.delete(*keys)
    except Exception as cache_err:
        current_app.logger.warning(f"Cache invalidation failed after cancellation: {cache_err}")

    return jsonify({
        "cancellation_confirmed": True,
        "cancelled_booking": target_booking.to_full_detail_dict()
    }), 200

@trekker_selfservice_blueprint.route("/bookings", methods=["GET"])
@jwt_required()
@require_trekker_role
def handle_list_own_booking_history():

    trekker_account = _fetch_authenticated_trekker_account()
    if trekker_account is None:
        return jsonify({"error": "Account not found.", "error_code": "ACCOUNT_NOT_FOUND"}), 404

    status_filter_value = request.args.get("status_filter", None)

    booking_history_query = trekker_account.participant_booking_history

    if status_filter_value:
        try:
            parsed_status = BookingLifecycleStatus(status_filter_value)
            booking_history_query = booking_history_query.filter_by(
                current_booking_lifecycle_status=parsed_status
            )
        except ValueError:
            return jsonify({
                "error": f"'{status_filter_value}' is not a valid booking status.",
                "error_code": "INVALID_STATUS_FILTER"
            }), 400

    all_bookings = booking_history_query.order_by(
        ParticipantBookingRecord.booking_placed_at_utc.desc()
    ).all()

    return jsonify({
        "booking_history": [b.to_full_detail_dict() for b in all_bookings],
        "total_booking_count": len(all_bookings)
    }), 200

@trekker_selfservice_blueprint.route("/bookings/export-csv", methods=["POST"])
@jwt_required()
@require_trekker_role
def handle_trigger_booking_history_csv_export():

    trekker_account = _fetch_authenticated_trekker_account()
    if trekker_account is None:
        return jsonify({"error": "Account not found.", "error_code": "ACCOUNT_NOT_FOUND"}), 404

    dispatched_celery_task = dispatch_booking_history_csv_export_task.delay(
        trekker_account_id=trekker_account.user_account_id,
        trekker_email_address=trekker_account.user_email_address,
        trekker_full_name=trekker_account.user_full_name,
    )

    current_app.logger.info(
        f"CSV export task dispatched for trekker id={trekker_account.user_account_id} "
        f"(Celery task_id={dispatched_celery_task.id})"
    )

    return jsonify({
        "export_task_accepted": True,
        "message": (
            "Your booking history CSV export has been queued. "
            "You will receive an email notification when it is ready."
        ),
        "celery_task_id": dispatched_celery_task.id,
    }), 202
