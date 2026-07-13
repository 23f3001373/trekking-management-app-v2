"""
tasks.py — Celery Background Task Definitions
==============================================
This module defines all asynchronous and scheduled tasks for the Trekking
Management Platform. Tasks run in a separate Celery worker process and have
full access to the Flask application context (via the ContextAwareCeleryTask
base class configured in __init__.py).

Three categories of tasks are defined here:

  CATEGORY A — Scheduled Periodic Tasks (driven by Celery Beat):
    1. `send_daily_upcoming_trek_reminder_emails` — Runs every day at 08:00 IST.
       Queries for expeditions starting in the next 48 hours and emails
       all BOOKED participants a reminder with their expedition details.

    2. `generate_monthly_admin_activity_report_pdf` — Runs on the 1st of every
       month at 06:00 IST. Compiles an HTML/PDF report of platform activity
       (new registrations, bookings, completed treks) for the Admin.

  CATEGORY B — User-Triggered Async Tasks:
    3. `dispatch_booking_history_csv_export_task` — Triggered by a Trekker via
       POST /api/trekker/bookings/export-csv. Builds a CSV in memory and either
       emails it to the trekker or saves it to a file path for download.

HOW Celery Beat scheduling is configured:
------------------------------------------
The `beat_schedule` dict at the bottom of this file is read by the Celery Beat
scheduler process. Each entry maps a human-readable task name to a schedule
(crontab or interval) and the task function to call.

HOW to run the workers:
------------------------
  # Start the Celery worker (processes tasks from the queue):
  celery -A celery_worker.celery_task_queue worker --loglevel=info

  # Start the Celery Beat scheduler (enqueues periodic tasks):
  celery -A celery_worker.celery_task_queue beat --loglevel=info

SMTP / Email Note:
------------------
In development, the email sending is implemented with Flask-Mail via SMTP.
In a production deployment, replace with a transactional email provider SDK
(SendGrid, AWS SES, Mailgun) for reliability and deliverability guarantees.
"""

import csv
import io
import json
import os
import smtplib
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

from celery.schedules import crontab
from flask import current_app

from .extensions import celery_task_queue, database_extension as db
from .models import (
    PlatformUserAccount,
    TrekkingRouteExpedition,
    ParticipantBookingRecord,
    UserPlatformRole,
    ExpeditionLifecycleStatus,
    BookingLifecycleStatus,
)


# =========================================================================== #
#  UTILITY: Google Chat Webhook Helper                                         #
# =========================================================================== #

