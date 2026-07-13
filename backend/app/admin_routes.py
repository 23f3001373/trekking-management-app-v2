"""
admin_routes.py — Admin Operations Blueprint
=============================================
All endpoints under `/api/admin/*` require:
  (a) A valid JWT access token.
  (b) The `platform_role` claim in that token to equal "Admin".

Any request that fails either check is rejected before the route function body
is even entered, via the `require_admin_role` decorator defined below.

Responsibilities of this Blueprint
------------------------------------
  • Trek CRUD: Create, read, update, delete TrekkingRouteExpedition records.
  • Staff Management: Create Staff accounts, assign staff to expeditions.
  • User Management: List all users, toggle blacklist/active flags.
  • Dashboard Metrics: Aggregate counters for the Admin overview panel.
  • Redis Cache Invalidation: Any write to expedition data clears the cache
    to prevent Trekkers from seeing stale open-trek listings.

Redis Cache Strategy
---------------------
The open-treks listing is cached at key `trek_platform:open_treks:<filter_hash>`.
Whenever an expedition is created, updated, or deleted by the Admin, the entire
open-treks cache namespace is flushed using `cache.delete_many()` with a pattern.
This is a "write-through invalidation" strategy: cache is cleared on writes,
repopulated lazily on the next read.
"""

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


# --------------------------------------------------------------------------- #
# Blueprint Declaration                                                         #
# --------------------------------------------------------------------------- #
admin_operations_blueprint = Blueprint(
    "admin_operations_blueprint",
    __name__,
    url_prefix="/api/admin"
)

# Pre-instantiated schema objects (module-level, created once).
_expedition_create_schema = ExpeditionCreateRequestSchema()
_expedition_update_schema = ExpeditionUpdateRequestSchema()
_staff_create_schema = AdminCreateStaffAccountRequestSchema()


# --------------------------------------------------------------------------- #
# RBAC Decorator — Admin Role Guard                                             #
# --------------------------------------------------------------------------- #

def require_admin_role(route_handler_function):
    """
    Decorator that enforces Admin-only access on any route it wraps.

    This is applied in addition to `@jwt_required()` so the check chain is:
      1. JWT present and valid? (jwt_required handles this)
      2. JWT claims show role == "Admin"? (this decorator handles this)

    If either check fails, the request is rejected before the route body runs.
    Using a decorator keeps the role-check logic out of each route function,
    preventing copy-paste errors and ensuring the check cannot be accidentally omitted.

    Args:
        route_handler_function: The Flask route function being decorated.

    Returns:
        Callable: The wrapped function that includes the admin role check.
    """
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


# --------------------------------------------------------------------------- #
# Utility: Invalidate Open-Treks Cache                                          #
# --------------------------------------------------------------------------- #

def _invalidate_open_treks_redis_cache() -> None:
    """
    Clears all cached open-trek listing entries from Redis.

    WHY flush ALL open-treks keys instead of one specific key?
    When an expedition is updated, we don't know which filter combinations
    it appears in (all difficulties, EASY only, MODERATE+location, etc.).
    The safest and simplest invalidation strategy is to flush the entire
    open-treks namespace. The slight over-invalidation cost is acceptable
    because trek updates are infrequent admin actions.

    The cache key prefix is defined in config.py as:
      CACHE_KEY_PREFIX_OPEN_TREKS = "trek_platform:open_treks:"
    """
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
            # Fallback for simple/in-memory cache (e.g. SimpleCache in testing)
            cache.clear()
            current_app.logger.debug("Cleared testing/fallback cache.")
    except Exception as cache_invalidation_exception:
        # Cache invalidation failure is non-fatal — log it but don't crash the request.
        current_app.logger.warning(
            f"Cache invalidation failed (non-fatal): {cache_invalidation_exception}"
        )


# =========================================================================== #
#  ADMIN DASHBOARD METRICS                                                      #
# =========================================================================== #

@admin_operations_blueprint.route("/dashboard/metrics", methods=["GET"])
@jwt_required()
@require_admin_role
def handle_admin_dashboard_metrics_retrieval():
    """
    Returns aggregate metric counters for the Admin dashboard overview panel.

    Computed with optimised SQL COUNT queries rather than loading all rows into
    Python — for large datasets, this is orders of magnitude faster than
    `len(TrekkingRouteExpedition.query.all())`.

    Returns:
        200: Dict of metric counters (total users, open expeditions, etc.)
    """
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

    return jsonify({
        "admin_dashboard_metrics": {
            "total_registered_trekkers": total_registered_trekkers,
            "total_staff_accounts": total_staff_accounts,
            "total_blacklisted_accounts": total_blacklisted_accounts,
            "total_expeditions_on_platform": total_expeditions,
            "currently_open_expeditions": open_expeditions_count,
            "active_participant_bookings": active_bookings_count,
        }
    }), 200


# =========================================================================== #
#  EXPEDITION CRUD ROUTES                                                        #
# =========================================================================== #

