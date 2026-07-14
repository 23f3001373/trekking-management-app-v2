

from functools import wraps

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
    ExpeditionDifficultyLevel,
    BookingLifecycleStatus,
)
from .schemas import (
    ExpeditionCreateRequestSchema,
    ExpeditionUpdateRequestSchema,
    AdminCreateStaffAccountRequestSchema,
)

admin_operations_blueprint = Blueprint(
    "admin_operations_blueprint",
    __name__,
    url_prefix="/api/admin"
)

_expedition_create_schema = ExpeditionCreateRequestSchema()
_expedition_update_schema = ExpeditionUpdateRequestSchema()
_staff_create_schema = AdminCreateStaffAccountRequestSchema()

def require_admin_role(route_handler_function):

    @wraps(route_handler_function)
    def admin_role_enforcement_wrapper(*args, **kwargs):
        incoming_jwt_claims = get_jwt()
        if incoming_jwt_claims.get("platform_role") != UserPlatformRole.ADMIN.value:
            return jsonify({
                "authorisation_error": "This endpoint is restricted to Admin accounts only.",
                "error_code": "INSUFFICIENT_ROLE"
            }), 403
        return route_handler_function(*args, **kwargs)
    return admin_role_enforcement_wrapper

# check credentials

def _invalidate_open_treks_redis_cache() -> None:

    try:
        cache_key_prefix = current_app.config.get(
            "CACHE_KEY_PREFIX_OPEN_TREKS", "trek_platform:open_treks:"
        )
        cache_type = current_app.config.get("CACHE_TYPE")
        if cache_type == "RedisCache":
            redis_client = getattr(cache.cache, "_write_client", None) or getattr(cache.cache, "_client", None)
            if redis_client:
                matching_cache_keys = redis_client.keys(f"{cache_key_prefix}*")
                if matching_cache_keys:
                    redis_client.delete(*matching_cache_keys)
                    current_app.logger.debug(
                        f"Invalidated {len(matching_cache_keys)} open-treks cache entries from Redis."
                    )
        else:
            cache.clear()
            current_app.logger.debug("Cleared testing/fallback cache.")
    except Exception as cache_invalidation_exception:
        current_app.logger.warning(
            f"Cache invalidation failed (non-fatal): {cache_invalidation_exception}"
        )

