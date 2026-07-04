"""
models.py — SQLAlchemy ORM Models & Database Bootstrap
=======================================================
This module defines the entire relational schema for the Trekking Management
Platform V2. Three first-class domain entities are modelled here:

  1. PlatformUserAccount  — unified user table covering Admin, Staff, Trekker roles.
  2. TrekkingRouteExpedition — every trekking route offered on the platform.
  3. ParticipantBookingRecord — a join between a Trekker and an Expedition.

Design Principles Followed
---------------------------
* SINGLE SOURCE OF TRUTH: All column definitions, constraints, and relationship
  configurations live here. No raw SQL DDL scripts exist; the schema emerges
  entirely from SQLAlchemy model classes.
* SELF-DOCUMENTING NAMING: Column and relationship names are verbose but
  unambiguous — a reader unfamiliar with the codebase should be able to infer
  business rules from names alone without reading external documentation.
* PROGRAMMATIC SEEDING: The `initialise_database_and_seed_admin()` function
  at the bottom of this file handles both `db.create_all()` and the idempotent
  insertion of the first Admin account, satisfying the requirement that the
  database is NEVER created manually.
* DEFENSIVE DEFAULTS: Every nullable=False column has a server_default or
  Python-level default so that accidental blank inserts fail loudly.

Dependencies
------------
  flask_sqlalchemy  — SQLAlchemy integration for Flask (ORM, session, metadata)
  werkzeug.security — PBKDF2-HMAC password hashing (no plaintext ever stored)
  datetime, enum   — stdlib; used for timestamps and role/status constants
"""

import enum
from datetime import datetime, timezone

from werkzeug.security import generate_password_hash, check_password_hash

from .extensions import database_extension as db


# =========================================================================== #
#  SECTION 1 — Enumeration Types                                               #
#  Using Python `enum.Enum` instead of plain string constants gives us:        #
#    • Database-level CHECK constraints (via SQLAlchemy's Enum column type)     #
#    • IDE auto-complete and static type checking                               #
#    • A single place to add/rename roles or statuses without hunting strings   #
# =========================================================================== #

class UserPlatformRole(enum.Enum):
    """
    Defines the three distinct actor types on the platform.

    ADMIN  — full system control: create/edit/delete treks, manage users,
             view all reports, and assign staff to expeditions.
    STAFF  — operational role: update expedition slot counts, change
             expedition status (Open/Closed/Completed), and view participant
             lists for assigned expeditions only.
    TREKKER — end-user role: self-register, browse open expeditions, make
              bookings, download booking history as CSV, and update own profile.
    """
    ADMIN = "Admin"
    STAFF = "Staff"
    TREKKER = "Trekker"


class ExpeditionDifficultyLevel(enum.Enum):
    """
    Categorises a trekking route's physical and technical challenge level.

    EASY     — suitable for beginners; flat or gently sloped terrain.
    MODERATE — requires reasonable fitness; some steep sections or altitude.
    HARD     — demands advanced fitness, acclimatisation, and experience.

    The difficulty level is a key filter criterion on the Trekker dashboard,
    allowing users to search for expeditions within their capability range.
    """
    EASY = "Easy"
    MODERATE = "Moderate"
    HARD = "Hard"


class ExpeditionLifecycleStatus(enum.Enum):
    """
    Models the full lifecycle of a TrekkingRouteExpedition from creation
    to completion. Valid transitions:

      PENDING ──► APPROVED ──► OPEN ──► CLOSED ──► COMPLETED
                                   └──► CANCELLED (admin override)

    PENDING   — admin has created the route record; awaiting review.
    APPROVED  — admin has reviewed and approved; awaiting slot publication.
    OPEN      — accepting bookings from Trekkers.
    CLOSED    — no new bookings accepted (slots full or admin decision).
    COMPLETED — expedition has concluded; all participant records finalised.
    CANCELLED — expedition was called off before starting.
    """
    PENDING = "Pending"
    APPROVED = "Approved"
    OPEN = "Open"
    CLOSED = "Closed"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"


class BookingLifecycleStatus(enum.Enum):
    """
    Tracks the state of an individual participant's booking record.

    BOOKED    — confirmed reservation; a slot is held for this trekker.
    CANCELLED — trekker or admin cancelled; the slot is released back to
                the expedition's available_participant_slots count.
    COMPLETED — the expedition finished and the trekker participated.
    """
    BOOKED = "Booked"
    CANCELLED = "Cancelled"
    COMPLETED = "Completed"