@admin_operations_blueprint.route("/expeditions", methods=["GET"])
@jwt_required()
@require_admin_role
def handle_list_all_expeditions_for_admin():
    """
    Lists ALL expeditions in the system regardless of status (Admin-only view).

    Unlike the Trekker's open-trek listing (which is cached and filtered),
    this endpoint always queries the live database so the Admin sees the
    current ground truth, including PENDING, CANCELLED, and COMPLETED records.

    Query Parameters:
        status_filter (str): Optional. Filter by lifecycle status.
        page (int): Page number for pagination (default 1).
        per_page (int): Results per page (default 20, max 100).

    Returns:
        200: Paginated list of expedition summary dicts.
    """
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
    """
    Creates a brand-new TrekkingRouteExpedition record (Admin only).

    The newly created expedition starts with `status=PENDING` and must be
    explicitly transitioned to APPROVED → OPEN by the Admin before trekkers
    can discover and book it.

    Slot initialisation: `available_participant_slots_remaining` is set equal
    to `total_participant_slots_capacity` at creation time (all slots free).

    Returns:
        201: Created expedition's full summary dict.
        400: Validation error from the request schema.
        422: Staff leader ID provided but no matching Staff account found.
    """
    try:
        validated_expedition_data = _expedition_create_schema.load(
            request.get_json(force=True, silent=True) or {}
        )
    except ValidationError as schema_error:
        return jsonify({"validation_errors": schema_error.messages}), 400

    # If a staff leader was specified, verify they exist and hold the STAFF role.
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
        available_participant_slots_remaining=slot_capacity,  # All slots free at creation.
        current_expedition_lifecycle_status=ExpeditionLifecycleStatus.PENDING,
        expedition_cover_image_url=validated_expedition_data.get("expedition_cover_image_url"),
        expedition_meeting_point_address=validated_expedition_data.get("expedition_meeting_point_address"),
        assigned_staff_leader_id=designated_staff_leader_id,
    )

    db.session.add(new_expedition_record)
    db.session.commit()

    # Invalidate the cache so the next trekker listing reflects the new expedition
    # (once it reaches OPEN status, it will be included in cached results).
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
    """
    Retrieves the full detail of a single expedition by its primary key.

    Returns:
        200: Expedition summary dict.
        404: No expedition found with the given ID.
    """
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
    """
    Applies partial updates to an existing expedition (Admin only).

    Only the fields present in the request body are updated; absent fields
    retain their current database values. This PATCH semantics (rather than PUT)
    is used to allow the Admin to change just the status or just the staff
    assignment without re-sending the entire expedition payload.

    Post-update, the Redis open-treks cache is invalidated to ensure trekkers
    see the updated information on their next page load.

    Returns:
        200: Updated expedition summary dict.
        400: Validation error.
        404: Expedition not found.
        422: Invalid staff leader ID.
    """
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

    # Apply only the non-None fields from the validated payload.
    # None values here mean "field was not included in the request" (see schema load_default=None).
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

    # Difficulty level requires enum conversion.
    if validated_update_payload.get("expedition_difficulty_level"):
        target_expedition.expedition_difficulty_level = ExpeditionDifficultyLevel(
            validated_update_payload["expedition_difficulty_level"]
        )

    # Status requires enum conversion.
    if validated_update_payload.get("current_expedition_lifecycle_status"):
        target_expedition.current_expedition_lifecycle_status = ExpeditionLifecycleStatus(
            validated_update_payload["current_expedition_lifecycle_status"]
        )

    # Slot capacity change: ensure it's not below current active bookings.
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

    # Staff leader update with validation.
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
    """
    Permanently deletes an expedition and all its associated booking records.

    WHY allow hard deletion instead of soft-delete?
    For the current scale of this platform, hard deletion is acceptable.
    The cascade `delete-orphan` on the `registered_participant_bookings`
    relationship ensures all linked ParticipantBookingRecord rows are also
    removed in the same transaction, maintaining referential integrity.

    In a production system with financial records, a soft-delete (`is_deleted=True`)
    flag would be preferred to preserve audit history.

    Returns:
        200: Deletion confirmation message.
        404: Expedition not found.
        409: Cannot delete an expedition with BOOKED (active) bookings.
    """
    target_expedition = TrekkingRouteExpedition.query.get(expedition_record_id)
    if target_expedition is None:
        return jsonify({
            "error": f"No expedition found with id={expedition_record_id}.",
            "error_code": "EXPEDITION_NOT_FOUND"
        }), 404

    # Safety gate: refuse to delete expeditions with active bookings.
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


# =========================================================================== #
#  USER & STAFF MANAGEMENT ROUTES                                               #
# =========================================================================== #

@admin_operations_blueprint.route("/users", methods=["GET"])
@jwt_required()
@require_admin_role
def handle_list_all_platform_users():
    """
    Lists all non-Admin user accounts for the Admin management panel.

    Supports optional filtering by role and blacklist status via query params.
    Excludes the Admin's own account from the list (Admins manage users, not
    themselves through this endpoint).

    Query Parameters:
        role_filter (str): "Staff" or "Trekker".
        blacklisted_only (bool): "true" to show only blacklisted accounts.
        search_keyword (str): Case-insensitive match against name or email.

    Returns:
        200: List of user account dicts (password hashes excluded).
    """
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
    """
    Creates a new Staff account (Admin only).

    Staff accounts cannot self-register. The Admin creates them here and
    communicates the credentials to the new staff member through a secure
    out-of-band channel (e.g., encrypted email). The staff member should
    be prompted to change their password on first login.

    Returns:
        201: Created staff account's safe public dict.
        400: Validation error.
        409: Email already registered.
    """
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

    # Send credentials email to the newly created staff member (per wireframe details).
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
    """
    Toggles the blacklist flag on a non-Admin user account.

    Blacklisting immediately prevents the user from logging in on their
    next request (token refresh will also be denied). It does NOT delete
    the account or any historical data — it's a reversible soft-ban.

    Returns:
        200: Updated blacklist status and confirmation message.
        403: Attempted to blacklist an Admin account.
        404: User account not found.
    """
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

    # Toggle the current blacklist state.
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
    """
    Permanently deletes a non-Admin user account (Trekker or Staff).
    All associated bookings (if Trekker) will cascade delete.
    Any assigned expeditions (if Staff) will set the guide leader to NULL.
    """
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
    """
    Returns the full list of confirmed participant bookings for a specific
    expedition — an Admin view that includes all booking statuses.

    Returns:
        200: List of participant booking detail dicts.
        404: Expedition not found.
    """
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