@admin_operations_blueprint.route("/dashboard/metrics", methods=["GET"])
@jwt_required()
@require_admin_role
def handle_admin_dashboard_metrics_retrieval():

    total_registered_trekkers = PlatformUserAccount.query.filter_by(
        assigned_platform_role=UserPlatformRole.TREKKER
    ).count()

    total_staff_accounts = PlatformUserAccount.query.filter_by(
        assigned_platform_role=UserPlatformRole.STAFF
    ).count()

    total_blacklisted_accounts = PlatformUserAccount.query.filter_by(
        is_account_blacklisted=True
    ).count()

    total_expeditions = TrekkingRouteExpedition.query.count()

    open_expeditions_count = TrekkingRouteExpedition.query.filter_by(
        current_expedition_lifecycle_status=ExpeditionLifecycleStatus.OPEN
    ).count()

    active_bookings_count = ParticipantBookingRecord.query.filter_by(
        current_booking_lifecycle_status=BookingLifecycleStatus.BOOKED
    ).count()

    easy_count = TrekkingRouteExpedition.query.filter_by(expedition_difficulty_level=ExpeditionDifficultyLevel.EASY).count()
    moderate_count = TrekkingRouteExpedition.query.filter_by(expedition_difficulty_level=ExpeditionDifficultyLevel.MODERATE).count()
    hard_count = TrekkingRouteExpedition.query.filter_by(expedition_difficulty_level=ExpeditionDifficultyLevel.HARD).count()
    difficulty_distribution = {
        "Easy": easy_count,
        "Moderate": moderate_count,
        "Hard": hard_count
    }

    booked_count = ParticipantBookingRecord.query.filter_by(current_booking_lifecycle_status=BookingLifecycleStatus.BOOKED).count()
    cancelled_count = ParticipantBookingRecord.query.filter_by(current_booking_lifecycle_status=BookingLifecycleStatus.CANCELLED).count()
    completed_count = ParticipantBookingRecord.query.filter_by(current_booking_lifecycle_status=BookingLifecycleStatus.COMPLETED).count()
    booking_status_distribution = {
        "Booked": booked_count,
        "Cancelled": cancelled_count,
        "Completed": completed_count
    }

    all_expeditions = TrekkingRouteExpedition.query.all()
    most_popular = []
    for exp in all_expeditions:
        count = ParticipantBookingRecord.query.filter_by(
            booked_expedition_instance_id=exp.trekking_route_expedition_id
        ).filter(
            ParticipantBookingRecord.current_booking_lifecycle_status.in_([
                BookingLifecycleStatus.BOOKED,
                BookingLifecycleStatus.COMPLETED
            ])
        ).count()
        most_popular.append({
            "expedition_route_name": exp.expedition_route_name,
            "booking_count": count
        })
    most_popular.sort(key=lambda x: x["booking_count"], reverse=True)

    return jsonify({
        "admin_dashboard_metrics": {
            "total_registered_trekkers": total_registered_trekkers,
            "total_staff_accounts": total_staff_accounts,
            "total_blacklisted_accounts": total_blacklisted_accounts,
            "total_expeditions_on_platform": total_expeditions,
            "currently_open_expeditions": open_expeditions_count,
            "active_participant_bookings": active_bookings_count,
            "difficulty_distribution": difficulty_distribution,
            "booking_status_distribution": booking_status_distribution
        },
        "difficulty_distribution": difficulty_distribution,
        "booking_status_distribution": booking_status_distribution,
        "most_popular_expeditions": most_popular
    }), 200

@admin_operations_blueprint.route("/expeditions", methods=["GET"])
@jwt_required()
@require_admin_role
def handle_list_all_expeditions_for_admin():

    status_filter_value = request.args.get("status_filter", None)
    page_number = int(request.args.get("page", 1))
    results_per_page = min(int(request.args.get("per_page", 20)), 100)

    expedition_base_query = TrekkingRouteExpedition.query

    if status_filter_value:
        try:
            parsed_status = ExpeditionLifecycleStatus(status_filter_value)
            expedition_base_query = expedition_base_query.filter_by(
                current_expedition_lifecycle_status=parsed_status
            )
        except ValueError:
            return jsonify({
                "error": f"'{status_filter_value}' is not a valid expedition status.",
                "error_code": "INVALID_STATUS_FILTER"
            }), 400

    paginated_expeditions = expedition_base_query.order_by(
        TrekkingRouteExpedition.expedition_record_created_at_utc.desc()
    ).paginate(page=page_number, per_page=results_per_page, error_out=False)

    return jsonify({
        "expeditions": [e.to_public_summary_dict() for e in paginated_expeditions.items],
        "pagination": {
            "current_page": paginated_expeditions.page,
            "total_pages": paginated_expeditions.pages,
            "total_expedition_count": paginated_expeditions.total,
            "results_per_page": results_per_page,
            "has_next_page": paginated_expeditions.has_next,
            "has_previous_page": paginated_expeditions.has_prev,
        }
    }), 200

