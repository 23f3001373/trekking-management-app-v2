

import enum
from datetime import datetime, timezone

from werkzeug.security import generate_password_hash, check_password_hash

from .extensions import database_extension as db

class UserPlatformRole(enum.Enum):

    ADMIN = "Admin"
    STAFF = "Staff"
    TREKKER = "Trekker"

class ExpeditionDifficultyLevel(enum.Enum):

    EASY = "Easy"
    MODERATE = "Moderate"
    HARD = "Hard"

class ExpeditionLifecycleStatus(enum.Enum):

    PENDING = "Pending"
    APPROVED = "Approved"
    OPEN = "Open"
    CLOSED = "Closed"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"

class BookingLifecycleStatus(enum.Enum):

    BOOKED = "Booked"
    CANCELLED = "Cancelled"
    COMPLETED = "Completed"

class PlatformUserAccount(db.Model):

    __tablename__ = "platform_user_accounts"

    user_account_id: int = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True,
    )

    user_full_name: str = db.Column(
        db.String(120),
        nullable=False,
    )

    user_email_address: str = db.Column(
        db.String(255),
        unique=True,
        nullable=False,
        index=True,
    )

    hashed_password_credential: str = db.Column(
        db.String(256),
        nullable=False,
    )

    # check credentials
    assigned_platform_role: UserPlatformRole = db.Column(
        db.Enum(UserPlatformRole, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=UserPlatformRole.TREKKER,
    )

    is_account_active: bool = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
    )

    is_account_blacklisted: bool = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
    )

    user_contact_phone_number: str = db.Column(
        db.String(20),
        nullable=True,
    )

    user_profile_bio_summary: str = db.Column(
        db.Text,
        nullable=True,
    )

    user_emergency_contact_name: str = db.Column(
        db.String(120),
        nullable=True,
    )

    user_emergency_contact_phone: str = db.Column(
        db.String(20),
        nullable=True,
    )

    account_created_at_utc: datetime = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    account_last_updated_at_utc: datetime = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    expeditions_led_as_staff = db.relationship(
        "TrekkingRouteExpedition",
        back_populates="assigned_staff_leader",
        foreign_keys="TrekkingRouteExpedition.assigned_staff_leader_id",
        lazy="select",
    )

    participant_booking_history = db.relationship(
        "ParticipantBookingRecord",
        back_populates="booking_owner_trekker",
        foreign_keys="ParticipantBookingRecord.booking_owner_trekker_id",
        lazy="dynamic",  # query db
        cascade="all, delete-orphan",
    )

    def set_hashed_password(self, raw_plaintext_password: str) -> None:

        # return response
        self.hashed_password_credential = generate_password_hash(raw_plaintext_password)

    def verify_submitted_password(self, submitted_plaintext_password: str) -> bool:

        return check_password_hash(self.hashed_password_credential, submitted_plaintext_password)

    def to_safe_public_dict(self) -> dict:

        return {
            "user_account_id": self.user_account_id,
            "user_full_name": self.user_full_name,
            "user_email_address": self.user_email_address,
            "assigned_platform_role": self.assigned_platform_role.value,
            "is_account_active": self.is_account_active,
            "is_account_blacklisted": self.is_account_blacklisted,
            "user_contact_phone_number": self.user_contact_phone_number,
            "user_profile_bio_summary": self.user_profile_bio_summary,
            "user_emergency_contact_name": self.user_emergency_contact_name,
            "user_emergency_contact_phone": self.user_emergency_contact_phone,
            "account_created_at_utc": (
                self.account_created_at_utc.isoformat() if self.account_created_at_utc else None
            ),
        }

    def __repr__(self) -> str:
        return (
            f"<PlatformUserAccount id={self.user_account_id} "
            f"email={self.user_email_address!r} "
            f"role={self.assigned_platform_role.value}>"
        )

