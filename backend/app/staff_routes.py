

from functools import wraps

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt
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
from .schemas import StaffExpeditionStatusUpdateRequestSchema

staff_operations_blueprint = Blueprint(
    "staff_operations_blueprint",
    __name__,
    url_prefix="/api/staff"
)

_staff_status_update_schema = StaffExpeditionStatusUpdateRequestSchema()

STAFF_PERMITTED_STATUS_TRANSITIONS = {
    ExpeditionLifecycleStatus.OPEN: [
        ExpeditionLifecycleStatus.CLOSED,
        ExpeditionLifecycleStatus.COMPLETED,
    ],
    ExpeditionLifecycleStatus.CLOSED: [
        ExpeditionLifecycleStatus.OPEN,
        ExpeditionLifecycleStatus.COMPLETED,
    ],
}

def require_staff_role(route_handler_function):

    @wraps(route_handler_function)
    def staff_role_enforcement_wrapper(*args, **kwargs):
        incoming_jwt_claims = get_jwt()
        if incoming_jwt_claims.get("platform_role") != UserPlatformRole.STAFF.value:
            return jsonify({
                "authorisation_error": "This endpoint is restricted to Trek Staff accounts only.",
                "error_code": "INSUFFICIENT_ROLE"
            }), 403
        return route_handler_function(*args, **kwargs)
    return staff_role_enforcement_wrapper

def _extract_current_staff_account_id_from_jwt() -> int:

    return get_jwt().get("user_account_id")

@staff_operations_blueprint.route("/dashboard/summary", methods=["GET"])
@jwt_required()
@require_staff_role
def handle_staff_dashboard_summary_retrieval():

    current_staff_id = _extract_current_staff_account_id_from_jwt()

    assigned_expeditions_by_status = {}
    for lifecycle_status in ExpeditionLifecycleStatus:
        count = TrekkingRouteExpedition.query.filter_by(
            assigned_staff_leader_id=current_staff_id,
            current_expedition_lifecycle_status=lifecycle_status
        ).count()
        assigned_expeditions_by_status[lifecycle_status.value] = count

    total_participants_across_assignments = (
        db.session.query(db.func.count(ParticipantBookingRecord.participant_booking_record_id))
        .join(
            TrekkingRouteExpedition,
            ParticipantBookingRecord.booked_expedition_instance_id ==
            TrekkingRouteExpedition.trekking_route_expedition_id
        )
        .filter(
            TrekkingRouteExpedition.assigned_staff_leader_id == current_staff_id,
            ParticipantBookingRecord.current_booking_lifecycle_status == BookingLifecycleStatus.BOOKED
        )
        .scalar()
    )

    return jsonify({
        "staff_dashboard_summary": {
            "assigned_expedition_counts_by_status": assigned_expeditions_by_status,
            "total_active_participants_under_management": total_participants_across_assignments or 0,
        }
    }), 200

@staff_operations_blueprint.route("/assigned-expeditions", methods=["GET"])
@jwt_required()
@require_staff_role
def handle_list_staff_assigned_expeditions():

    current_staff_id = _extract_current_staff_account_id_from_jwt()
    status_filter_value = request.args.get("status_filter", None)

    assigned_expedition_query = TrekkingRouteExpedition.query.filter_by(
        assigned_staff_leader_id=current_staff_id
    )

    if status_filter_value:
        try:
            parsed_status = ExpeditionLifecycleStatus(status_filter_value)
            assigned_expedition_query = assigned_expedition_query.filter_by(
                current_expedition_lifecycle_status=parsed_status
            )
        except ValueError:
            return jsonify({
                "error": f"'{status_filter_value}' is not a valid expedition status.",
                "error_code": "INVALID_STATUS_FILTER"
            }), 400

    assigned_expeditions = assigned_expedition_query.order_by(
        TrekkingRouteExpedition.expedition_scheduled_start_date.asc()
    ).all()

    return jsonify({
        "assigned_expeditions": [e.to_public_summary_dict() for e in assigned_expeditions],
        "total_assigned_count": len(assigned_expeditions)
    }), 200

