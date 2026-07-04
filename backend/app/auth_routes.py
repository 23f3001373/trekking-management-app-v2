"""
auth_routes.py — Authentication Blueprint
==========================================
Handles all unauthenticated and session-management endpoints:

  POST /api/auth/register  — Trekker self-registration
  POST /api/auth/login     — All roles (returns role-scoped JWT)
  POST /api/auth/refresh   — Issue a new access token using a refresh token
  DELETE /api/auth/logout  — Client-side token invalidation guidance

Design Decisions
-----------------
• JWT tokens are returned in the response body (not set-cookie) so the
  Vue.js SPA can store them in memory (most secure) or localStorage
  and attach them as `Authorization: Bearer <token>` headers.
• Refresh tokens enable silent reauthentication without re-entering credentials.
• Admin and Staff accounts cannot be created through this blueprint; they are
  provisioned exclusively through the Admin panel (admin_routes.py).
• Blacklisted accounts are refused login at the credential check stage with
  HTTP 403 Forbidden (not 401) to distinguish "wrong password" from "banned".
"""

import uuid
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    jwt_required,
    get_jwt_identity,
    get_jwt,
)
from marshmallow import ValidationError

from .extensions import database_extension as db
from .models import PlatformUserAccount, UserPlatformRole
from .schemas import TrekkerSelfRegistrationRequestSchema, UserLoginRequestSchema


# --------------------------------------------------------------------------- #
# Blueprint Declaration                                                         #
# --------------------------------------------------------------------------- #
# `url_prefix="/api/auth"` is applied at registration time in __init__.py,
# so all routes here are relative to that prefix.
authentication_blueprint = Blueprint(
    "authentication_blueprint",
    __name__,
    url_prefix="/api/auth"
)

# Schema instances are created once at module load, not on every request,
# to avoid the overhead of repeated class instantiation.
_trekker_registration_schema = TrekkerSelfRegistrationRequestSchema()
_user_login_schema = UserLoginRequestSchema()


# --------------------------------------------------------------------------- #
# Route: POST /api/auth/register                                                #
# --------------------------------------------------------------------------- #

@authentication_blueprint.route("/register", methods=["POST"])
def handle_trekker_self_registration():
    """
    Registers a brand-new Trekker account.

    WHY only Trekkers can self-register?
    Admin and Staff accounts hold elevated privileges that must be granted
    deliberately by a trusted administrator. Allowing open registration for
    those roles would be a critical privilege-escalation vulnerability.

    Flow:
      1. Validate request JSON against TrekkerSelfRegistrationRequestSchema.
      2. Check that no account with the same email already exists (unique email).
      3. Create a new PlatformUserAccount with role=TREKKER.
      4. Hash and store the password via set_hashed_password().
      5. Return the new account's safe public dict with HTTP 201 Created.

    Returns:
        201: Account created successfully; includes account details (no password).
        400: Validation error — missing fields or constraint violations.
        409: Email address already registered.
    """
    # ---- 1. Schema validation ---- #
    try:
        validated_registration_data = _trekker_registration_schema.load(
            request.get_json(force=True, silent=True) or {}
        )
    except ValidationError as schema_validation_error:
        return jsonify({
            "registration_failed": True,
            "validation_errors": schema_validation_error.messages
        }), 400

    # ---- 2. Email uniqueness check ---- #
    submitted_email = validated_registration_data["user_email_address"].lower().strip()
    existing_account_with_email = PlatformUserAccount.query.filter_by(
        user_email_address=submitted_email
    ).first()

    if existing_account_with_email is not None:
        return jsonify({
            "registration_failed": True,
            "error": "An account with this email address already exists. Please log in instead.",
            "error_code": "EMAIL_ALREADY_REGISTERED"
        }), 409

    # ---- 3. Construct and persist the new Trekker account ---- #
    newly_created_trekker_account = PlatformUserAccount(
        user_full_name=validated_registration_data["user_full_name"].strip(),
        user_email_address=submitted_email,
        assigned_platform_role=UserPlatformRole.TREKKER,
        user_contact_phone_number=validated_registration_data.get("user_contact_phone_number"),
        is_account_active=True,
        is_account_blacklisted=False,
    )

    # 4. Hash the password — plaintext is discarded after this call.
    newly_created_trekker_account.set_hashed_password(
        validated_registration_data["raw_password"]
    )

    db.session.add(newly_created_trekker_account)
    db.session.commit()

    current_app.logger.info(
        f"New Trekker account registered: {submitted_email} "
        f"(id={newly_created_trekker_account.user_account_id})"
    )

    return jsonify({
        "registration_successful": True,
        "message": "Your trekker account has been created. You can now log in.",
        "account_details": newly_created_trekker_account.to_safe_public_dict()
    }), 201


# --------------------------------------------------------------------------- #
# Route: POST /api/auth/login                                                   #
# --------------------------------------------------------------------------- #