# =========================================================================== #
#  SECTION 2 — ORM Model: PlatformUserAccount                                  #
#  Represents every human actor on the system in a single unified table.       #
#  Role-based access control is enforced by checking the `assigned_platform_   #
#  role` field on each authenticated request.                                  #
# =========================================================================== #

class PlatformUserAccount(db.Model):
    """
    PlatformUserAccount — Unified user entity for all roles.

    A single-table design is chosen over a table-per-role hierarchy because:
      - The three roles share the vast majority of attributes (name, email,
        password, timestamps, active/blacklist flags).
      - Role-specific data (e.g., which expeditions are assigned to a staff
        member) is handled via relationships rather than extra columns.
      - Querying "all users" for admin dashboards is a simple SELECT * rather
        than a UNION across multiple tables.

    The `is_account_blacklisted` flag provides a soft-ban mechanism — the
    account record is preserved for audit history but login is denied.
    """

    __tablename__ = "platform_user_accounts"

    # ------------------------------------------------------------------ #
    # Primary Key                                                          #
    # ------------------------------------------------------------------ #
    user_account_id: int = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True,
    )

    # ------------------------------------------------------------------ #
    # Identity & Contact                                                   #
    # ------------------------------------------------------------------ #
    user_full_name: str = db.Column(
        db.String(120),
        nullable=False,
    )

    user_email_address: str = db.Column(
        db.String(255),
        unique=True,
        nullable=False,
        index=True,  # Indexed for fast lookup during login credential checks.
    )

    # Stores the PBKDF2-HMAC-SHA256 hash produced by werkzeug.
    # The raw password is NEVER persisted to the database under any circumstance.
    hashed_password_credential: str = db.Column(
        db.String(256),
        nullable=False,
    )

    # ------------------------------------------------------------------ #
    # Role & Status Flags                                                  #
    # ------------------------------------------------------------------ #
    assigned_platform_role: UserPlatformRole = db.Column(
        db.Enum(UserPlatformRole),
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

    # ------------------------------------------------------------------ #
    # Profile Attributes (optional, enriches Trekker's public profile)    #
    # ------------------------------------------------------------------ #
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

    # ------------------------------------------------------------------ #
    # Audit Timestamps                                                     #
    # ------------------------------------------------------------------ #
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

    # ------------------------------------------------------------------ #
    # Relationships                                                         #
    # ------------------------------------------------------------------ #

    # A Staff member may be assigned to lead multiple expeditions.
    # `back_populates` keeps both sides of the relationship in sync.
    expeditions_led_as_staff = db.relationship(
        "TrekkingRouteExpedition",
        back_populates="assigned_staff_leader",
        foreign_keys="TrekkingRouteExpedition.assigned_staff_leader_id",
        lazy="select",
    )

    # A Trekker may hold multiple booking records (past and present).
    participant_booking_history = db.relationship(
        "ParticipantBookingRecord",
        back_populates="booking_owner_trekker",
        foreign_keys="ParticipantBookingRecord.booking_owner_trekker_id",
        lazy="dynamic",  # 'dynamic' returns a query object for large collections.
        cascade="all, delete-orphan",
    )

    # ------------------------------------------------------------------ #
    # Password Utility Methods                                             #
    # ------------------------------------------------------------------ #

    def set_hashed_password(self, raw_plaintext_password: str) -> None:
        """
        Hashes the provided plaintext password using Werkzeug's PBKDF2-HMAC-SHA256
        implementation and stores the result in `hashed_password_credential`.

        This method is the ONLY sanctioned way to set or change a password.
        It is called during user creation and password-reset workflows.

        Args:
            raw_plaintext_password: The user-supplied password in cleartext.
                                    It is hashed immediately and never assigned
                                    to any attribute of this model object.
        """
        # `generate_password_hash` automatically prepends the algorithm identifier
        # and a random salt to the hash string, making each hash unique even for
        # identical passwords. No manual salting is needed.
        self.hashed_password_credential = generate_password_hash(raw_plaintext_password)

    def verify_submitted_password(self, submitted_plaintext_password: str) -> bool:
        """
        Verifies whether a submitted plaintext password matches the stored hash.

        Returns True only if the candidate password, when hashed with the same
        algorithm and salt extracted from `hashed_password_credential`, produces
        the same hash. A timing-safe comparison prevents timing-oracle attacks.

        Args:
            submitted_plaintext_password: The candidate password provided at login.

        Returns:
            bool: True if the password is correct, False otherwise.
        """
        return check_password_hash(self.hashed_password_credential, submitted_plaintext_password)

    def to_safe_public_dict(self) -> dict:
        """
        Serialises this user account to a dictionary safe for API responses.

        Critically, `hashed_password_credential` is EXCLUDED. This method is
        called by route handlers when returning user data to the client, ensuring
        the password hash can never leak through a JSON response by accident.

        Returns:
            dict: A JSON-serialisable representation of this user account.
        """
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


# =========================================================================== #
#  SECTION 3 — ORM Model: TrekkingRouteExpedition                              #
#  Each row represents ONE scheduled instance of a trekking route.            #
#  The same physical route (e.g., "Himalayan Base Camp") can have multiple     #
#  expedition rows with different dates, staff, and slot counts.               #
# =========================================================================== #

class TrekkingRouteExpedition(db.Model):
    """
    TrekkingRouteExpedition — A fully scheduled and staffed trek event.

    This model captures both the static route description (name, location,
    difficulty) and the dynamic event parameters (dates, slots, staff assignment,
    lifecycle status). Splitting these into separate "Route" and "Event" tables
    would be over-engineering for the current scale; a single table with
    nullable date fields is sufficient and easier to query from the SPA.

    Slot Management Logic
    ----------------------
    `total_participant_slots_capacity` is set once by the Admin at creation.
    `available_participant_slots_remaining` is decremented by 1 on each
    successful BOOKED booking and incremented by 1 on each CANCELLED booking.
    A booking attempt when `available_participant_slots_remaining == 0` is
    rejected with HTTP 409 Conflict (overbooking prevention).
    """

    __tablename__ = "trekking_route_expeditions"

    # ------------------------------------------------------------------ #
    # Primary Key                                                          #
    # ------------------------------------------------------------------ #
    trekking_route_expedition_id: int = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True,
    )

    # ------------------------------------------------------------------ #
    # Route Description                                                    #
    # ------------------------------------------------------------------ #
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
        db.Enum(ExpeditionDifficultyLevel),
        nullable=False,
    )

    # Duration is stored in whole days for simplicity.
    expedition_duration_in_days: int = db.Column(
        db.Integer,
        nullable=False,
    )

    # Price per person in Indian Rupees (stored as integer paise for precision).
    expedition_price_per_person_inr: float = db.Column(
        db.Float,
        nullable=False,
        default=0.0,
    )

    # ------------------------------------------------------------------ #
    # Scheduling                                                           #
    # ------------------------------------------------------------------ #
    expedition_scheduled_start_date: datetime = db.Column(
        db.Date,
        nullable=True,
    )

    expedition_scheduled_end_date: datetime = db.Column(
        db.Date,
        nullable=True,
    )

    # Deadline after which new bookings are no longer accepted.
    expedition_booking_cutoff_date: datetime = db.Column(
        db.Date,
        nullable=True,
    )

    # ------------------------------------------------------------------ #
    # Slot / Capacity Management                                           #
    # ------------------------------------------------------------------ #
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

    # ------------------------------------------------------------------ #
    # Staff Assignment                                                      #
    # ------------------------------------------------------------------ #
    assigned_staff_leader_id: int = db.Column(
        db.Integer,
        db.ForeignKey(
            "platform_user_accounts.user_account_id",
            ondelete="SET NULL",   # If the staff account is deleted, nullify rather than cascade.
        ),
        nullable=True,
        index=True,
    )

    assigned_staff_leader = db.relationship(
        "PlatformUserAccount",
        back_populates="expeditions_led_as_staff",
        foreign_keys=[assigned_staff_leader_id],
        lazy="joined",  # Eagerly load the staff leader name in the same query.
    )

    # ------------------------------------------------------------------ #
    # Lifecycle Status                                                      #
    # ------------------------------------------------------------------ #
    current_expedition_lifecycle_status: ExpeditionLifecycleStatus = db.Column(
        db.Enum(ExpeditionLifecycleStatus),
        nullable=False,
        default=ExpeditionLifecycleStatus.PENDING,
    )

    # ------------------------------------------------------------------ #
    # Route Media                                                          #
    # ------------------------------------------------------------------ #
    expedition_cover_image_url: str = db.Column(
        db.String(500),
        nullable=True,
    )

    expedition_meeting_point_address: str = db.Column(
        db.String(300),
        nullable=True,
    )

    # ------------------------------------------------------------------ #
    # Audit Timestamps                                                     #
    # ------------------------------------------------------------------ #
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

    # ------------------------------------------------------------------ #
    # Relationships                                                         #
    # ------------------------------------------------------------------ #

    # One expedition can have many booking records from different trekkers.
    registered_participant_bookings = db.relationship(
        "ParticipantBookingRecord",
        back_populates="booked_expedition_instance",
        foreign_keys="ParticipantBookingRecord.booked_expedition_instance_id",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    # ------------------------------------------------------------------ #
    # Business Logic Helper Methods                                        #
    # ------------------------------------------------------------------ #

    @property
    def is_currently_open_for_new_bookings(self) -> bool:
        """
        Computed property: returns True only when the expedition can still
        accept new participant bookings.

        Two conditions must BOTH hold:
          1. The lifecycle status is OPEN (admin-controlled gate).
          2. At least one participant slot remains available.

        This property is the authoritative check used in the booking route
        before any slot decrement is attempted.
        """
        return (
            self.current_expedition_lifecycle_status == ExpeditionLifecycleStatus.OPEN
            and self.available_participant_slots_remaining > 0
        )

    def to_public_summary_dict(self) -> dict:
        """
        Returns a JSON-serialisable summary of this expedition for the
        Trekker's explore page and the Redis-cached trek listing endpoint.

        Excludes internal audit fields to keep the payload lightweight.
        The staff leader's name is included (via the eagerly loaded
        `assigned_staff_leader` relationship) so the client doesn't need
        a second API call just to display who's leading the trek.
        """
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


# =========================================================================== #
#  SECTION 4 — ORM Model: ParticipantBookingRecord                             #
#  The associative entity linking a PlatformUserAccount (Trekker role) to      #
#  a TrekkingRouteExpedition, with full booking lifecycle tracking.             #
# =========================================================================== #

class ParticipantBookingRecord(db.Model):
    """
    ParticipantBookingRecord — A trekker's reservation for a specific expedition.

    This is the central transactional table of the application. Each row
    represents one human's commitment to attend one specific expedition.

    Uniqueness Constraint
    ----------------------
    A trekker may NOT book the same expedition twice. The composite unique
    constraint on (booking_owner_trekker_id, booked_expedition_instance_id)
    enforces this at the database level, providing a safety net even if the
    application-level duplicate-check is somehow bypassed.

    Slot Lifecycle Contract
    ------------------------
    When a row is INSERTED with status=BOOKED:
      → expedition.available_participant_slots_remaining -= 1

    When a row's status is UPDATED to CANCELLED:
      → expedition.available_participant_slots_remaining += 1

    When a row's status is UPDATED to COMPLETED:
      → slots are NOT re-released (the trek already happened).

    These mutations happen in the trekker_routes.py booking handler within
    a single database transaction to prevent race conditions.
    """

    __tablename__ = "participant_booking_records"

    # Composite unique constraint: prevents a trekker from double-booking.
    __table_args__ = (
        db.UniqueConstraint(
            "booking_owner_trekker_id",
            "booked_expedition_instance_id",
            name="uq_one_booking_per_trekker_per_expedition"
        ),
    )

    # ------------------------------------------------------------------ #
    # Primary Key                                                          #
    # ------------------------------------------------------------------ #
    participant_booking_record_id: int = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True,
    )

    # ------------------------------------------------------------------ #
    # Foreign Keys — the two sides of this M:M junction                   #
    # ------------------------------------------------------------------ #
    booking_owner_trekker_id: int = db.Column(
        db.Integer,
        db.ForeignKey(
            "platform_user_accounts.user_account_id",
            ondelete="CASCADE"  # Delete booking records if the user account is deleted.
        ),
        nullable=False,
        index=True,
    )

    booked_expedition_instance_id: int = db.Column(
        db.Integer,
        db.ForeignKey(
            "trekking_route_expeditions.trekking_route_expedition_id",
            ondelete="CASCADE"  # Delete bookings if the parent expedition is deleted.
        ),
        nullable=False,
        index=True,
    )

    # ------------------------------------------------------------------ #
    # Booking State & Metadata                                             #
    # ------------------------------------------------------------------ #
    current_booking_lifecycle_status: BookingLifecycleStatus = db.Column(
        db.Enum(BookingLifecycleStatus),
        nullable=False,
        default=BookingLifecycleStatus.BOOKED,
    )

    # A human-readable confirmation code displayed to the trekker after booking.
    # Formatted as "TRK-{expedition_id}-{trekker_id}-{YYYYMMDD}" in the route handler.
    booking_confirmation_reference_code: str = db.Column(
        db.String(50),
        unique=True,
        nullable=True,
    )

    # Number of participants included in this booking. Defaults to 1 (individual),
    # but could be extended to group bookings in a future version.
    number_of_participants_in_booking: int = db.Column(
        db.Integer,
        nullable=False,
        default=1,
    )

    # Optional note from the trekker (dietary restrictions, accessibility needs, etc.)
    trekker_special_requirements_note: str = db.Column(
        db.Text,
        nullable=True,
    )

    # Record of why a booking was cancelled — populated by the cancellation handler.
    cancellation_reason_description: str = db.Column(
        db.String(500),
        nullable=True,
    )

    # ------------------------------------------------------------------ #
    # Audit Timestamps                                                     #
    # ------------------------------------------------------------------ #
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

    # ------------------------------------------------------------------ #
    # Relationships                                                         #
    # ------------------------------------------------------------------ #

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

    # ------------------------------------------------------------------ #
    # Serialisation Helper                                                  #
    # ------------------------------------------------------------------ #

    def to_full_detail_dict(self) -> dict:
        """
        Returns a complete, JSON-serialisable representation of this booking
        record, including denormalised fields from the related expedition and
        trekker for convenient display on the Trekker's booking history page
        and for CSV export by the Celery async task.

        The denormalisation here is intentional: it makes the API response
        self-contained and avoids N+1 query issues when rendering a list of
        bookings (since `lazy="joined"` already loaded both relationships).
        """
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
            # Denormalised expedition fields for self-contained responses:
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


