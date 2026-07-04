"""
staff_routes.py — Trek Staff Operations Blueprint
==================================================
All endpoints under `/api/staff/*` are accessible only to authenticated users
holding the `platform_role == "Staff"` JWT claim. The `require_staff_role`
decorator enforces this at the route level.

Staff Role Responsibilities
----------------------------
  1. VIEW assigned expeditions only (not the full platform catalog).
  2. UPDATE expedition status within permitted transitions:
       Open → Closed, Closed → Open, Open/Closed → Completed.
  3. ADJUST available_participant_slots_remaining for operational corrections
     (e.g., a participant dropped out without formally cancelling their booking).
  4. VIEW the registered participant list for their assigned expeditions.

WHY strict assignment scoping?
Staff members should only see and operate on expeditions they are responsible
for. Cross-expedition data access would be a data-leak risk if a staff member's
account were compromised. The `assigned_staff_leader_id == current_user_id`
check on every query is the enforcement mechanism.
"""

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


# --------------------------------------------------------------------------- #
# Blueprint Declaration                                                         #
# --------------------------------------------------------------------------- #
staff_operations_blueprint = Blueprint(
    "staff_operations_blueprint",
    __name__,
    url_prefix="/api/staff"
)

_staff_status_update_schema = StaffExpeditionStatusUpdateRequestSchema()

# Valid status transitions a staff member is allowed to make.
# Admin can do broader transitions; staff is limited to operational changes.
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


# --------------------------------------------------------------------------- #
# RBAC Decorator — Staff Role Guard                                             #
# --------------------------------------------------------------------------- #

def require_staff_role(route_handler_function):
    """
    Decorator that enforces Staff-only access on routes it wraps.

    Applied after `@jwt_required()` to form a two-layer auth check:
      1. JWT present and valid?
      2. JWT role claim == "Staff"?

    Note: Admin accounts intentionally do NOT pass this check. If the Admin
    needs to view staff-facing data, they should use the admin blueprint endpoints.
    This separation ensures the two dashboards remain distinct and testable.
    """
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


# --------------------------------------------------------------------------- #
# Utility: Get Current Staff Account ID from JWT                                #
# --------------------------------------------------------------------------- #

def _extract_current_staff_account_id_from_jwt() -> int:
    """
    Extracts and returns the `user_account_id` integer from the current
    request's JWT claims.

    This is called at the start of every staff route to determine which
    expeditions the authenticated staff member is authorised to access.
    All queries are then filtered by `assigned_staff_leader_id == this value`.

    Returns:
        int: The authenticated staff member's user_account_id.
    """
    return get_jwt().get("user_account_id")


# =========================================================================== #
#  STAFF DASHBOARD                                                              #
# =========================================================================== #

@staff_operations_blueprint.route("/dashboard/summary", methods=["GET"])
@jwt_required()
@require_staff_role
def handle_staff_dashboard_summary_retrieval():
    """
    Returns a summary of the staff member's current operational workload.

    Provides counts of their assigned expeditions by status — allowing the
    dashboard to show quick-glance badges like "2 Open, 1 Pending Completion".

    Returns:
        200: Dict of expedition status counts and staff profile summary.
    """
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


# =========================================================================== #
#  STAFF — VIEW ASSIGNED EXPEDITIONS                                            #
# =========================================================================== #

@staff_operations_blueprint.route("/assigned-expeditions", methods=["GET"])
@jwt_required()
@require_staff_role
def handle_list_staff_assigned_expeditions():
    """
    Returns all expeditions currently assigned to the authenticated staff member.

    Scoped strictly to `assigned_staff_leader_id == current_staff_id` —
    staff cannot query other staff members' expeditions.

    Query Parameters:
        status_filter (str): Optional. Filter by lifecycle status.

    Returns:
        200: List of expedition summary dicts assigned to this staff member.
    """
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


# =========================================================================== #
#  STAFF — UPDATE EXPEDITION STATUS & SLOTS                                     #
# =========================================================================== #

@staff_operations_blueprint.route(
    "/assigned-expeditions/<int:expedition_record_id>/operational-update",
    methods=["PATCH"]
)
@jwt_required()
@require_staff_role
def handle_staff_expedition_operational_update(expedition_record_id: int):
    """
    Allows a staff member to update the status and/or available slot count
    of an expedition they are assigned to.

    Status Transition Rules (enforced here, not in the schema):
      OPEN    → CLOSED     (booking window closed)
      OPEN    → COMPLETED  (trek finished)
      CLOSED  → OPEN       (re-open for last-minute bookings)
      CLOSED  → COMPLETED  (trek finished from closed state)

    Staff CANNOT:
      • Transition to PENDING or APPROVED (admin-only gates)
      • Transition to CANCELLED (admin-only)
      • Update expeditions they are NOT assigned to

    Slot Adjustment Logic:
      Staff can manually correct `available_participant_slots_remaining` to
      handle real-world discrepancies (e.g., a trekker's physical no-show
      that wasn't formally cancelled in the system). The adjusted value cannot
      exceed `total_participant_slots_capacity`.

    Returns:
        200: Updated expedition summary dict.
        400: Validation error.
        403: Staff member is not assigned to this expedition.
        404: Expedition not found.
        409: Invalid status transition attempted.
    """
    current_staff_id = _extract_current_staff_account_id_from_jwt()

    # --- Ownership verification: ensure this expedition belongs to this staff ---
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

    # --- Status transition validation ---
    requested_new_status_str = validated_operational_update.get("current_expedition_lifecycle_status")
    if requested_new_status_str:
        requested_new_status = ExpeditionLifecycleStatus(requested_new_status_str)
        current_status = target_expedition.current_expedition_lifecycle_status

        permitted_transitions = STAFF_PERMITTED_STATUS_TRANSITIONS.get(current_status, [])
        if requested_new_status not in permitted_transitions:
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

        # If marked COMPLETED, also mark all BOOKED records as COMPLETED.
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

    # --- Available slot adjustment ---
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

    # Invalidate cache — a slot count or status change affects what trekkers see.
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


# =========================================================================== #
#  STAFF — VIEW PARTICIPANT LIST                                                 #
# =========================================================================== #

@staff_operations_blueprint.route(
    "/assigned-expeditions/<int:expedition_record_id>/participants",
    methods=["GET"]
)
@jwt_required()
@require_staff_role
def handle_get_participant_list_for_assigned_expedition(expedition_record_id: int):
    """
    Returns the list of registered participants for a specific expedition
    that the authenticated staff member is assigned to.

    This is the operational roster — staff use it to prepare participant
    kits, track headcount at assembly points, and verify special requirements.
    Only BOOKED (confirmed) participants are returned by default; include
    `show_all_statuses=true` query param to also see cancelled records.

    Query Parameters:
        show_all_statuses (bool): Default false. If true, include cancelled participants.

    Returns:
        200: Participant roster with booking detail dicts.
        403: Not assigned to this expedition.
        404: Expedition not found.
    """
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
        # By default, show only confirmed (BOOKED) participants for the roster.
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
