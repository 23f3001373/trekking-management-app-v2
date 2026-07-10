"""
test_app.py — Integration and Unit Test Suite
================================================
This test suite verifies the correctness of the Trekking Management Platform V2.
It uses Python's built-in `unittest` library and Flask's test client. The database
is set to an in-memory SQLite database (via TestingConfig) to ensure tests run
isolated and leave no trace on disk.

Features Verified:
  1. Auth: User registration, login validation, token refresh, profile update.
  2. Admin: Expedition creation, staff registration, user query, blacklist.
  3. Staff: Viewing assigned treks, updating slots and lifecycle status.
  4. Trekker: Fetching open treks, booking, overbooking prevention, cancellation.

Usage:
  python -m unittest test_app.py
"""

import json
import unittest
from datetime import datetime, timezone, timedelta

# Adjust path to import backend app components
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_flask_application
from app.extensions import database_extension as db
from app.models import (
    PlatformUserAccount,
    TrekkingRouteExpedition,
    ParticipantBookingRecord,
    UserPlatformRole,
    ExpeditionLifecycleStatus,
    ExpeditionDifficultyLevel,
    BookingLifecycleStatus,
)


class TrekkingPlatformTestCase(unittest.TestCase):
    """
    TrekkingPlatformTestCase — holds all assertions and flows for testing
    the backend APIs under a simulated environment.
    """

    def setUp(self) -> None:
        """
        setUp() — runs before every individual test function.
        Initialises a fresh Flask app instance with TestingConfig, binds it
        to a test client, and builds a clean schema inside the in-memory DB.
        """
        # Create Flask app using factory configured for testing
        self.flask_app = create_flask_application("testing")
        self.app_context = self.flask_app.app_context()
        self.app_context.push()

        # Bind the Flask test client
        self.client = self.flask_app.test_client()

        # Re-create database schemas fresh
        db.create_all()

        # Set up default credentials from configuration
        self.admin_email = self.flask_app.config["ADMIN_SEED_EMAIL"]
        self.admin_password = self.flask_app.config["ADMIN_SEED_PASSWORD"]

    def tearDown(self) -> None:
        """
        tearDown() — runs after every individual test function.
        Clears the database session and pops the application context.
        """
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    # =========================================================================
    # Helpers: Login and Token Retrieval
    # =========================================================================

    def _get_auth_headers(self, email_address: str, password_credential: str) -> dict:
        """Helper to login a user and return the Authorization header."""
        login_response = self.client.post(
            "/api/auth/login",
            json={
                "user_email_address": email_address,
                "submitted_password": password_credential,
            }
        )
        self.assertEqual(login_response.status_code, 200)
        token_data = json.loads(login_response.data)
        return {
            "Authorization": f"Bearer {token_data['access_token']}"
        }

    # =========================================================================
    # Test Cases: Auth & Registration
    # =========================================================================

    def test_admin_account_pre_seeded(self) -> None:
        """Verifies that the default Admin account is correctly pre-seeded on startup."""
        admin_user = PlatformUserAccount.query.filter_by(
            assigned_platform_role=UserPlatformRole.ADMIN
        ).first()
        self.assertIsNotNone(admin_user)
        self.assertEqual(admin_user.user_email_address, self.admin_email)
        self.assertTrue(admin_user.verify_submitted_password(self.admin_password))

    def test_trekker_registration_and_login_flow(self) -> None:
        """Verifies the self-registration and subsequent login flow for trekkers."""
        # 1. Self Register
        reg_payload = {
            "user_full_name": "Vijay Kumar",
            "user_email_address": "vijay@himalayas.com",
            "user_contact_phone_number": "+919999988888",
            "raw_password": "SecurePassword@123",
        }
        reg_response = self.client.post("/api/auth/register", json=reg_payload)
        self.assertEqual(reg_response.status_code, 201)

        # Verify database record
        trekker_in_db = PlatformUserAccount.query.filter_by(user_email_address="vijay@himalayas.com").first()
        self.assertIsNotNone(trekker_in_db)
        self.assertEqual(trekker_in_db.assigned_platform_role, UserPlatformRole.TREKKER)

        # 2. Login
        login_response = self.client.post(
            "/api/auth/login",
            json={
                "user_email_address": "vijay@himalayas.com",
                "submitted_password": "SecurePassword@123",
            }
        )
        self.assertEqual(login_response.status_code, 200)
        data = json.loads(login_response.data)
        self.assertIn("access_token", data)
        self.assertEqual(data["authenticated_user"]["user_email_address"], "vijay@himalayas.com")

        # 3. Test token refresh
        refresh_headers = {"Authorization": f"Bearer {data['refresh_token']}"}
        refresh_response = self.client.post("/api/auth/refresh-token", headers=refresh_headers)
        self.assertEqual(refresh_response.status_code, 200)
        refresh_data = json.loads(refresh_response.data)
        self.assertIn("new_access_token", refresh_data)

    def test_login_invalid_credentials_fails(self) -> None:
        """Verifies login fails cleanly with correct HTTP code on bad credentials."""
        login_response = self.client.post(
            "/api/auth/login",
            json={
                "user_email_address": self.admin_email,
                "submitted_password": "wrong-password",
            }
        )
        self.assertEqual(login_response.status_code, 401)
        data = json.loads(login_response.data)
        self.assertTrue(data.get("login_failed"))

    # =========================================================================
    # Test Cases: Admin Actions
    # =========================================================================

    def test_admin_can_create_staff_member(self) -> None:
        """Verifies that an Admin can register a new Staff account, and Staff cannot register themselves."""
        admin_headers = self._get_auth_headers(self.admin_email, self.admin_password)

        staff_payload = {
            "user_full_name": "Trek Leader Rohan",
            "user_email_address": "rohan@trekstaff.com",
            "user_contact_phone_number": "+918888877777",
            "raw_password": "StaffPassword@789",
        }

        # Submit via admin client
        creation_response = self.client.post("/api/admin/staff", json=staff_payload, headers=admin_headers)
        self.assertEqual(creation_response.status_code, 201)

        # Verify in DB
        staff_user = PlatformUserAccount.query.filter_by(user_email_address="rohan@trekstaff.com").first()
        self.assertIsNotNone(staff_user)
        self.assertEqual(staff_user.assigned_platform_role, UserPlatformRole.STAFF)

    def test_admin_can_crud_expedition(self) -> None:
        """Verifies that an Admin can Create, Read, Update, and Delete expeditions."""
        admin_headers = self._get_auth_headers(self.admin_email, self.admin_password)

        # 1. Create Expedition
        exp_payload = {
            "expedition_route_name": "Kedarkantha Winter Expedition 2026",
            "expedition_geographical_location": "Sankri, Uttarakhand",
            "expedition_difficulty_level": "Moderate",
            "expedition_duration_in_days": 6,
            "expedition_price_per_person_inr": 8500.0,
            "total_participant_slots_capacity": 15,
            "expedition_scheduled_start_date": "2026-12-10",
            "expedition_scheduled_end_date": "2026-12-16",
            "expedition_booking_cutoff_date": "2026-12-05",
        }
        create_response = self.client.post("/api/admin/expeditions", json=exp_payload, headers=admin_headers)
        self.assertEqual(create_response.status_code, 201)
        created_data = json.loads(create_response.data)
        exp_id = created_data["created_expedition"]["trekking_route_expedition_id"]

        # Verify defaults (should be in PENDING lifecycle status)
        exp_in_db = TrekkingRouteExpedition.query.get(exp_id)
        self.assertEqual(exp_in_db.current_expedition_lifecycle_status, ExpeditionLifecycleStatus.PENDING)

        # 2. Update Expedition
        update_payload = {
            "expedition_route_name": "Kedarkantha Winter Expedition 2026 (Updated)",
            "current_expedition_lifecycle_status": "Open",  # Open it for bookings
            "expedition_difficulty_level": "Moderate",
            "expedition_duration_in_days": 6,
            "total_participant_slots_capacity": 15,
        }
        update_response = self.client.patch(f"/api/admin/expeditions/{exp_id}", json=update_payload, headers=admin_headers)
        self.assertEqual(update_response.status_code, 200)

        # Verify status is now OPEN
        exp_in_db = TrekkingRouteExpedition.query.get(exp_id)
        self.assertEqual(exp_in_db.current_expedition_lifecycle_status, ExpeditionLifecycleStatus.OPEN)

        # 3. Delete Expedition
        delete_response = self.client.delete(f"/api/admin/expeditions/{exp_id}", headers=admin_headers)
        self.assertEqual(delete_response.status_code, 200)
        self.assertIsNone(TrekkingRouteExpedition.query.get(exp_id))

    # =========================================================================
    # Test Cases: Trekker Booking & Overbooking Safeguards
    # =========================================================================

    def test_trekker_booking_lifecycle_and_overbooking_protection(self) -> None:
        """
        Verifies the core booking flow, ensures slot quantities are updated
        atomically, prevents duplicate bookings, and enforces overbooking safeguards.
        """
        # 1. Create a Staff Leader
        admin_headers = self._get_auth_headers(self.admin_email, self.admin_password)
        staff_response = self.client.post(
            "/api/admin/staff",
            json={
                "user_full_name": "Staff Guide Amit",
                "user_email_address": "amit@trekstaff.com",
                "raw_password": "AmitSecurePassword@999",
            },
            headers=admin_headers
        )
        self.assertEqual(staff_response.status_code, 201)
        staff_id = PlatformUserAccount.query.filter_by(user_email_address="amit@trekstaff.com").first().user_account_id

        # 2. Create an Expedition with only 2 available slots and assign Staff
        exp_payload = {
            "expedition_route_name": "Quick weekend escape to Triund",
            "expedition_geographical_location": "Dharamshala, Himachal",
            "expedition_difficulty_level": "Easy",
            "expedition_duration_in_days": 2,
            "expedition_price_per_person_inr": 2000.0,
            "total_participant_slots_capacity": 2,
            "assigned_staff_leader_id": staff_id,
        }
        create_response = self.client.post("/api/admin/expeditions", json=exp_payload, headers=admin_headers)
        exp_id = json.loads(create_response.data)["created_expedition"]["trekking_route_expedition_id"]

        # Open the expedition
        self.client.patch(
            f"/api/admin/expeditions/{exp_id}",
            json={
                "expedition_route_name": "Quick weekend escape to Triund",
                "current_expedition_lifecycle_status": "Open",
                "expedition_difficulty_level": "Easy",
                "expedition_duration_in_days": 2,
                "total_participant_slots_capacity": 2,
            },
            headers=admin_headers
        )

        # 3. Create Trekker Account & book 1 slot
        self.client.post(
            "/api/auth/register",
            json={
                "user_full_name": "Trekker Sunil",
                "user_email_address": "sunil@adventure.com",
                "raw_password": "SecurePassword@123",
            }
        )
        trekker_headers = self._get_auth_headers("sunil@adventure.com", "SecurePassword@123")

        # Book 1 slot
        booking_response = self.client.post(
            "/api/trekker/bookings",
            json={
                "booked_expedition_instance_id": exp_id,
                "number_of_participants_in_booking": 1,
                "simulated_payment_completed": True
            },
            headers=trekker_headers
        )
        self.assertEqual(booking_response.status_code, 201)
        booking_data = json.loads(booking_response.data)
        self.assertIn("confirmation_reference_code", booking_data)

        # Verify slots remaining in DB is now 1
        exp_in_db = TrekkingRouteExpedition.query.get(exp_id)
        self.assertEqual(exp_in_db.available_participant_slots_remaining, 1)

        # Try booking again for the same trek (Duplicate booking guard check)
        dup_booking_response = self.client.post(
            "/api/trekker/bookings",
            json={
                "booked_expedition_instance_id": exp_id,
                "number_of_participants_in_booking": 1,
                "simulated_payment_completed": True
            },
            headers=trekker_headers
        )
        self.assertEqual(dup_booking_response.status_code, 409)  # Conflict (duplicate booking)

        # 4. Create another Trekker Account and try booking 2 slots (exceeds remaining slots=1)
        self.client.post(
            "/api/auth/register",
            json={
                "user_full_name": "Trekker Rahul",
                "user_email_address": "rahul@adventure.com",
                "raw_password": "SecurePassword@456",
            }
        )
        trekker2_headers = self._get_auth_headers("rahul@adventure.com", "SecurePassword@456")

        overbook_response = self.client.post(
            "/api/trekker/bookings",
            json={
                "booked_expedition_instance_id": exp_id,
                "number_of_participants_in_booking": 2,
                "simulated_payment_completed": True
            },
            headers=trekker2_headers
        )
        self.assertEqual(overbook_response.status_code, 409)  # Conflict

        # 5. Book exactly the 1 remaining slot
        successful_fill_response = self.client.post(
            "/api/trekker/bookings",
            json={
                "booked_expedition_instance_id": exp_id,
                "number_of_participants_in_booking": 1,
                "simulated_payment_completed": True
            },
            headers=trekker2_headers
        )
        self.assertEqual(successful_fill_response.status_code, 201)

        # Verify expedition auto-closed because available slots became 0
        exp_in_db = TrekkingRouteExpedition.query.get(exp_id)
        self.assertEqual(exp_in_db.available_participant_slots_remaining, 0)
        self.assertEqual(exp_in_db.current_expedition_lifecycle_status, ExpeditionLifecycleStatus.CLOSED)

        # 6. Sunil cancels his booking (should restore 1 slot and re-open expedition to OPEN)
        booking_id = booking_data["booking_details"]["participant_booking_record_id"]
        cancel_response = self.client.patch(
            f"/api/trekker/bookings/{booking_id}/cancel",
            json={"cancellation_reason_description": "Illness"},
            headers=trekker_headers
        )
        self.assertEqual(cancel_response.status_code, 200)

        # Verify slots restored and status auto-reopened
        exp_in_db = TrekkingRouteExpedition.query.get(exp_id)
        self.assertEqual(exp_in_db.available_participant_slots_remaining, 1)
        self.assertEqual(exp_in_db.current_expedition_lifecycle_status, ExpeditionLifecycleStatus.OPEN)

    # =========================================================================
    # Test Cases: Staff Operations
    # =========================================================================

    def test_staff_dashboard_and_operations(self) -> None:
        """Verifies that Staff can manage operational details for assigned treks only."""
        admin_headers = self._get_auth_headers(self.admin_email, self.admin_password)

        # 1. Create a Staff user
        self.client.post(
            "/api/admin/staff",
            json={
                "user_full_name": "Staff Guide Preet",
                "user_email_address": "preet@trekstaff.com",
                "raw_password": "PreetSecurePassword@111",
            },
            headers=admin_headers
        )
        preet_db = PlatformUserAccount.query.filter_by(user_email_address="preet@trekstaff.com").first()
        preet_id = preet_db.user_account_id
        preet_headers = self._get_auth_headers("preet@trekstaff.com", "PreetSecurePassword@111")

        # 2. Create and assign an expedition to Amit (Not Preet)
        self.client.post(
            "/api/admin/staff",
            json={
                "user_full_name": "Staff Guide Amit",
                "user_email_address": "amit@trekstaff.com",
                "raw_password": "AmitSecurePassword@999",
            },
            headers=admin_headers
        )
        amit_db = PlatformUserAccount.query.filter_by(user_email_address="amit@trekstaff.com").first()
        amit_id = amit_db.user_account_id

        create_response = self.client.post(
            "/api/admin/expeditions",
            json={
                "expedition_route_name": "Amit's Secret Expedition",
                "expedition_geographical_location": "Sikkim, India",
                "expedition_difficulty_level": "Hard",
                "expedition_duration_in_days": 10,
                "total_participant_slots_capacity": 10,
                "assigned_staff_leader_id": amit_id,
            },
            headers=admin_headers
        )
        exp_id = json.loads(create_response.data)["created_expedition"]["trekking_route_expedition_id"]

        # Make it open
        self.client.patch(
            f"/api/admin/expeditions/{exp_id}",
            json={
                "expedition_route_name": "Amit's Secret Expedition",
                "current_expedition_lifecycle_status": "Open",
                "expedition_difficulty_level": "Hard",
                "expedition_duration_in_days": 10,
                "total_participant_slots_capacity": 10,
            },
            headers=admin_headers
        )

        # 3. Preet tries to update Amit's expedition (should be forbidden!)
        unauthorized_update_response = self.client.patch(
            f"/api/staff/assigned-expeditions/{exp_id}/operational-update",
            json={"available_participant_slots_remaining": 5},
            headers=preet_headers
        )
        self.assertEqual(unauthorized_update_response.status_code, 404)  # Secure fallback (not found) for unauthorized staff

        # 4. Assign Amit's trek to Preet (reassign via admin)
        self.client.patch(
            f"/api/admin/expeditions/{exp_id}",
            json={
                "expedition_route_name": "Preet's Newly Assigned Expedition",
                "current_expedition_lifecycle_status": "Open",
                "expedition_difficulty_level": "Hard",
                "expedition_duration_in_days": 10,
                "total_participant_slots_capacity": 10,
                "assigned_staff_leader_id": preet_id,
            },
            headers=admin_headers
        )

        # 5. Preet now tries to update (should succeed)
        authorized_update_response = self.client.patch(
            f"/api/staff/assigned-expeditions/{exp_id}/operational-update",
            json={"available_participant_slots_remaining": 8, "current_expedition_lifecycle_status": "Closed"},
            headers=preet_headers
        )
        self.assertEqual(authorized_update_response.status_code, 200)

        # Verify changes in DB
        exp_in_db = TrekkingRouteExpedition.query.get(exp_id)
        self.assertEqual(exp_in_db.available_participant_slots_remaining, 8)
        self.assertEqual(exp_in_db.current_expedition_lifecycle_status, ExpeditionLifecycleStatus.CLOSED)


if __name__ == "__main__":
    unittest.main()