# =========================================================================== #
#  SECTION 5 — Database Bootstrap & Admin Seeding                              #
#  This is the ONLY place where `db.create_all()` is ever called.              #
#  Manual table creation or raw DDL scripts are strictly forbidden.             #
# =========================================================================== #

def initialise_database_and_seed_admin(flask_application_instance) -> None:
    """
    Programmatically initialises the database schema and seeds the Admin account.

    This function is called ONCE from the Flask app factory (`__init__.py`) during
    application startup. It is idempotent: running it multiple times on an already
    initialised database is safe — it will neither duplicate tables nor insert a
    second Admin account.

    Step-by-Step Execution
    -----------------------
    1. `db.create_all()` — Inspects all ORM model classes registered with the
       SQLAlchemy metadata and issues CREATE TABLE IF NOT EXISTS for each one.
       This means tables that already exist are left completely untouched.

    2. Admin existence check — Queries for any existing ADMIN-role user. If one
       is found, seeding is skipped. This prevents the seed from overwriting a
       password that was changed post-deployment.

    3. Admin insertion — If no Admin exists, creates one using credentials from
       the application's config (which in production come from env vars). The
       password is hashed via `set_hashed_password` — the plaintext is never
       written to the DB.

    Args:
        flask_application_instance: The fully configured Flask app object.
                                    Needed to push an application context so
                                    SQLAlchemy can access the database URI.
    """
    # Push a new application context so that `db.session` and `db.create_all()`
    # have access to `current_app.config` (which holds the DB URI, etc.).
    # Without this context push, calling db functions outside a request cycle
    # would raise a `RuntimeError: Working outside of application context`.
    with flask_application_instance.app_context():

        # ---- Step 1: Create all tables that don't yet exist. ---- #
        db.create_all()
        flask_application_instance.logger.info(
            "Database schema synchronisation complete via db.create_all()."
        )

        # ---- Step 2: Check whether an Admin account already exists. ---- #
        existing_admin_account = PlatformUserAccount.query.filter_by(
            assigned_platform_role=UserPlatformRole.ADMIN
        ).first()

        if existing_admin_account is not None:
            # An admin already exists — do nothing. This branch is hit on every
            # server restart after the very first boot, making the seed idempotent.
            flask_application_instance.logger.info(
                f"Admin account already exists (email: {existing_admin_account.user_email_address}). "
                "Skipping seed insertion."
            )
            return

        # ---- Step 3: No Admin found — create and persist the seed account. ---- #
        config = flask_application_instance.config

        seeded_admin_account = PlatformUserAccount(
            user_full_name=config.get("ADMIN_SEED_FULL_NAME", "Platform Administrator"),
            user_email_address=config["ADMIN_SEED_EMAIL"],
            assigned_platform_role=UserPlatformRole.ADMIN,
            is_account_active=True,
            is_account_blacklisted=False,
        )

        # Hash the seed password — the plaintext from config is NEVER stored.
        seeded_admin_account.set_hashed_password(config["ADMIN_SEED_PASSWORD"])

        db.session.add(seeded_admin_account)
        db.session.commit()

        flask_application_instance.logger.warning(
            f"SEED: Admin account created with email '{config['ADMIN_SEED_EMAIL']}'. "
            "IMPORTANT — Change this password immediately in a production environment!"
        )
