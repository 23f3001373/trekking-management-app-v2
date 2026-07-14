

from marshmallow import (
    Schema,
    fields,
    validate,
    validates,
    validates_schema,
    ValidationError,
    post_load,
    EXCLUDE,
)
import re
from datetime import date

def _validate_strong_password(raw_password_value: str) -> None:

    if len(raw_password_value) < 8:
        raise ValidationError("Password must be at least 8 characters long.")
    if not re.search(r"[A-Z]", raw_password_value):
        raise ValidationError("Password must contain at least one uppercase letter.")
    if not re.search(r"\d", raw_password_value):
        raise ValidationError("Password must contain at least one digit.")
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>_\-]", raw_password_value):
        raise ValidationError("Password must contain at least one special character.")

_email_validator = validate.Email(error="A valid email address is required.")

_phone_validator = validate.Regexp(
    r"^\+?[\d\s\-\(\)]{7,20}$",
    error="Phone number must be 7–20 digits and may include +, spaces, dashes, or parentheses."
)

class TrekkerSelfRegistrationRequestSchema(Schema):

    class Meta:
        unknown = EXCLUDE

    user_full_name = fields.Str(
        required=True,
        validate=validate.Length(min=2, max=120, error="Full name must be 2–120 characters."),
        metadata={"description": "Trekker's display name shown on dashboards."}
    )

    user_email_address = fields.Email(
        required=True,
        validate=_email_validator,
        metadata={"description": "Unique login email; used for booking confirmations."}
    )

    raw_password = fields.Str(
        required=True,
        load_only=True,
        validate=_validate_strong_password,
        metadata={"description": "Must be ≥8 chars with uppercase, digit, and special char."}
    )

    user_contact_phone_number = fields.Str(
        required=False,
        allow_none=True,
        validate=_phone_validator,
        load_default=None,
    )

class UserLoginRequestSchema(Schema):

    class Meta:
        unknown = EXCLUDE

    user_email_address = fields.Email(
        required=True,
        validate=_email_validator,
    )

    submitted_password = fields.Str(
        required=True,
        load_only=True,
        validate=validate.Length(min=1, error="Password cannot be empty."),
    )

class PasswordChangeRequestSchema(Schema):

    class Meta:
        unknown = EXCLUDE

    current_password = fields.Str(required=True, load_only=True)
    new_password = fields.Str(
        required=True,
        load_only=True,
        validate=_validate_strong_password,
    )

    @validates_schema
    def validate_passwords_are_different(self, incoming_data, **kwargs):

        if incoming_data.get("current_password") == incoming_data.get("new_password"):
            raise ValidationError(
                "New password must be different from the current password.",
                field_name="new_password"
            )

class TrekkerProfileUpdateRequestSchema(Schema):

    class Meta:
        unknown = EXCLUDE

    user_full_name = fields.Str(
        validate=validate.Length(min=2, max=120),
        load_default=None,
    )
    user_contact_phone_number = fields.Str(
        validate=_phone_validator,
        allow_none=True,
        load_default=None,
    )
    user_profile_bio_summary = fields.Str(
        validate=validate.Length(max=1000, error="Bio must be under 1000 characters."),
        allow_none=True,
        load_default=None,
    )
    user_emergency_contact_name = fields.Str(
        validate=validate.Length(max=120),
        allow_none=True,
        load_default=None,
    )
    user_emergency_contact_phone = fields.Str(
        validate=_phone_validator,
        allow_none=True,
        load_default=None,
    )

class AdminCreateStaffAccountRequestSchema(Schema):

    class Meta:
        unknown = EXCLUDE

    user_full_name = fields.Str(
        required=True,
        validate=validate.Length(min=2, max=120),
    )
    user_email_address = fields.Email(required=True, validate=_email_validator)
    raw_password = fields.Str(
        required=True,
        load_only=True,
        validate=_validate_strong_password,
    )
    user_contact_phone_number = fields.Str(
        validate=_phone_validator,
        allow_none=True,
        load_default=None,
    )

class ExpeditionCreateRequestSchema(Schema):

    class Meta:
        unknown = EXCLUDE

    expedition_route_name = fields.Str(
        required=True,
        validate=validate.Length(min=5, max=200, error="Route name must be 5–200 characters."),
    )
    expedition_geographical_location = fields.Str(
        required=True,
        validate=validate.Length(min=3, max=200),
    )
    expedition_detailed_description = fields.Str(required=False, allow_none=True, load_default=None)
    expedition_difficulty_level = fields.Str(
        required=True,
        validate=validate.OneOf(
            ["Easy", "Moderate", "Hard"],
            error="Difficulty must be one of: Easy, Moderate, Hard."
        ),
    )
    expedition_duration_in_days = fields.Int(
        required=True,
        validate=validate.Range(min=1, max=365, error="Duration must be 1–365 days."),
    )
    expedition_price_per_person_inr = fields.Float(
        required=False,
        validate=validate.Range(min=0.0, error="Price cannot be negative."),
        load_default=0.0,
    )
    expedition_scheduled_start_date = fields.Date(
        required=False,
        allow_none=True,
        load_default=None,
    )
    expedition_scheduled_end_date = fields.Date(
        required=False,
        allow_none=True,
        load_default=None,
    )
    expedition_booking_cutoff_date = fields.Date(
        required=False,
        allow_none=True,
        load_default=None,
    )
    total_participant_slots_capacity = fields.Int(
        required=True,
        validate=validate.Range(min=1, max=500, error="Slots must be between 1 and 500."),
    )
    expedition_cover_image_url = fields.Url(
        required=False,
        allow_none=True,
        load_default=None,
    )
    expedition_meeting_point_address = fields.Str(
        required=False,
        allow_none=True,
        load_default=None,
        validate=validate.Length(max=300),
    )
    assigned_staff_leader_id = fields.Int(
        required=False,
        allow_none=True,
        load_default=None,
    )

    @validates_schema
    def validate_date_ordering(self, incoming_data, **kwargs):

        start = incoming_data.get("expedition_scheduled_start_date")
        end = incoming_data.get("expedition_scheduled_end_date")
        cutoff = incoming_data.get("expedition_booking_cutoff_date")

        if start and end and end < start:
            raise ValidationError(
                "End date must be on or after the start date.",
                field_name="expedition_scheduled_end_date"
            )
        if cutoff and start and cutoff > start:
            raise ValidationError(
                "Booking cutoff date must be on or before the start date.",
                field_name="expedition_booking_cutoff_date"
            )

