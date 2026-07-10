# 🌿 TrekVista — Setup, Troubleshooting & Walkthrough Guide

This guide provides comprehensive instructions on how to run TrekVista (Trekking Management Platform V2), troubleshoot common operational issues, and perform a live walkthrough of the application to demonstrate its full architectural features.

---

## 🚀 Part 1: How to Run the Application

The application is built as a decoupled system: a **Flask API Backend**, a **Vue.js 3 Single Page Application (SPA) Frontend**, and a **Celery Task Queue** driven by a **Redis Broker**. 

Follow these steps in separate terminal shells:

### 1. Start the Redis Server (inside WSL 2)
To avoid Windows socket loopback lockups on the standard Redis port `6379`, start Redis on port `6380` inside WSL:
```bash
wsl redis-server --port 6380 --protected-mode no --daemonize yes
```
*Verify Redis is alive by running: `wsl redis-cli -p 6380 ping` (should reply `PONG`).*

### 2. Start the Flask Backend API
Navigate to the `backend/` directory, activate the virtual environment, and run the development server:
```powershell
cd backend
.venv\Scripts\activate
python run.py
```
*The API server will run at `http://127.0.0.1:5000`.*

### 3. Start the Celery Worker & Beat Processes
In two separate terminal shells, start the Celery processes to handle asynchronous background tasks and scheduled reminders:
- **Terminal A (Celery Worker)**:
  ```powershell
  cd backend
  .venv\Scripts\activate
  celery -A celery_worker.celery_task_queue worker --loglevel=info --concurrency=2 -P solo
  ```
- **Terminal B (Celery Beat Scheduler)**:
  ```powershell
  cd backend
  .venv\Scripts\activate
  celery -A celery_worker.celery_task_queue beat --loglevel=info
  ```

### 4. Start the Frontend Server
Serve the `frontend/` directory using Python's built-in HTTP server:
```powershell
cd frontend
python -m http.server 5501
```
*Open `http://localhost:5501/index.html` in your web browser to access the app.*

---

## 🛠️ Part 2: Troubleshooting Guide (Common Problems)

### 1. Redis Connection Refused (`ConnectionRefusedError: [WinError 10061]`)
* **Symptom**: The Celery worker or Flask API logs show `Error 10061 connecting to localhost:6380`.
* **Cause**: Redis inside WSL has exited, or loopback port-forwarding between Windows and WSL has broken.
* **Solution**:
  1. Restart Redis inside WSL: `wsl redis-server --port 6380 --protected-mode no --daemonize yes`
  2. Verify WSL IP connectivity: test using `wsl redis-cli -p 6380 ping`
  3. Ensure `REDIS_URL` in `backend/.env` points to `redis://localhost:6380/0`.

### 2. Login CORS Block / Network Error
* **Symptom**: Clicking "Login" in the browser results in a generic network error or a browser console error complaining about CORS.
* **Cause**: Flask's Allowed Origins list does not match the port or hostname of the frontend server.
* **Solution**:
  1. Check `backend/.env` and ensure `ALLOWED_CORS_ORIGINS` includes `http://localhost:5501` and `http://127.0.0.1:5501`.
  2. Restart the Flask API server so the environment configurations reload.

### 3. Empty Metrics Cards or Dashboards Showing 0 Data
* **Symptom**: You log in as a Trekker or Coordinator and the page says "No bookings yet" or shows `0` metrics despite data existing in the database.
* **Cause**: Key mismatch between the backend response keys and the frontend Vue state attributes.
* **Solution**: Keep the frontend `app.js` data-parsing logic robust. For example:
  - Trekker Bookings: Use `data.booking_history || data.booking_history_records`
  - Admin Metrics: Use `data.admin_dashboard_metrics || data`
  - Staff Dashboard: Map metrics cleanly from `assigned_expedition_counts_by_status`.

---

## 🎭 Part 3: How to Give a Walkthrough of the App

To present a professional, end-to-end demonstration of the platform, follow this role-based walkthrough script.

### 🏁 Step 0: Prep the Database with Clean Demo Data
To save time during the live demo, seed the SQLite database with one Trekker account, one Staff account, and a scheduled expedition:
1. Create a script named `seed_demo.py` in the `backend/` directory:
   ```python
   import datetime
   from app import create_flask_application
   from app.extensions import database_extension as db
   from app.models import PlatformUserAccount, TrekkingRouteExpedition, ParticipantBookingRecord, UserPlatformRole, ExpeditionDifficultyLevel, ExpeditionLifecycleStatus, BookingLifecycleStatus
   
   app = create_flask_application("development")
   with app.app_context():
       ParticipantBookingRecord.query.delete()
       TrekkingRouteExpedition.query.delete()
       PlatformUserAccount.query.filter(PlatformUserAccount.assigned_platform_role != UserPlatformRole.ADMIN).delete()
       
       # Seed Staff Coordinator
       staff = PlatformUserAccount(user_full_name="Jane Staff", user_email_address="jane@trekapp.com", assigned_platform_role=UserPlatformRole.STAFF, is_account_active=True, is_account_blacklisted=False)
       staff.set_hashed_password("StaffPassword123!")
       db.session.add(staff)
       
       # Seed Trekker
       trekker = PlatformUserAccount(user_full_name="John Trekker", user_email_address="john@trekapp.com", assigned_platform_role=UserPlatformRole.TREKKER, is_account_active=True, is_account_blacklisted=False)
       trekker.set_hashed_password("TrekkerPassword123!")
       db.session.add(trekker)
       db.session.commit()
       print("Demo database successfully seeded!")
   ```