@authentication_blueprint.route("/login", methods=["POST"])
def handle_user_login():
    """
    Authenticates a user of any role and returns a JWT access + refresh token pair.

    The response payload includes the user's role so the Vue.js SPA can
    immediately route to the correct dashboard (Admin/Staff/Trekker) without
    a second API call.

    The JWT identity is set to the user's email address (a stable, human-readable
    unique identifier). The role is embedded as an additional claim so route
    decorators can perform role checks without a DB lookup on every request.

    Flow:
      1. Validate login credentials via schema.
      2. Look up the account by email.
      3. Verify password hash.
      4. Check for blacklist or deactivation.
      5. Generate JWT access + refresh tokens with role claim.
      6. Return tokens and account summary.

    Returns:
        200: Login successful; includes access_token, refresh_token, and user info.
        400: Validation error on the request body.
        401: Email not found or password incorrect (generic message prevents enumeration).
        403: Account is blacklisted or deactivated.
    """
    # ---- 1. Validate the incoming credentials payload ---- #
    try:
        validated_login_credentials = _user_login_schema.load(
            request.get_json(force=True, silent=True) or {}
        )
    except ValidationError as schema_validation_error:
        return jsonify({
            "login_failed": True,
            "validation_errors": schema_validation_error.messages
        }), 400

    submitted_email = validated_login_credentials["user_email_address"].lower().strip()

    # ---- 2. Look up account by email ---- #
    matched_user_account = PlatformUserAccount.query.filter_by(
        user_email_address=submitted_email
    ).first()

    # ---- 3. Verify password (constant-time comparison via werkzeug) ---- #
    # We use the same generic error for "not found" AND "wrong password" to
    # prevent email enumeration attacks (attacker can't tell which one failed).
    if matched_user_account is None or not matched_user_account.verify_submitted_password(
        validated_login_credentials["submitted_password"]
    ):
        return jsonify({
            "login_failed": True,
            "error": "Invalid email address or password.",
            "error_code": "INVALID_CREDENTIALS"
        }), 401

    # ---- 4. Check account standing ---- #
    if matched_user_account.is_account_blacklisted:
        return jsonify({
            "login_failed": True,
            "error": "Your account has been suspended. Please contact support.",
            "error_code": "ACCOUNT_BLACKLISTED"
        }), 403

    if not matched_user_account.is_account_active:
        return jsonify({
            "login_failed": True,
            "error": "Your account is currently deactivated. Please contact support.",
            "error_code": "ACCOUNT_DEACTIVATED"
        }), 403

    # ---- 5. Generate JWT token pair ---- #
    # `additional_claims` embeds the role and account ID directly in the token payload.
    # Route decorators can read these without hitting the database, improving performance.
    jwt_additional_claims = {
        "platform_role": matched_user_account.assigned_platform_role.value,
        "user_account_id": matched_user_account.user_account_id,
        "user_full_name": matched_user_account.user_full_name,
    }

    jwt_access_token = create_access_token(
        identity=matched_user_account.user_email_address,
        additional_claims=jwt_additional_claims
    )
    jwt_refresh_token = create_refresh_token(
        identity=matched_user_account.user_email_address,
        additional_claims=jwt_additional_claims
    )

    current_app.logger.info(
        f"Login successful: {submitted_email} "
        f"(role={matched_user_account.assigned_platform_role.value})"
    )

    return jsonify({
        "login_successful": True,
        "access_token": jwt_access_token,
        "refresh_token": jwt_refresh_token,
        "authenticated_user": matched_user_account.to_safe_public_dict()
    }), 200


# --------------------------------------------------------------------------- #
# Route: POST /api/auth/refresh and /api/auth/refresh-token                     #
# --------------------------------------------------------------------------- #

@authentication_blueprint.route("/refresh", methods=["POST"])
@authentication_blueprint.route("/refresh-token", methods=["POST"])
@jwt_required(refresh=True)  # Requires a valid REFRESH token (not an access token).
def handle_access_token_refresh():
    """
    Issues a new short-lived access token using a valid refresh token.

    This enables "silent refresh" in the SPA: when an API call returns 401
    TOKEN_EXPIRED, the Vue.js auth interceptor automatically sends the
    refresh token to this endpoint and retries the original request with the
    new access token — the user never sees a login page.

    The refresh token itself is NOT rotated here for simplicity. In a production
    system, consider implementing refresh token rotation (single-use refresh tokens)
    to limit replay-attack exposure.

    Returns:
        200: New access token issued successfully.
        401: Refresh token is expired or invalid.
    """
    requesting_user_email = get_jwt_identity()
    existing_jwt_claims = get_jwt()

    # Re-fetch the account to ensure it hasn't been blacklisted since the
    # refresh token was originally issued (a token can outlive a ban decision).
    current_user_account = PlatformUserAccount.query.filter_by(
        user_email_address=requesting_user_email
    ).first()

    if current_user_account is None or current_user_account.is_account_blacklisted:
        return jsonify({
            "refresh_failed": True,
            "error": "Cannot refresh token for this account.",
            "error_code": "ACCOUNT_INVALID"
        }), 401

    refreshed_jwt_claims = {
        "platform_role": current_user_account.assigned_platform_role.value,
        "user_account_id": current_user_account.user_account_id,
        "user_full_name": current_user_account.user_full_name,
    }

    new_access_token = create_access_token(
        identity=requesting_user_email,
        additional_claims=refreshed_jwt_claims
    )

    return jsonify({
        "token_refreshed": True,
        "access_token": new_access_token,
        "new_access_token": new_access_token
    }), 200