@staff_operations_blueprint.route(
    "/assigned-expeditions/<int:expedition_record_id>/operational-update",
    methods=["PATCH"]
)
@jwt_required()
@require_staff_role
def handle_staff_expedition_operational_update(expedition_record_id: int):

    current_staff_id = _extract_current_staff_account_id_from_jwt()

    target_expedition = TrekkingRouteExpedition.query.filter_by(
        trekking_route_expedition_id=expedition_record_id,
        assigned_staff_leader_id=current_staff_id
    ).first()

    if target_expedition is None:
        return jsonify({
            "error": "Expedition not found or you are not assigned to it.",
            "error_code": "EXPEDITION_NOT_FOUND_OR_UNAUTHORIZED"
        }), 404

    try:
        validated_operational_update = _staff_status_update_schema.load(
            request.get_json(force=True, silent=True) or {}
        )
    except ValidationError as schema_error:
        return jsonify({"validation_errors": schema_error.messages}), 400

    requested_new_status_str = validated_operational_update.get("current_expedition_lifecycle_status")
    if requested_new_status_str:
        requested_new_status = ExpeditionLifecycleStatus(requested_new_status_str)
        current_status = target_expedition.current_expedition_lifecycle_status

        permitted_transitions = STAFF_PERMITTED_STATUS_TRANSITIONS.get(current_status, [])
        if requested_new_status != current_status and requested_new_status not in permitted_transitions:
            return jsonify({
                "error": (
                    f"Cannot transition from '{current_status.value}' to "
                    f"'{requested_new_status.value}'. "
                    f"Permitted next statuses from '{current_status.value}': "
                    f"{[s.value for s in permitted_transitions]}"
                ),
                "error_code": "INVALID_STATUS_TRANSITION"
            }), 409

        target_expedition.current_expedition_lifecycle_status = requested_new_status

        if requested_new_status == ExpeditionLifecycleStatus.COMPLETED:
            active_bookings_to_complete = (
                target_expedition.registered_participant_bookings
                .filter_by(current_booking_lifecycle_status=BookingLifecycleStatus.BOOKED)
                .all()
            )
            for booking_record in active_bookings_to_complete:
                booking_record.current_booking_lifecycle_status = BookingLifecycleStatus.COMPLETED
            current_app.logger.info(
                f"Staff completed expedition id={expedition_record_id}: "
                f"Marked {len(active_bookings_to_complete)} bookings as COMPLETED."
            )

    if validated_operational_update.get("available_participant_slots_remaining") is not None:
        adjusted_slot_count = validated_operational_update["available_participant_slots_remaining"]
        if adjusted_slot_count > target_expedition.total_participant_slots_capacity:
            return jsonify({
                "error": (
                    f"Available slots ({adjusted_slot_count}) cannot exceed "
                    f"total capacity ({target_expedition.total_participant_slots_capacity})."
                ),
                "error_code": "SLOTS_EXCEED_CAPACITY"
            }), 409
        target_expedition.available_participant_slots_remaining = adjusted_slot_count

    db.session.commit()

    try:
        redis_client = cache.cache._write_client
        prefix = current_app.config.get("CACHE_KEY_PREFIX_OPEN_TREKS", "trek_platform:open_treks:")
        keys_to_delete = redis_client.keys(f"{prefix}*")
        if keys_to_delete:
            redis_client.delete(*keys_to_delete)
    except Exception as cache_error:
        current_app.logger.warning(f"Cache invalidation failed after staff update: {cache_error}")

    return jsonify({
        "update_successful": True,
        "updated_expedition": target_expedition.to_public_summary_dict()
    }), 200

@staff_operations_blueprint.route(
    "/assigned-expeditions/<int:expedition_record_id>/participants",
    methods=["GET"]
)
@jwt_required()
@require_staff_role
def handle_get_participant_list_for_assigned_expedition(expedition_record_id: int):

    current_staff_id = _extract_current_staff_account_id_from_jwt()

    target_expedition = TrekkingRouteExpedition.query.filter_by(
        trekking_route_expedition_id=expedition_record_id,
        assigned_staff_leader_id=current_staff_id
    ).first()

    if target_expedition is None:
        return jsonify({
            "error": "Expedition not found or you are not assigned to it.",
            "error_code": "EXPEDITION_NOT_FOUND_OR_UNAUTHORIZED"
        }), 404

    show_all_statuses = request.args.get("show_all_statuses", "false").lower() == "true"

    participant_booking_query = target_expedition.registered_participant_bookings

    if not show_all_statuses:
        participant_booking_query = participant_booking_query.filter_by(
            current_booking_lifecycle_status=BookingLifecycleStatus.BOOKED
        )

    all_participants = participant_booking_query.order_by(
        ParticipantBookingRecord.booking_placed_at_utc.asc()
    ).all()

    return jsonify({
        "expedition_name": target_expedition.expedition_route_name,
        "expedition_id": expedition_record_id,
        "confirmed_participant_count": target_expedition.total_participant_slots_capacity
            - target_expedition.available_participant_slots_remaining,
        "available_slots_remaining": target_expedition.available_participant_slots_remaining,
        "participant_roster": [p.to_full_detail_dict() for p in all_participants]
    }), 200