@admin_operations_blueprint.route("/expeditions", methods=["POST"])
@jwt_required()
@require_admin_role
def handle_create_new_expedition():

    try:
        validated_expedition_data = _expedition_create_schema.load(
            request.get_json(force=True, silent=True) or {}
        )
    except ValidationError as schema_error:
        return jsonify({"validation_errors": schema_error.messages}), 400

    designated_staff_leader_id = validated_expedition_data.get("assigned_staff_leader_id")
    if designated_staff_leader_id is not None:
        designated_staff_account = PlatformUserAccount.query.filter_by(
            user_account_id=designated_staff_leader_id,
            assigned_platform_role=UserPlatformRole.STAFF
        ).first()
        if designated_staff_account is None:
            return jsonify({
                "error": f"No Staff account found with id={designated_staff_leader_id}.",
                "error_code": "STAFF_ACCOUNT_NOT_FOUND"
            }), 422

    slot_capacity = validated_expedition_data["total_participant_slots_capacity"]
    difficulty_enum = ExpeditionDifficultyLevel(validated_expedition_data["expedition_difficulty_level"])

    new_expedition_record = TrekkingRouteExpedition(
        expedition_route_name=validated_expedition_data["expedition_route_name"],
        expedition_geographical_location=validated_expedition_data["expedition_geographical_location"],
        expedition_detailed_description=validated_expedition_data.get("expedition_detailed_description"),
        expedition_difficulty_level=difficulty_enum,
        expedition_duration_in_days=validated_expedition_data["expedition_duration_in_days"],
        expedition_price_per_person_inr=validated_expedition_data.get("expedition_price_per_person_inr", 0.0),
        expedition_scheduled_start_date=validated_expedition_data.get("expedition_scheduled_start_date"),
        expedition_scheduled_end_date=validated_expedition_data.get("expedition_scheduled_end_date"),
        expedition_booking_cutoff_date=validated_expedition_data.get("expedition_booking_cutoff_date"),
        total_participant_slots_capacity=slot_capacity,
        available_participant_slots_remaining=slot_capacity,  # query db
        current_expedition_lifecycle_status=ExpeditionLifecycleStatus.PENDING,
        expedition_cover_image_url=validated_expedition_data.get("expedition_cover_image_url"),
        expedition_meeting_point_address=validated_expedition_data.get("expedition_meeting_point_address"),
        assigned_staff_leader_id=designated_staff_leader_id,
    )

    db.session.add(new_expedition_record)
    db.session.commit()

    _invalidate_open_treks_redis_cache()

    current_app.logger.info(
        f"Admin created new expedition: {new_expedition_record.expedition_route_name!r} "
        f"(id={new_expedition_record.trekking_route_expedition_id})"
    )

    return jsonify({
        "creation_successful": True,
        "created_expedition": new_expedition_record.to_public_summary_dict()
    }), 201

@admin_operations_blueprint.route("/expeditions/<int:expedition_record_id>", methods=["GET"])
@jwt_required()
@require_admin_role
def handle_get_single_expedition_detail(expedition_record_id: int):

    target_expedition = TrekkingRouteExpedition.query.get(expedition_record_id)
    if target_expedition is None:
        return jsonify({
            "error": f"No expedition found with id={expedition_record_id}.",
            "error_code": "EXPEDITION_NOT_FOUND"
        }), 404

    return jsonify({"expedition_detail": target_expedition.to_public_summary_dict()}), 200