# --------------------------------------------------------------------------- #
# Route: GET /api/auth/me                                                       #
# --------------------------------------------------------------------------- #

@authentication_blueprint.route("/me", methods=["GET"])
@jwt_required()
def handle_get_current_user_profile():
    """
    Returns the full profile of the currently authenticated user.

    The Vue.js SPA calls this on page load (after finding a stored token)
    to rehydrate the user's state (name, role, profile fields) without
    forcing a re-login. The JWT provides identity; this route provides the
    fresh DB record.

    Returns:
        200: Current user's safe public profile dict.
        404: JWT identity doesn't match any account (edge case — account deleted post-login).
    """
    requesting_user_email = get_jwt_identity()
    current_user_account = PlatformUserAccount.query.filter_by(
        user_email_address=requesting_user_email
    ).first()

    if current_user_account is None:
        return jsonify({
            "error": "Authenticated account not found.",
            "error_code": "ACCOUNT_NOT_FOUND"
        }), 404

    return jsonify({
        "current_user_profile": current_user_account.to_safe_public_dict()
    }), 200


# --------------------------------------------------------------------------- #
# Route: DELETE /api/auth/logout                                                #
# --------------------------------------------------------------------------- #

@authentication_blueprint.route("/logout", methods=["DELETE"])
@jwt_required()
def handle_user_logout():
    """
    Logs out the current user. Since we use stateless JWTs, we simply return
    success to the client so it can discard the tokens from memory/storage.
    """
    return jsonify({
        "logout_successful": True,
        "message": "Logged out successfully."
    }), 200


# --------------------------------------------------------------------------- #
# Route: PATCH /api/auth/update-profile                                         #
# --------------------------------------------------------------------------- #

@authentication_blueprint.route("/update-profile", methods=["PATCH"])
@jwt_required()
def handle_update_profile():
    """
    Updates the profile details of the currently authenticated user.
    Only allows updating specific non-sensitive fields.
    """
    requesting_user_email = get_jwt_identity()
    current_user_account = PlatformUserAccount.query.filter_by(
        user_email_address=requesting_user_email
    ).first()

    if current_user_account is None:
        return jsonify({"error": "Account not found."}), 404

    request_data = request.get_json(force=True, silent=True) or {}
    
    # Update optional profile fields
    if "user_full_name" in request_data:
        name = request_data["user_full_name"].strip()
        if len(name) >= 2:
            current_user_account.user_full_name = name
    
    if "user_contact_phone_number" in request_data:
        current_user_account.user_contact_phone_number = request_data["user_contact_phone_number"]
        
    if "user_profile_bio_summary" in request_data:
        current_user_account.user_profile_bio_summary = request_data["user_profile_bio_summary"]
        
    if "user_emergency_contact_name" in request_data:
        current_user_account.user_emergency_contact_name = request_data["user_emergency_contact_name"]
        
    if "user_emergency_contact_phone" in request_data:
        current_user_account.user_emergency_contact_phone = request_data["user_emergency_contact_phone"]

    db.session.commit()
    return jsonify({
        "profile_updated": True,
        "updated_user_profile": current_user_account.to_safe_public_dict()
    }), 200


# --------------------------------------------------------------------------- #
# Route: PATCH /api/auth/change-password                                         #
# --------------------------------------------------------------------------- #

@authentication_blueprint.route("/change-password", methods=["PATCH"])
@jwt_required()
def handle_change_password():
    """
    Changes the password of the currently authenticated user after verifying
    their current password.
    """
    requesting_user_email = get_jwt_identity()
    current_user_account = PlatformUserAccount.query.filter_by(
        user_email_address=requesting_user_email
    ).first()

    if current_user_account is None:
        return jsonify({"error": "Account not found."}), 404

    request_data = request.get_json(force=True, silent=True) or {}
    current_password = request_data.get("current_password")
    new_password = request_data.get("new_password")

    if not current_password or not new_password:
        return jsonify({"error": "Missing current or new password."}), 400

    if not current_user_account.verify_submitted_password(current_password):
        return jsonify({"error": "Incorrect current password."}), 400

    # Password complexity checks (matching the frontend constraints)
    if len(new_password) < 8 or not any(c.isupper() for c in new_password) or not any(c.isdigit() for c in new_password) or not any(not c.isalnum() for c in new_password):
        return jsonify({"error": "New password does not meet security requirements."}), 400

    current_user_account.set_hashed_password(new_password)
    db.session.commit()

    return jsonify({
        "password_changed": True,
        "message": "Password changed successfully."
    }), 200