2. Run it: `python seed_demo.py`, then delete the file.

---

### 👑 Phase 1: The Admin Walkthrough (Full System Control)
**Goal**: Show how the administrator creates staff, manages users, schedules treks, and monitors platform health.

1. **Log In as Admin**:
   - Credentials: `admin@trekapp.com` / `Admin@SecurePass123`
2. **Dashboard Overview**:
   - Point out the metrics cards (**Total Expeditions**, **Registered Users**, **Trek Staff**, **Total Bookings**).
   - Point out the interactive charts displaying popular treks and bookings over time (powered by Chart.js).
3. **Staff & User Management**:
   - Click the **Users** tab in the sidebar. Show that `Jane Staff` and `John Trekker` are listed here.
   - Point out the **Ban** action button—explain that this is a soft-ban mechanism that prevents login but preserves historical audit trails.
4. **Create a Scheduled Expedition**:
   - Navigate to the **Expeditions** tab.
   - Click **Add Expedition** (or **Create Expedition**).
   - Fill in details:
     - Name: `Roopkund Mystery Lake`
     - Geographical Location: `Uttarakhand, India`
     - Difficulty: `Moderate`
     - Duration: `8 days`
     - Capacity: `15 slots`
     - Start Date: `2026-08-01`
     - End Date: `2026-08-09`
     - Cutoff Date: `2026-07-25`
     - Price: `15000`
     - Staff Assignment: Select `Jane Staff` from the dropdown list.
   - Save the record. Point out that new expeditions are set to **Pending** status by default for administrative safety review.
5. **Approve and Open the Expedition**:
   - Click **Edit** on the Roopkund expedition, update its lifecycle status to **Open**, and save. Explain that this publishes the slots to the public search API.

---

### 🧗 Phase 2: The Trekker Walkthrough (Self-Service Experience)
**Goal**: Show how a customer registers, browses treks, makes a booking, and interacts with their dashboard.

1. **Log In as Trekker**:
   - Log out of Admin and sign in as: `john@trekapp.com` / `TrekkerPassword123!`.
2. **Explore Expeditions**:
   - Point out the welcome card personalized with John's name.
   - Go to the **Explore Treks** tab. Highlight the **live search filters**: filter by "Moderate" difficulty or type "India".
   - *Technical Note to mention*: Explain that the search results are cached in Redis for 5 minutes to minimize database load.
3. **Make a Booking**:
   - Click **Book Now** on the `"Roopkund Mystery Lake"` card.
   - Enter `1` participant and add a special note (e.g., *"Requesting vegetarian meals"*).
   - Complete the booking flow.
4. **Review Bookings History**:
   - Navigate to the **My Bookings** tab. Show that the booking is listed under **Upcoming** with status `Booked`.
   - Point out the aggregated metrics cards on the Trekker dashboard showing active bookings, total spent (`15,000 INR`), and completed treks.

---

### 🗂️ Phase 3: The Coordinator/Staff Walkthrough (Operational Field Updates)
**Goal**: Show how the field staff manages slot availability, updates expedition progress, and views rosters.

1. **Log In as Staff**:
   - Log out of Trekker and sign in as: `jane@trekapp.com` / `StaffPassword123!`.
2. **Dashboard Overview**:
   - Show that Jane sees only her own assigned expeditions: **Assigned Treks = 1**, **Total Participants = 1**. Explain this ensures strict data access control.
3. **Operational Update**:
   - Click the **Manage** button on the `"Roopkund Mystery Lake"` assigned expedition.
   - Change the remaining slots from `14` to `12` (explain that staff can adjust slot counts to correct real-world discrepancies like no-shows).
   - Submit the update and show that the dashboard metrics and available slots dynamically refresh to `12 slots left`.
4. **View Participant Roster**:
   - Click **View Participants** to see the roster of confirmed hikers. Point out that `John Trekker` is visible, along with his contact details and special request note.

---

### 📊 Phase 4: Async Operations & CSV Export (The Celery Layer)
**Goal**: Show the architecture handling background processing.

1. **Trigger CSV Export**:
   - Go back to the Trekker Dashboard (`john@trekapp.com`).
   - Click **Export History to CSV**.
   - Show the toast message: *"Your booking history CSV export has been queued..."*.
   - *Technical explanation*: Mention that for large user profiles, generating files synchronously blocks the web request thread. By delegating this to a **Celery Worker** in the background, the UI remains fully responsive.
2. **Check Logs**:
   - Show the Celery Worker terminal logs executing the task in the background and generating the report.