@admin_operations_blueprint.route("/expeditions/<int:expedition_record_id>", methods=["PATCH"])
@jwt_required()
@require_admin_role
def handle_update_expedition_record(expedition_record_id: int):

    target_expedition = TrekkingRouteExpedition.query.get(expedition_record_id)
    if target_expedition is None:
        return jsonify({
            "error": f"No expedition found with id={expedition_record_id}.",
            "error_code": "EXPEDITION_NOT_FOUND"
        }), 404

    try:
        validated_update_payload = _expedition_update_schema.load(
            request.get_json(force=True, silent=True) or {}
        )
    except ValidationError as schema_error:
        return jsonify({"validation_errors": schema_error.messages}), 400

    field_mapping_for_update = {
        "expedition_route_name": "expedition_route_name",
        "expedition_geographical_location": "expedition_geographical_location",
        "expedition_detailed_description": "expedition_detailed_description",
        "expedition_duration_in_days": "expedition_duration_in_days",
        "expedition_price_per_person_inr": "expedition_price_per_person_inr",
        "expedition_scheduled_start_date": "expedition_scheduled_start_date",
        "expedition_scheduled_end_date": "expedition_scheduled_end_date",
        "expedition_booking_cutoff_date": "expedition_booking_cutoff_date",
        "expedition_cover_image_url": "expedition_cover_image_url",
        "expedition_meeting_point_address": "expedition_meeting_point_address",
    }

    for payload_key, model_attribute_name in field_mapping_for_update.items():
        incoming_value = validated_update_payload.get(payload_key)
        if incoming_value is not None:
            setattr(target_expedition, model_attribute_name, incoming_value)

    if validated_update_payload.get("expedition_difficulty_level"):
        target_expedition.expedition_difficulty_level = ExpeditionDifficultyLevel(
            validated_update_payload["expedition_difficulty_level"]
        )

    if validated_update_payload.get("current_expedition_lifecycle_status"):
        target_expedition.current_expedition_lifecycle_status = ExpeditionLifecycleStatus(
            validated_update_payload["current_expedition_lifecycle_status"]
        )

    if validated_update_payload.get("total_participant_slots_capacity") is not None:
        new_capacity = validated_update_payload["total_participant_slots_capacity"]
        confirmed_bookings_count = ParticipantBookingRecord.query.filter_by(
            booked_expedition_instance_id=expedition_record_id,
            current_booking_lifecycle_status=BookingLifecycleStatus.BOOKED
        ).count()
        if new_capacity < confirmed_bookings_count:
            return jsonify({
                "error": (
                    f"Cannot reduce capacity to {new_capacity}. "
                    f"There are {confirmed_bookings_count} active bookings."
                ),
                "error_code": "CAPACITY_BELOW_ACTIVE_BOOKINGS"
            }), 409
        slot_difference = new_capacity - target_expedition.total_participant_slots_capacity
        target_expedition.total_participant_slots_capacity = new_capacity
        target_expedition.available_participant_slots_remaining = max(
            0, target_expedition.available_participant_slots_remaining + slot_difference
        )

    if "assigned_staff_leader_id" in validated_update_payload:
        new_staff_id = validated_update_payload["assigned_staff_leader_id"]
        if new_staff_id is not None:
            staff_account_check = PlatformUserAccount.query.filter_by(
                user_account_id=new_staff_id,
                assigned_platform_role=UserPlatformRole.STAFF
            ).first()
            if staff_account_check is None:
                return jsonify({
                    "error": f"No Staff account found with id={new_staff_id}.",
                    "error_code": "STAFF_ACCOUNT_NOT_FOUND"
                }), 422
        target_expedition.assigned_staff_leader_id = new_staff_id

    db.session.commit()
    _invalidate_open_treks_redis_cache()

    return jsonify({
        "update_successful": True,
        "updated_expedition": target_expedition.to_public_summary_dict()
    }), 200

@admin_operations_blueprint.route("/expeditions/<int:expedition_record_id>", methods=["DELETE"])
@jwt_required()
@require_admin_role
def handle_delete_expedition_record(expedition_record_id: int):

    target_expedition = TrekkingRouteExpedition.query.get(expedition_record_id)
    if target_expedition is None:
        return jsonify({
            "error": f"No expedition found with id={expedition_record_id}.",
            "error_code": "EXPEDITION_NOT_FOUND"
        }), 404

    active_booking_count = ParticipantBookingRecord.query.filter_by(
        booked_expedition_instance_id=expedition_record_id,
        current_booking_lifecycle_status=BookingLifecycleStatus.BOOKED
    ).count()

    if active_booking_count > 0:
        return jsonify({
            "error": (
                f"Cannot delete this expedition — {active_booking_count} active bookings exist. "
                "Cancel all bookings first, or set status to CANCELLED."
            ),
            "error_code": "ACTIVE_BOOKINGS_PREVENT_DELETION"
        }), 409

    expedition_name_for_log = target_expedition.expedition_route_name
    db.session.delete(target_expedition)
    db.session.commit()
    _invalidate_open_treks_redis_cache()

    current_app.logger.warning(
        f"Admin deleted expedition: {expedition_name_for_log!r} (id={expedition_record_id})"
    )

    return jsonify({
        "deletion_successful": True,
        "message": f"Expedition '{expedition_name_for_log}' and all its records have been permanently deleted."
    }), 200