class TrekkingRouteExpedition(db.Model):

    __tablename__ = "trekking_route_expeditions"

    trekking_route_expedition_id: int = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True,
    )

    expedition_route_name: str = db.Column(
        db.String(200),
        nullable=False,
    )

    expedition_geographical_location: str = db.Column(
        db.String(200),
        nullable=False,
    )

    expedition_detailed_description: str = db.Column(
        db.Text,
        nullable=True,
    )

    expedition_difficulty_level: ExpeditionDifficultyLevel = db.Column(
        db.Enum(ExpeditionDifficultyLevel, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )

    expedition_duration_in_days: int = db.Column(
        db.Integer,
        nullable=False,
    )

    expedition_price_per_person_inr: float = db.Column(
        db.Float,
        nullable=False,
        default=0.0,
    )

    expedition_scheduled_start_date: datetime = db.Column(
        db.Date,
        nullable=True,
    )

    expedition_scheduled_end_date: datetime = db.Column(
        db.Date,
        nullable=True,
    )

    expedition_booking_cutoff_date: datetime = db.Column(
        db.Date,
        nullable=True,
    )

    total_participant_slots_capacity: int = db.Column(
        db.Integer,
        nullable=False,
    )

    available_participant_slots_remaining: int = db.Column(
        db.Integer,
        nullable=False,
        comment=(
            "Live count of slots still open for booking. "
            "Decremented on BOOKED, incremented on CANCELLED. "
            "A CHECK constraint (enforced in application logic) keeps this >= 0."
        )
    )

    assigned_staff_leader_id: int = db.Column(
        db.Integer,
        db.ForeignKey(
            "platform_user_accounts.user_account_id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    assigned_staff_leader = db.relationship(
        "PlatformUserAccount",
        back_populates="expeditions_led_as_staff",
        foreign_keys=[assigned_staff_leader_id],
        lazy="joined",
    )

    current_expedition_lifecycle_status: ExpeditionLifecycleStatus = db.Column(
        db.Enum(ExpeditionLifecycleStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ExpeditionLifecycleStatus.PENDING,
    )

    expedition_cover_image_url: str = db.Column(
        db.String(500),
        nullable=True,
    )

    expedition_meeting_point_address: str = db.Column(
        db.String(300),
        nullable=True,
    )

    expedition_record_created_at_utc: datetime = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    expedition_record_last_updated_at_utc: datetime = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    registered_participant_bookings = db.relationship(
        "ParticipantBookingRecord",
        back_populates="booked_expedition_instance",
        foreign_keys="ParticipantBookingRecord.booked_expedition_instance_id",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    @property
    def is_currently_open_for_new_bookings(self) -> bool:

        return (
            self.current_expedition_lifecycle_status == ExpeditionLifecycleStatus.OPEN
            and self.available_participant_slots_remaining > 0
        )

    def to_public_summary_dict(self) -> dict:

        return {
            "trekking_route_expedition_id": self.trekking_route_expedition_id,
            "expedition_route_name": self.expedition_route_name,
            "expedition_geographical_location": self.expedition_geographical_location,
            "expedition_detailed_description": self.expedition_detailed_description,
            "expedition_difficulty_level": self.expedition_difficulty_level.value,
            "expedition_duration_in_days": self.expedition_duration_in_days,
            "expedition_price_per_person_inr": self.expedition_price_per_person_inr,
            "expedition_scheduled_start_date": (
                self.expedition_scheduled_start_date.isoformat()
                if self.expedition_scheduled_start_date else None
            ),
            "expedition_scheduled_end_date": (
                self.expedition_scheduled_end_date.isoformat()
                if self.expedition_scheduled_end_date else None
            ),
            "expedition_booking_cutoff_date": (
                self.expedition_booking_cutoff_date.isoformat()
                if self.expedition_booking_cutoff_date else None
            ),
            "total_participant_slots_capacity": self.total_participant_slots_capacity,
            "available_participant_slots_remaining": self.available_participant_slots_remaining,
            "current_expedition_lifecycle_status": self.current_expedition_lifecycle_status.value,
            "expedition_cover_image_url": self.expedition_cover_image_url,
            "expedition_meeting_point_address": self.expedition_meeting_point_address,
            "assigned_staff_leader_name": (
                self.assigned_staff_leader.user_full_name
                if self.assigned_staff_leader else "Unassigned"
            ),
            "is_currently_open_for_new_bookings": self.is_currently_open_for_new_bookings,
        }

    def __repr__(self) -> str:
        return (
            f"<TrekkingRouteExpedition id={self.trekking_route_expedition_id} "
            f"name={self.expedition_route_name!r} "
            f"status={self.current_expedition_lifecycle_status.value}>"
        )

class ParticipantBookingRecord(db.Model):

    __tablename__ = "participant_booking_records"

    __table_args__ = (
        db.UniqueConstraint(
            "booking_owner_trekker_id",
            "booked_expedition_instance_id",
            name="uq_one_booking_per_trekker_per_expedition"
        ),
    )

    participant_booking_record_id: int = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True,
    )

    booking_owner_trekker_id: int = db.Column(
        db.Integer,
        db.ForeignKey(
            "platform_user_accounts.user_account_id",
            ondelete="CASCADE"
        ),
        nullable=False,
        index=True,
    )

    booked_expedition_instance_id: int = db.Column(
        db.Integer,
        db.ForeignKey(
            "trekking_route_expeditions.trekking_route_expedition_id",
            ondelete="CASCADE"
        ),
        nullable=False,
        index=True,
    )

    current_booking_lifecycle_status: BookingLifecycleStatus = db.Column(
        db.Enum(BookingLifecycleStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=BookingLifecycleStatus.BOOKED,
    )

    booking_confirmation_reference_code: str = db.Column(
        db.String(50),
        unique=True,
        nullable=True,
    )

    number_of_participants_in_booking: int = db.Column(
        db.Integer,
        nullable=False,
        default=1,
    )

    trekker_special_requirements_note: str = db.Column(
        db.Text,
        nullable=True,
    )

    cancellation_reason_description: str = db.Column(
        db.String(500),
        nullable=True,
    )

    booking_placed_at_utc: datetime = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    booking_last_status_changed_at_utc: datetime = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    booking_owner_trekker = db.relationship(
        "PlatformUserAccount",
        back_populates="participant_booking_history",
        foreign_keys=[booking_owner_trekker_id],
        lazy="joined",
    )

    booked_expedition_instance = db.relationship(
        "TrekkingRouteExpedition",
        back_populates="registered_participant_bookings",
        foreign_keys=[booked_expedition_instance_id],
        lazy="joined",
    )

    def to_full_detail_dict(self) -> dict:

        expedition = self.booked_expedition_instance
        return {
            "participant_booking_record_id": self.participant_booking_record_id,
            "booking_confirmation_reference_code": self.booking_confirmation_reference_code,
            "current_booking_lifecycle_status": self.current_booking_lifecycle_status.value,
            "number_of_participants_in_booking": self.number_of_participants_in_booking,
            "trekker_special_requirements_note": self.trekker_special_requirements_note,
            "cancellation_reason_description": self.cancellation_reason_description,
            "booking_placed_at_utc": (
                self.booking_placed_at_utc.isoformat() if self.booking_placed_at_utc else None
            ),
            "booking_last_status_changed_at_utc": (
                self.booking_last_status_changed_at_utc.isoformat()
                if self.booking_last_status_changed_at_utc else None
            ),
            "expedition_route_name": expedition.expedition_route_name if expedition else None,
            "expedition_geographical_location": (
                expedition.expedition_geographical_location if expedition else None
            ),
            "expedition_difficulty_level": (
                expedition.expedition_difficulty_level.value if expedition else None
            ),
            "expedition_scheduled_start_date": (
                expedition.expedition_scheduled_start_date.isoformat()
                if expedition and expedition.expedition_scheduled_start_date else None
            ),
            "expedition_scheduled_end_date": (
                expedition.expedition_scheduled_end_date.isoformat()
                if expedition and expedition.expedition_scheduled_end_date else None
            ),
            "expedition_price_per_person_inr": (
                expedition.expedition_price_per_person_inr if expedition else None
            ),
        }

    def __repr__(self) -> str:
        return (
            f"<ParticipantBookingRecord id={self.participant_booking_record_id} "
            f"trekker_id={self.booking_owner_trekker_id} "
            f"expedition_id={self.booked_expedition_instance_id} "
            f"status={self.current_booking_lifecycle_status.value}>"
        )

def initialise_database_and_seed_admin(flask_application_instance) -> None:

    with flask_application_instance.app_context():

        db.create_all()
        flask_application_instance.logger.info(
            "Database schema synchronisation complete via db.create_all()."
        )

        existing_admin_account = PlatformUserAccount.query.filter_by(
            assigned_platform_role=UserPlatformRole.ADMIN
        ).first()

        if existing_admin_account is not None:
            flask_application_instance.logger.info(
                f"Admin account already exists (email: {existing_admin_account.user_email_address}). "
                "Skipping seed insertion."
            )
            return

        config = flask_application_instance.config

        seeded_admin_account = PlatformUserAccount(
            user_full_name=config.get("ADMIN_SEED_FULL_NAME", "Platform Administrator"),
            user_email_address=config["ADMIN_SEED_EMAIL"],
            assigned_platform_role=UserPlatformRole.ADMIN,
            is_account_active=True,
            is_account_blacklisted=False,
        )

        seeded_admin_account.set_hashed_password(config["ADMIN_SEED_PASSWORD"])

        db.session.add(seeded_admin_account)
        db.session.commit()

        flask_application_instance.logger.warning(
            f"SEED: Admin account created with email '{config['ADMIN_SEED_EMAIL']}'. "
            "IMPORTANT — Change this password immediately in a production environment!"
        )