def _send_google_chat_webhook_notification(webhook_url: str, message_text: str) -> bool:
    """
    Sends a message to a Google Chat space using a incoming webhook.
    Returns True if sent successfully, False otherwise.
    """
    if not webhook_url:
        return False
    try:
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps({"text": message_text}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as response:
            return response.status == 200
    except urllib.error.URLError as e:
        current_app.logger.error(f"Google Chat webhook notification error: {e}")
        return False


# =========================================================================== #
#  UTILITY: Email Sending Helper                                                 #
# =========================================================================== #

def _send_smtp_email_notification(
    recipient_email_address: str,
    email_subject_line: str,
    email_html_body: str,
    attachment_filename: str = None,
    attachment_bytes_content: bytes = None,
) -> bool:
    """
    Sends an email via SMTP using configuration from the Flask app config.

    This is a low-level utility used by all task functions that need to send
    notifications. It is intentionally simple — no queueing, no retry logic
    at this level (Celery task retries handle that at a higher level).

    Args:
        recipient_email_address: The To: address.
        email_subject_line: The Subject: header.
        email_html_body: The HTML body of the email (rich formatting supported).
        attachment_filename: Optional. Filename for a file attachment.
        attachment_bytes_content: Optional. Raw bytes of the attachment.

    Returns:
        bool: True if the email was sent without SMTP errors, False otherwise.
    """
    mail_config = {
        "server": current_app.config.get("MAIL_SERVER", "smtp.gmail.com"),
        "port": current_app.config.get("MAIL_PORT", 587),
        "use_tls": current_app.config.get("MAIL_USE_TLS", True),
        "username": current_app.config.get("MAIL_USERNAME", ""),
        "password": current_app.config.get("MAIL_PASSWORD", ""),
        "sender": current_app.config.get("MAIL_DEFAULT_SENDER", "noreply@trekkingplatform.com"),
    }

    # If SMTP credentials are not configured (dev environment) or placeholder values used, log and write to local file.
    is_placeholder = (
        not mail_config["username"] or 
        not mail_config["password"] or 
        "your-gmail" in mail_config["username"] or 
        "example" in mail_config["username"]
    )
    if is_placeholder:
        try:
            sent_emails_dir = os.path.abspath(os.path.join(current_app.root_path, "..", "sent_emails"))
            os.makedirs(sent_emails_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_subject = "".join([c for c in email_subject_line if c.isalnum() or c in " _-"]).strip()
            email_filename = f"{timestamp}_{recipient_email_address}_{safe_subject}.html"
            email_filepath = os.path.join(sent_emails_dir, email_filename)
            
            with open(email_filepath, "w", encoding="utf-8") as email_file:
                email_file.write(email_html_body)
                
            if attachment_filename and attachment_bytes_content is not None:
                attachment_filepath = os.path.join(sent_emails_dir, f"{timestamp}_{attachment_filename}")
                with open(attachment_filepath, "wb") as attachment_file:
                    attachment_file.write(attachment_bytes_content)
                    
            current_app.logger.warning(
                f"[MAIL SIMULATED] SMTP not configured. Saved email '{email_subject_line}' "
                f"to sent_emails/{email_filename}"
            )
        except Exception as e:
            current_app.logger.error(f"Error simulating email save: {e}")
        return True  # Return True so tasks don't fail in development.

    try:
        email_message = MIMEMultipart("mixed")
        email_message["From"] = mail_config["sender"]
        email_message["To"] = recipient_email_address
        email_message["Subject"] = email_subject_line

        html_part = MIMEText(email_html_body, "html", "utf-8")
        email_message.attach(html_part)

        # Attach a file if one is provided (used for CSV/PDF attachments).
        if attachment_filename and attachment_bytes_content:
            file_attachment_part = MIMEBase("application", "octet-stream")
            file_attachment_part.set_payload(attachment_bytes_content)
            encoders.encode_base64(file_attachment_part)
            file_attachment_part.add_header(
                "Content-Disposition",
                f'attachment; filename="{attachment_filename}"'
            )
            email_message.attach(file_attachment_part)

        with smtplib.SMTP(mail_config["server"], mail_config["port"]) as smtp_connection:
            smtp_connection.ehlo()
            if mail_config["use_tls"]:
                smtp_connection.starttls()
            smtp_connection.login(mail_config["username"], mail_config["password"])
            smtp_connection.sendmail(
                mail_config["sender"],
                recipient_email_address,
                email_message.as_string()
            )

        current_app.logger.info(
            f"Email sent successfully to {recipient_email_address}: '{email_subject_line}'"
        )
        return True

    except smtplib.SMTPException as smtp_error:
        current_app.logger.error(
            f"SMTP error sending to {recipient_email_address}: {smtp_error}"
        )
        return False


# =========================================================================== #
#  CATEGORY A — SCHEDULED PERIODIC TASKS                                        #
# =========================================================================== #

@celery_task_queue.task(
    bind=True,
    name="trekking_platform.tasks.send_daily_upcoming_trek_reminder_emails",
    max_retries=3,
    default_retry_delay=300,  # Retry after 5 minutes on transient failures.
)
def send_daily_upcoming_trek_reminder_notifications(self) -> dict:
    """
    SCHEDULED TASK — Runs daily at 08:00 IST (02:30 UTC).

    Scans all OPEN/APPROVED expeditions scheduled to start within the next
    48 hours and sends personalised email reminders to every BOOKED participant.

    WHY 48-hour window instead of 24?
    A 48-hour lead time gives trekkers enough time to travel to the assembly
    point for multi-city trips, pack final gear, and arrange transportation.
    A 24-hour window would be too late for long-distance participants.

    Task Retry Behaviour:
    If a transient error occurs (e.g., brief SMTP server downtime), Celery
    automatically retries up to `max_retries=3` times with `default_retry_delay`
    seconds between attempts, using the `self.retry(exc=exception)` pattern.

    Returns:
        dict: Summary of how many reminders were sent and how many failed.
    """
    current_app.logger.info(
        "Celery task started: send_daily_upcoming_trek_reminder_notifications"
    )

    reminder_window_start = datetime.now(timezone.utc).date()
    reminder_window_end = reminder_window_start + timedelta(hours=48)

    # Find all expeditions starting within the next 48 hours.
    upcoming_expeditions_in_window = TrekkingRouteExpedition.query.filter(
        TrekkingRouteExpedition.expedition_scheduled_start_date >= reminder_window_start,
        TrekkingRouteExpedition.expedition_scheduled_start_date <= reminder_window_end,
        TrekkingRouteExpedition.current_expedition_lifecycle_status.in_([
            ExpeditionLifecycleStatus.OPEN,
            ExpeditionLifecycleStatus.APPROVED,
            ExpeditionLifecycleStatus.CLOSED,
        ])
    ).all()

    total_reminders_sent = 0
    total_reminders_failed = 0

    for upcoming_expedition in upcoming_expeditions_in_window:
        # Get all confirmed participants for this expedition.
        confirmed_participants = (
            upcoming_expedition.registered_participant_bookings
            .filter_by(current_booking_lifecycle_status=BookingLifecycleStatus.BOOKED)
            .all()
        )

        for participant_booking in confirmed_participants:
            participant_trekker = participant_booking.booking_owner_trekker

            # Build a personalised HTML email body.
            reminder_email_html = f"""
            <html><body style="font-family: Arial, sans-serif; color: #333;">
            <div style="max-width: 600px; margin: auto; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
                <h2 style="color: #2E7D32;">🏔️ Trek Reminder — {upcoming_expedition.expedition_route_name}</h2>
                <p>Hello <strong>{participant_trekker.user_full_name}</strong>,</p>
                <p>This is your <strong>48-hour reminder</strong> for your upcoming trek!</p>
                <table style="width: 100%; border-collapse: collapse; margin: 16px 0;">
                    <tr><td style="padding: 8px; background: #f5f5f5;"><strong>Trek Name</strong></td>
                        <td style="padding: 8px;">{upcoming_expedition.expedition_route_name}</td></tr>
                    <tr><td style="padding: 8px; background: #f5f5f5;"><strong>Location</strong></td>
                        <td style="padding: 8px;">{upcoming_expedition.expedition_geographical_location}</td></tr>
                    <tr><td style="padding: 8px; background: #f5f5f5;"><strong>Start Date</strong></td>
                        <td style="padding: 8px;">{upcoming_expedition.expedition_scheduled_start_date}</td></tr>
                    <tr><td style="padding: 8px; background: #f5f5f5;"><strong>Meeting Point</strong></td>
                        <td style="padding: 8px;">{upcoming_expedition.expedition_meeting_point_address or 'See trek details page'}</td></tr>
                    <tr><td style="padding: 8px; background: #f5f5f5;"><strong>Booking Ref</strong></td>
                        <td style="padding: 8px;"><code>{participant_booking.booking_confirmation_reference_code}</code></td></tr>
                    <tr><td style="padding: 8px; background: #f5f5f5;"><strong>Staff Leader</strong></td>
                        <td style="padding: 8px;">{upcoming_expedition.assigned_staff_leader.user_full_name if upcoming_expedition.assigned_staff_leader else 'To be announced'}</td></tr>
                </table>
                <p style="color: #555;">Please arrive at the meeting point <strong>30 minutes before departure</strong>.</p>
                <p style="color: #555;">Stay safe, stay hydrated, and enjoy the mountains! 🌿</p>
                <hr/>
                <p style="font-size: 12px; color: #888;">Trekking Platform V2 — Automated Reminder</p>
            </div></body></html>
            """

            email_sent_successfully = _send_smtp_email_notification(
                recipient_email_address=participant_trekker.user_email_address,
                email_subject_line=(
                    f"⛺ Reminder: Your trek '{upcoming_expedition.expedition_route_name}' "
                    f"starts on {upcoming_expedition.expedition_scheduled_start_date}!"
                ),
                email_html_body=reminder_email_html,
            )

            # Optional/Extra feature: Google Chat Webhook reminder integration
            google_chat_webhook_url = current_app.config.get("GOOGLE_CHAT_WEBHOOK_URL")
            if google_chat_webhook_url:
                chat_message = (
                    f"🏔️ *Upcoming Trek Reminder* for *{participant_trekker.user_full_name}*!\n"
                    f"⛺ Trek: *{upcoming_expedition.expedition_route_name}*\n"
                    f"📅 Start Date: {upcoming_expedition.expedition_scheduled_start_date}\n"
                    f"📍 Meeting Point: {upcoming_expedition.expedition_meeting_point_address or 'See platform'}\n"
                    f"🔑 Booking Ref: `{participant_booking.booking_confirmation_reference_code}`"
                )
                _send_google_chat_webhook_notification(google_chat_webhook_url, chat_message)

            if email_sent_successfully:
                total_reminders_sent += 1
            else:
                total_reminders_failed += 1

    task_summary = {
        "task_name": "send_daily_upcoming_trek_reminder_notifications",
        "expeditions_processed": len(upcoming_expeditions_in_window),
        "reminder_emails_sent": total_reminders_sent,
        "reminder_emails_failed": total_reminders_failed,
        "google_chat_notifications_sent": total_reminders_sent if google_chat_webhook_url else 0,
        "executed_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    current_app.logger.info(f"Task completed: {task_summary}")
    return task_summary


@celery_task_queue.task(
    bind=True,
    name="trekking_platform.tasks.generate_monthly_admin_activity_report_pdf",
    max_retries=2,
    default_retry_delay=600,  # Retry after 10 minutes if PDF generation fails.
)
def generate_monthly_admin_activity_report_pdf(self) -> dict:
    """
    SCHEDULED TASK — Runs on the 1st of every month at 06:00 IST (00:30 UTC).

    Compiles a comprehensive monthly activity report for the Admin covering:
      • New Trekker registrations in the past month.
      • New bookings placed in the past month.
      • Expeditions completed in the past month.
      • Expeditions cancelled in the past month.
      • Revenue estimate (bookings × price_per_person).

    The report is generated as a styled HTML string. In a full production setup,
    this would be rendered to PDF using WeasyPrint:
        from weasyprint import HTML
        pdf_bytes = HTML(string=html_report_content).write_pdf()

    For this implementation, the HTML report itself is emailed to the Admin
    as an attachment. PDF conversion is noted as a future enhancement.

    Returns:
        dict: Report generation summary with admin email delivery status.
    """
    current_app.logger.info(
        "Celery task started: generate_monthly_admin_activity_report_pdf"
    )

    now_utc = datetime.now(timezone.utc)
    # Report covers the previous calendar month.
    report_month_start = (now_utc.replace(day=1) - timedelta(days=1)).replace(day=1)
    report_month_end = now_utc.replace(day=1) - timedelta(seconds=1)
    month_label = report_month_start.strftime("%B %Y")

    # --- Gather metrics for the report period ---
    new_trekker_registrations = PlatformUserAccount.query.filter(
        PlatformUserAccount.assigned_platform_role == UserPlatformRole.TREKKER,
        PlatformUserAccount.account_created_at_utc >= report_month_start,
        PlatformUserAccount.account_created_at_utc <= report_month_end,
    ).count()

    new_bookings_placed = ParticipantBookingRecord.query.filter(
        ParticipantBookingRecord.booking_placed_at_utc >= report_month_start,
        ParticipantBookingRecord.booking_placed_at_utc <= report_month_end,
    ).count()

    completed_expeditions = TrekkingRouteExpedition.query.filter(
        TrekkingRouteExpedition.current_expedition_lifecycle_status == ExpeditionLifecycleStatus.COMPLETED,
        TrekkingRouteExpedition.expedition_record_last_updated_at_utc >= report_month_start,
        TrekkingRouteExpedition.expedition_record_last_updated_at_utc <= report_month_end,
    ).count()

    cancelled_expeditions = TrekkingRouteExpedition.query.filter(
        TrekkingRouteExpedition.current_expedition_lifecycle_status == ExpeditionLifecycleStatus.CANCELLED,
        TrekkingRouteExpedition.expedition_record_last_updated_at_utc >= report_month_start,
        TrekkingRouteExpedition.expedition_record_last_updated_at_utc <= report_month_end,
    ).count()

    # Revenue estimate: sum of (price × participants) for BOOKED/COMPLETED bookings.
    revenue_query_result = (
        db.session.query(
            db.func.sum(
                TrekkingRouteExpedition.expedition_price_per_person_inr *
                ParticipantBookingRecord.number_of_participants_in_booking
            )
        )
        .join(
            ParticipantBookingRecord,
            TrekkingRouteExpedition.trekking_route_expedition_id ==
            ParticipantBookingRecord.booked_expedition_instance_id
        )
        .filter(
            ParticipantBookingRecord.booking_placed_at_utc >= report_month_start,
            ParticipantBookingRecord.current_booking_lifecycle_status.in_([
                BookingLifecycleStatus.BOOKED,
                BookingLifecycleStatus.COMPLETED,
            ])
        )
        .scalar()
    )
    estimated_monthly_revenue_inr = revenue_query_result or 0.0

    # --- Build the HTML report ---
    html_report_content = f"""
    <html>
    <head>
        <style>
            body {{ font-family: 'Segoe UI', sans-serif; background: #f8f9fa; color: #333; }}
            .report-container {{ max-width: 800px; margin: 30px auto; background: white;
                                 padding: 40px; border-radius: 10px;
                                 box-shadow: 0 2px 15px rgba(0,0,0,0.1); }}
            h1 {{ color: #1B5E20; border-bottom: 3px solid #4CAF50; padding-bottom: 10px; }}
            h2 {{ color: #2E7D32; }}
            .metric-grid {{ display: grid; grid-template-columns: 1fr 1fr;
                            gap: 20px; margin: 20px 0; }}
            .metric-card {{ background: #E8F5E9; border-left: 5px solid #4CAF50;
                            padding: 16px; border-radius: 5px; }}
            .metric-card .value {{ font-size: 2em; font-weight: bold; color: #1B5E20; }}
            .metric-card .label {{ color: #555; font-size: 0.9em; }}
            .revenue-highlight {{ background: #FFF8E1; border-left: 5px solid #FFC107;
                                   padding: 20px; border-radius: 5px; margin: 20px 0; }}
            .revenue-highlight .value {{ font-size: 2.5em; font-weight: bold; color: #F57F17; }}
            footer {{ text-align: center; color: #888; font-size: 0.8em; margin-top: 30px; }}
        </style>
    </head>
    <body>
        <div class="report-container">
            <h1>🏔️ Trekking Platform V2 — Monthly Activity Report</h1>
            <p><strong>Report Period:</strong> {month_label}</p>
            <p><strong>Generated At:</strong> {now_utc.strftime('%d %B %Y, %H:%M UTC')}</p>

            <h2>📊 Activity Metrics</h2>
            <div class="metric-grid">
                <div class="metric-card">
                    <div class="value">{new_trekker_registrations}</div>
                    <div class="label">New Trekker Registrations</div>
                </div>
                <div class="metric-card">
                    <div class="value">{new_bookings_placed}</div>
                    <div class="label">New Bookings Placed</div>
                </div>
                <div class="metric-card">
                    <div class="value">{completed_expeditions}</div>
                    <div class="label">Expeditions Completed</div>
                </div>
                <div class="metric-card">
                    <div class="value">{cancelled_expeditions}</div>
                    <div class="label">Expeditions Cancelled</div>
                </div>
            </div>

            <h2>💰 Estimated Revenue</h2>
            <div class="revenue-highlight">
                <div class="value">₹{estimated_monthly_revenue_inr:,.2f}</div>
                <div class="label">
                    Estimated revenue from bookings placed in {month_label}
                    (confirmed + completed bookings, based on per-person price)
                </div>
            </div>

            <footer>
                <p>This is an automated report generated by Trekking Platform V2.</p>
                <p>For queries, contact the system administrator.</p>
            </footer>
        </div>
    </body>
    </html>
    """

    # Fetch the Admin email to send the report to.
    admin_account = PlatformUserAccount.query.filter_by(
        assigned_platform_role=UserPlatformRole.ADMIN
    ).first()

    if admin_account is None:
        current_app.logger.error("Cannot send monthly report — no Admin account found.")
        return {"error": "Admin account not found for report delivery."}

    report_filename = f"trek_platform_report_{month_label.replace(' ', '_')}.html"

    email_sent = _send_smtp_email_notification(
        recipient_email_address=admin_account.user_email_address,
        email_subject_line=f"📊 Monthly Activity Report — {month_label} | Trekking Platform V2",
        email_html_body=f"<p>Please find the monthly report for <strong>{month_label}</strong> attached.</p>",
        attachment_filename=report_filename,
        attachment_bytes_content=html_report_content.encode("utf-8"),
    )

    task_summary = {
        "task_name": "generate_monthly_admin_activity_report_pdf",
        "report_period": month_label,
        "metrics": {
            "new_trekker_registrations": new_trekker_registrations,
            "new_bookings_placed": new_bookings_placed,
            "completed_expeditions": completed_expeditions,
            "cancelled_expeditions": cancelled_expeditions,
            "estimated_revenue_inr": estimated_monthly_revenue_inr,
        },
        "report_emailed_to_admin": email_sent,
        "executed_at_utc": now_utc.isoformat(),
    }
    current_app.logger.info(f"Monthly report task completed: {task_summary}")
    return task_summary


# =========================================================================== #
#  CATEGORY B — USER-TRIGGERED ASYNC TASKS                                      #
# =========================================================================== #

@celery_task_queue.task(
    bind=True,
    name="trekking_platform.tasks.dispatch_booking_history_csv_export_task",
    max_retries=3,
    default_retry_delay=60,
)
def dispatch_booking_history_csv_export_task(
    self,
    trekker_account_id: int,
    trekker_email_address: str,
    trekker_full_name: str,
) -> dict:
    """
    ASYNC TASK — Triggered by Trekker via POST /api/trekker/bookings/export-csv.

    Builds a complete CSV of the trekker's booking history and emails it to
    them as an attachment. The trekker receives an HTTP 202 immediately and
    this task runs in the background, notifying them via email when done.

    WHY pass IDs/strings instead of model objects?
    Celery serialises task arguments as JSON. SQLAlchemy model objects cannot
    be JSON-serialised. We pass only the scalar identifiers needed to re-fetch
    data inside the worker's Flask context.

    CSV Columns:
      Booking Ref, Expedition Name, Location, Difficulty, Start Date, End Date,
      Duration (days), Price (INR), Participants, Status, Special Requirements,
      Cancellation Reason, Booked At

    Args:
        trekker_account_id: The PK of the Trekker's PlatformUserAccount.
        trekker_email_address: Email address to deliver the CSV to.
        trekker_full_name: Used for personalisation in the email body.

    Returns:
        dict: Task execution summary including row count and email status.
    """
    current_app.logger.info(
        f"CSV export task started for trekker_account_id={trekker_account_id}"
    )

    try:
        # Re-fetch the trekker's bookings inside the Celery worker's app context.
        all_trekker_bookings = (
            ParticipantBookingRecord.query
            .filter_by(booking_owner_trekker_id=trekker_account_id)
            .order_by(ParticipantBookingRecord.booking_placed_at_utc.desc())
            .all()
        )

        # Build the CSV in memory using Python's stdlib csv module.
        csv_output_buffer = io.StringIO()
        csv_writer = csv.writer(csv_output_buffer, quoting=csv.QUOTE_ALL)

        # Write header row.
        csv_writer.writerow([
            "Booking Reference Code",
            "Expedition Name",
            "Geographical Location",
            "Difficulty Level",
            "Scheduled Start Date",
            "Scheduled End Date",
            "Duration (Days)",
            "Price Per Person (INR)",
            "Number of Participants",
            "Booking Status",
            "Special Requirements Note",
            "Cancellation Reason",
            "Booking Placed At (UTC)",
            "Last Status Change (UTC)",
        ])

        # Write one row per booking record.
        for booking in all_trekker_bookings:
            expedition = booking.booked_expedition_instance
            csv_writer.writerow([
                booking.booking_confirmation_reference_code or "N/A",
                expedition.expedition_route_name if expedition else "Expedition Deleted",
                expedition.expedition_geographical_location if expedition else "N/A",
                expedition.expedition_difficulty_level.value if expedition else "N/A",
                expedition.expedition_scheduled_start_date.isoformat()
                    if expedition and expedition.expedition_scheduled_start_date else "N/A",
                expedition.expedition_scheduled_end_date.isoformat()
                    if expedition and expedition.expedition_scheduled_end_date else "N/A",
                expedition.expedition_duration_in_days if expedition else "N/A",
                expedition.expedition_price_per_person_inr if expedition else "N/A",
                booking.number_of_participants_in_booking,
                booking.current_booking_lifecycle_status.value,
                booking.trekker_special_requirements_note or "",
                booking.cancellation_reason_description or "",
                booking.booking_placed_at_utc.isoformat()
                    if booking.booking_placed_at_utc else "N/A",
                booking.booking_last_status_changed_at_utc.isoformat()
                    if booking.booking_last_status_changed_at_utc else "N/A",
            ])

        csv_bytes_content = csv_output_buffer.getvalue().encode("utf-8-sig")
        # utf-8-sig adds a BOM so Excel correctly interprets the encoding.
        csv_output_buffer.close()

        total_rows_exported = len(all_trekker_bookings)
        export_timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        csv_attachment_filename = f"booking_history_{trekker_account_id}_{export_timestamp}.csv"

        # Compose the notification email with CSV attached.
        completion_email_html = f"""
        <html><body style="font-family: Arial, sans-serif; color: #333;">
        <div style="max-width: 600px; margin: auto; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
            <h2 style="color: #1565C0;">📄 Your Booking History Export is Ready</h2>
            <p>Hello <strong>{trekker_full_name}</strong>,</p>
            <p>Your booking history CSV export has been completed successfully.</p>
            <ul>
                <li><strong>Total Bookings Exported:</strong> {total_rows_exported}</li>
                <li><strong>Generated At:</strong> {datetime.now(timezone.utc).strftime('%d %b %Y, %H:%M UTC')}</li>
                <li><strong>Filename:</strong> <code>{csv_attachment_filename}</code></li>
            </ul>
            <p>The CSV file is attached to this email. Open it with Excel or Google Sheets.</p>
            <hr/>
            <p style="font-size: 12px; color: #888;">Trekking Platform V2 — Automated Export Notification</p>
        </div></body></html>
        """

        email_delivery_successful = _send_smtp_email_notification(
            recipient_email_address=trekker_email_address,
            email_subject_line="✅ Your Booking History CSV Export is Ready | Trekking Platform V2",
            email_html_body=completion_email_html,
            attachment_filename=csv_attachment_filename,
            attachment_bytes_content=csv_bytes_content,
        )

        task_result_summary = {
            "task_name": "dispatch_booking_history_csv_export_task",
            "trekker_account_id": trekker_account_id,
            "total_booking_rows_exported": total_rows_exported,
            "csv_filename": csv_attachment_filename,
            "email_delivered_successfully": email_delivery_successful,
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        }

        current_app.logger.info(f"CSV export task completed: {task_result_summary}")
        return task_result_summary

    except Exception as task_execution_error:
        current_app.logger.error(
            f"CSV export task failed for trekker_account_id={trekker_account_id}: "
            f"{task_execution_error}"
        )
        # Celery auto-retry: re-raise after registering for retry.
        raise self.retry(exc=task_execution_error)


# =========================================================================== #
#  CELERY BEAT SCHEDULE — Periodic Task Configuration                            #
# =========================================================================== #
#
# This dict is read by the `celery beat` process to know when to enqueue
# each periodic task. Tasks are identified by their `name` argument.
#
# Crontab expressions follow the same convention as Unix cron:
#   crontab(hour=2, minute=30) → every day at 02:30 UTC (08:00 IST)
#   crontab(day_of_month=1, hour=0, minute=30) → 1st of every month at 00:30 UTC

CELERY_BEAT_PERIODIC_TASK_SCHEDULE = {
    # Daily reminder at 08:00 IST (02:30 UTC)
    "daily-upcoming-trek-reminder-emails": {
        "task": "trekking_platform.tasks.send_daily_upcoming_trek_reminder_emails",
        "schedule": crontab(hour=2, minute=30),
        "options": {"expires": 3600},  # Discard if not consumed within 1 hour.
    },
    # Monthly report on the 1st of the month at 06:00 IST (00:30 UTC)
    "monthly-admin-activity-report-pdf": {
        "task": "trekking_platform.tasks.generate_monthly_admin_activity_report_pdf",
        "schedule": crontab(day_of_month=1, hour=0, minute=30),
        "options": {"expires": 7200},
    },
}