@admin_operations_blueprint.route("/users", methods=["GET"])
@jwt_required()
@require_admin_role
def handle_list_all_platform_users():

    role_filter = request.args.get("role_filter", None)
    blacklisted_only = request.args.get("blacklisted_only", "false").lower() == "true"
    search_keyword = request.args.get("search_keyword", None)

    user_query = PlatformUserAccount.query.filter(
        PlatformUserAccount.assigned_platform_role != UserPlatformRole.ADMIN
    )

    if role_filter:
        try:
            user_query = user_query.filter_by(
                assigned_platform_role=UserPlatformRole(role_filter)
            )
        except ValueError:
            return jsonify({"error": f"'{role_filter}' is not a valid role."}), 400

    if blacklisted_only:
        user_query = user_query.filter_by(is_account_blacklisted=True)

    if search_keyword:
        search_pattern = f"%{search_keyword.strip()}%"
        user_query = user_query.filter(
            db.or_(
                PlatformUserAccount.user_full_name.ilike(search_pattern),
                PlatformUserAccount.user_email_address.ilike(search_pattern),
            )
        )

    all_matching_users = user_query.order_by(
        PlatformUserAccount.account_created_at_utc.desc()
    ).all()

    return jsonify({
        "platform_users": [u.to_safe_public_dict() for u in all_matching_users],
        "total_count": len(all_matching_users)
    }), 200

@admin_operations_blueprint.route("/staff", methods=["POST"])
@jwt_required()
@require_admin_role
def handle_create_staff_account():

    try:
        validated_staff_data = _staff_create_schema.load(
            request.get_json(force=True, silent=True) or {}
        )
    except ValidationError as schema_error:
        return jsonify({"validation_errors": schema_error.messages}), 400

    submitted_email = validated_staff_data["user_email_address"].lower().strip()

    if PlatformUserAccount.query.filter_by(user_email_address=submitted_email).first():
        return jsonify({
            "error": "An account with this email already exists.",
            "error_code": "EMAIL_ALREADY_REGISTERED"
        }), 409

    new_staff_account = PlatformUserAccount(
        user_full_name=validated_staff_data["user_full_name"].strip(),
        user_email_address=submitted_email,
        assigned_platform_role=UserPlatformRole.STAFF,
        user_contact_phone_number=validated_staff_data.get("user_contact_phone_number"),
        is_account_active=True,
        is_account_blacklisted=False,
    )
    new_staff_account.set_hashed_password(validated_staff_data["raw_password"])

    db.session.add(new_staff_account)
    db.session.commit()

    try:
        from .tasks import _send_smtp_email_notification
        email_body = f"""
        <html><body style="font-family: Arial, sans-serif; color: #333;">
        <div style="max-width: 600px; margin: auto; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
            <h2 style="color: #2E7D32;">🏕️ Welcome to TrekVista — Staff Account Created</h2>
            <p>Hello <strong>{new_staff_account.user_full_name}</strong>,</p>
            <p>An administrator has created a Trek Guide / Staff account for you on the TrekVista platform.</p>
            <p>You can log in to your dashboard using the following credentials:</p>
            <table style="width: 100%; border-collapse: collapse; margin: 16px 0;">
                <tr><td style="padding: 8px; background: #f5f5f5;"><strong>Login Email</strong></td>
                    <td style="padding: 8px;">{new_staff_account.user_email_address}</td></tr>
                <tr><td style="padding: 8px; background: #f5f5f5;"><strong>Temporary Password</strong></td>
                    <td style="padding: 8px;"><code>{validated_staff_data["raw_password"]}</code></td></tr>
            </table>
            <p>Please log in and update your password from your profile settings as soon as possible. 🏔️</p>
        </div></body></html>
        """
        _send_smtp_email_notification(
            recipient_email_address=new_staff_account.user_email_address,
            email_subject_line="🎉 Welcome to TrekVista: Your Staff Account is Ready",
            email_html_body=email_body
        )
    except Exception as email_err:
        current_app.logger.warning(f"Failed to send staff welcome email: {email_err}")

    return jsonify({
        "creation_successful": True,
        "message": "Staff account created successfully.",
        "staff_account": new_staff_account.to_safe_public_dict()
    }), 201