class ExpeditionUpdateRequestSchema(Schema):

    class Meta:
        unknown = EXCLUDE

    expedition_route_name = fields.Str(validate=validate.Length(min=5, max=200), load_default=None)
    expedition_geographical_location = fields.Str(validate=validate.Length(min=3, max=200), load_default=None)
    expedition_detailed_description = fields.Str(allow_none=True, load_default=None)
    expedition_difficulty_level = fields.Str(
        validate=validate.OneOf(["Easy", "Moderate", "Hard"]),
        load_default=None,
    )
    expedition_duration_in_days = fields.Int(
        validate=validate.Range(min=1, max=365),
        load_default=None,
    )
    expedition_price_per_person_inr = fields.Float(
        validate=validate.Range(min=0.0),
        load_default=None,
    )
    expedition_scheduled_start_date = fields.Date(allow_none=True, load_default=None)
    expedition_scheduled_end_date = fields.Date(allow_none=True, load_default=None)
    expedition_booking_cutoff_date = fields.Date(allow_none=True, load_default=None)
    total_participant_slots_capacity = fields.Int(
        validate=validate.Range(min=1, max=500),
        load_default=None,
    )
    expedition_cover_image_url = fields.Url(allow_none=True, load_default=None)
    expedition_meeting_point_address = fields.Str(
        allow_none=True,
        load_default=None,
        validate=validate.Length(max=300),
    )
    assigned_staff_leader_id = fields.Int(allow_none=True, load_default=None)
    current_expedition_lifecycle_status = fields.Str(
        validate=validate.OneOf(
            ["Pending", "Approved", "Open", "Closed", "Completed", "Cancelled"],
            error="Status must be one of: Pending, Approved, Open, Closed, Completed, Cancelled."
        ),
        load_default=None,
    )

class StaffExpeditionStatusUpdateRequestSchema(Schema):

    class Meta:
        unknown = EXCLUDE

    current_expedition_lifecycle_status = fields.Str(
        required=False,
        validate=validate.OneOf(
            ["Open", "Closed", "Completed"],
            error="Staff may only set status to: Open, Closed, or Completed."
        ),
        load_default=None,
    )
    available_participant_slots_remaining = fields.Int(
        required=False,
        validate=validate.Range(min=0, error="Available slots cannot be negative."),
        load_default=None,
    )

# check credentials

class NewParticipantBookingRequestSchema(Schema):

    class Meta:
        unknown = EXCLUDE

    booked_expedition_instance_id = fields.Int(
        required=True,
        validate=validate.Range(min=1, error="A valid expedition ID is required."),
    )
    number_of_participants_in_booking = fields.Int(
        required=False,
        validate=validate.Range(min=1, max=10, error="Bookings support 1–10 participants."),
        load_default=1,
    )
    trekker_special_requirements_note = fields.Str(
        required=False,
        allow_none=True,
        validate=validate.Length(max=500),
        load_default=None,
    )

class BookingCancellationRequestSchema(Schema):

    class Meta:
        unknown = EXCLUDE

    cancellation_reason_description = fields.Str(
        required=False,
        allow_none=True,
        validate=validate.Length(max=500, error="Cancellation reason must be under 500 characters."),
        load_default=None,
    )

# query db

class OpenExpeditionFilterQuerySchema(Schema):

    class Meta:
        unknown = EXCLUDE

    difficulty_level_filter = fields.Str(
        validate=validate.OneOf(["Easy", "Moderate", "Hard"]),
        load_default=None,
    )
    geographical_location_keyword = fields.Str(
        validate=validate.Length(max=100),
        load_default=None,
    )
    minimum_duration_days = fields.Int(
        validate=validate.Range(min=1),
        load_default=None,
    )
    maximum_duration_days = fields.Int(
        validate=validate.Range(min=1),
        load_default=None,
    )
    maximum_price_inr = fields.Float(
        validate=validate.Range(min=0.0),
        load_default=None,
    )
    result_page_number = fields.Int(
        validate=validate.Range(min=1),
        load_default=1,
    )
    results_per_page_limit = fields.Int(
        validate=validate.Range(min=1, max=50),
        load_default=12,
    )
