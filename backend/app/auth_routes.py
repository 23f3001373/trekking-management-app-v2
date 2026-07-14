

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

authentication_blueprint = Blueprint(
    "authentication_blueprint",
    __name__,
    url_prefix="/api/auth"
)

_trekker_registration_schema = TrekkerSelfRegistrationRequestSchema()
_user_login_schema = UserLoginRequestSchema()

@authentication_blueprint.route("/register", methods=["POST"])
def handle_trekker_self_registration():

    try:
        validated_registration_data = _trekker_registration_schema.load(
            request.get_json(force=True, silent=True) or {}
        )
    except ValidationError as schema_validation_error:
        return jsonify({
            "registration_failed": True,
            "validation_errors": schema_validation_error.messages
        }), 400

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

    newly_created_trekker_account = PlatformUserAccount(
        user_full_name=validated_registration_data["user_full_name"].strip(),
        user_email_address=submitted_email,
        assigned_platform_role=UserPlatformRole.TREKKER,
        user_contact_phone_number=validated_registration_data.get("user_contact_phone_number"),
        is_account_active=True,
        is_account_blacklisted=False,
    )

    newly_created_trekker_account.set_hashed_password(
        validated_registration_data["raw_password"]
    )

    db.session.add(newly_created_trekker_account)
    db.session.commit()

    current_app.logger.info(
        f"New account registered: {submitted_email} "
        f"(role=Trekker, id={newly_created_trekker_account.user_account_id})"
    )

    return jsonify({
        "registration_successful": True,
        "message": "Your trekker account has been created. You can now log in.",
        "account_details": newly_created_trekker_account.to_safe_public_dict()
    }), 201

@authentication_blueprint.route("/login", methods=["POST"])
def handle_user_login():

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

    matched_user_account = PlatformUserAccount.query.filter_by(
        user_email_address=submitted_email
    ).first()

    if matched_user_account is None or not matched_user_account.verify_submitted_password(
        validated_login_credentials["submitted_password"]
    ):
        return jsonify({
            "login_failed": True,
            "error": "Invalid email address or password.",
            "error_code": "INVALID_CREDENTIALS"
        }), 401

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

@authentication_blueprint.route("/refresh", methods=["POST"])
@authentication_blueprint.route("/refresh-token", methods=["POST"])
@jwt_required(refresh=True)
def handle_access_token_refresh():

    requesting_user_email = get_jwt_identity()
    existing_jwt_claims = get_jwt()

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

@authentication_blueprint.route("/me", methods=["GET"])
@jwt_required()
def handle_get_current_user_profile():

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

@authentication_blueprint.route("/logout", methods=["DELETE"])
@jwt_required()
def handle_user_logout():

    return jsonify({
        "logout_successful": True,
        "message": "Logged out successfully."
    }), 200

@authentication_blueprint.route("/update-profile", methods=["PATCH"])
@jwt_required()
def handle_update_profile():

    requesting_user_email = get_jwt_identity()
    current_user_account = PlatformUserAccount.query.filter_by(
        user_email_address=requesting_user_email
    ).first()

    if current_user_account is None:
        return jsonify({"error": "Account not found."}), 404

    request_data = request.get_json(force=True, silent=True) or {}
    
    # check credentials
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

# query db

@authentication_blueprint.route("/change-password", methods=["PATCH"])
@jwt_required()
def handle_change_password():

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

    if len(new_password) < 8 or not any(c.isupper() for c in new_password) or not any(c.isdigit() for c in new_password) or not any(not c.isalnum() for c in new_password):
        return jsonify({"error": "New password does not meet security requirements."}), 400

    current_user_account.set_hashed_password(new_password)
    db.session.commit()

    return jsonify({
        "password_changed": True,
        "message": "Password changed successfully."
    }), 200