@admin_operations_blueprint.route("/users/<int:target_user_account_id>/blacklist", methods=["PATCH"])
@jwt_required()
@require_admin_role
def handle_toggle_user_blacklist_status(target_user_account_id: int):

    target_user = PlatformUserAccount.query.get(target_user_account_id)
    if target_user is None:
        return jsonify({
            "error": f"No user account found with id={target_user_account_id}.",
            "error_code": "USER_NOT_FOUND"
        }), 404

    if target_user.assigned_platform_role == UserPlatformRole.ADMIN:
        return jsonify({
            "error": "Admin accounts cannot be blacklisted.",
            "error_code": "CANNOT_BLACKLIST_ADMIN"
        }), 403

    target_user.is_account_blacklisted = not target_user.is_account_blacklisted
    db.session.commit()

    action_taken = "blacklisted" if target_user.is_account_blacklisted else "un-blacklisted"
    current_app.logger.warning(
        f"Admin {action_taken} user account: {target_user.user_email_address} "
        f"(id={target_user_account_id})"
    )

    return jsonify({
        "action_successful": True,
        "message": f"User account has been {action_taken}.",
        "is_account_blacklisted": target_user.is_account_blacklisted,
        "affected_user": target_user.to_safe_public_dict()
    }), 200

@admin_operations_blueprint.route("/users/<int:target_user_account_id>", methods=["DELETE"])
@jwt_required()
@require_admin_role
def handle_delete_user_account(target_user_account_id: int):

    target_user = PlatformUserAccount.query.get(target_user_account_id)
    if target_user is None:
        return jsonify({
            "error": f"No user account found with id={target_user_account_id}.",
            "error_code": "USER_NOT_FOUND"
        }), 404

    if target_user.assigned_platform_role == UserPlatformRole.ADMIN:
        return jsonify({
            "error": "Admin accounts cannot be deleted.",
            "error_code": "CANNOT_DELETE_ADMIN"
        }), 403

    user_email_for_log = target_user.user_email_address
    db.session.delete(target_user)
    db.session.commit()

    current_app.logger.warning(
        f"Admin deleted user account: {user_email_for_log} (id={target_user_account_id})"
    )

    return jsonify({
        "deletion_successful": True,
        "message": f"User account '{user_email_for_log}' has been permanently deleted."
    }), 200

@admin_operations_blueprint.route("/expeditions/<int:expedition_record_id>/participants", methods=["GET"])
@jwt_required()
@require_admin_role
def handle_get_expedition_participant_list_for_admin(expedition_record_id: int):

    target_expedition = TrekkingRouteExpedition.query.get(expedition_record_id)
    if target_expedition is None:
        return jsonify({"error": "Expedition not found.", "error_code": "EXPEDITION_NOT_FOUND"}), 404

    all_bookings_for_expedition = (
        target_expedition.registered_participant_bookings
        .order_by(ParticipantBookingRecord.booking_placed_at_utc.asc())
        .all()
    )

    return jsonify({
        "expedition_name": target_expedition.expedition_route_name,
        "expedition_id": expedition_record_id,
        "total_bookings": len(all_bookings_for_expedition),
        "participant_bookings": [b.to_full_detail_dict() for b in all_bookings_for_expedition]
    }), 200
