# 🏔️ Trekking Management Application V2

A comprehensive, multi-role Progressive Web Application (PWA) designed to streamline trekking operations. The system manages trekking routes, expeditions, bookings, staff allocations, and automated communications.

Built using a **Flask (Python) RESTful API** backend, a responsive **HTML5/Vanilla CSS/JavaScript (Vue.js CDN)** frontend, **Redis** caching, and **Celery** background workers.

---

##  Key Features

###  Multi-Role Dashboard Architecture
- **Admin Dashboard**:
  - Full CRUD operations on trekking routes and expeditions.
  - User and staff account management (including deactivation/blacklisting).
  - Visual analytics dashboard with charts (popular treks, user participation).
- **Trek Staff Dashboard**:
  - View and manage assigned expeditions.
  - Track registered participants per trek.
  - Update slots, meeting details, and operational status (e.g., mark as Started/Completed).
- **Trekker (Client) Dashboard**:
  - Browse and search available treks with real-time status indicators.
  - Book slot allocations with a simulated payment gateway.
  - View booking history and export personal booking records as CSV.

###  Transactional Slot Integrity
- Implements strict transaction locks to **prevent overbooking** beyond capacity.
- Automates lifecycle status transitions (e.g., automatically marks a trek as `Closed` when capacity is reached and re-opens it if a booking is cancelled).

###  Caching & Performance
- **Redis caching** is applied on heavily accessed public trek discovery endpoints.
- Features active cache invalidation hooks triggered upon admin changes, new bookings, or cancellations to ensure users always see accurate slot counts.

###  Asynchronous Tasks (Celery & Redis)
- **Daily Reminders**: Scheduled Celery Beat job enqueued daily at 08:00 IST to notify confirmed trekkers of upcoming treks starting within 48 hours via email/Google Chat webhook.
- **Monthly Admin Reports**: Automated report compiled on the 1st of every month summarizing monthly registrations, bookings, and revenue, delivered to the admin via email.
- **CSV Export**: User-triggered background task that generates a CSV of a trekker's booking history and emails it to them once ready.

###  Progressive Web App (PWA)
- Fully offline-capable using a **Cache-First service worker strategy** with an offline fallback page.
- Seamless "Add to Home Screen" support with high-resolution app icons and manifest file.

---

##  Technology Stack

- **Backend API**: Python 3.12, Flask, Flask-CORS, Flask-JWT-Extended
- **Database**: SQLite (SQLAlchemy ORM)
- **Caching & Message Broker**: Redis
- **Background Jobs**: Celery, Celery Beat
- **Frontend SPA**: Vue.js 3 (CDN-based), ChartJS (Analytics)
- **Styling**: Vanilla CSS, Bootstrap 5 (Glassmorphism & deep forest theme integration)

---

## 📂 Directory Structure

```text
trekking-app-v2/
├── backend/
│   ├── app/
│   │   ├── __init__.py          # Flask app initialization and blueprint registration
│   │   ├── config.py            # Environment configurations (dev, test, production)
│   │   ├── extensions.py        # Database, cache, and celery instantiation
│   │   ├── models.py            # SQLAlchemy database models for users, treks, and bookings
│   │   ├── schemas.py           # Marshmallow schemas for validating request data
│   │   ├── auth_routes.py       # User authentication, registration, and profile updates
│   │   ├── admin_routes.py      # Admin controllers for routes, staff creation, and blacklisting
│   │   ├── staff_routes.py      # Staff routes for updating statuses and viewing rosters
│   │   ├── trekker_routes.py    # Trekker routes for searching, booking, and cancelling treks
│   │   └── tasks.py             # Celery background tasks for emails and reports
│   ├── instance/
│   │   └── trekking_platform.db # Main SQLite database file
│   ├── celery_worker.py         # Entry point to run the Celery worker
│   ├── run.py                   # Entry point to run the Flask backend server
│   ├── requirements.txt         # List of Python dependencies
│   └── .env                     # App configurations (secrets, SMTP settings, etc.)
├── frontend/
│   ├── index.html               # Main HTML entry file for the Vue.js app
│   ├── app.js                   # Main JavaScript file containing Vue logic and API calls
│   ├── index.css                # Styling stylesheet (Bootstrap customizations and glassmorphism)
│   ├── manifest.json            # PWA manifest configuration
│   ├── sw.js                    # Service worker for offline caching and fallbacks
│   ├── offline.html             # Offline fallback page
│   └── assets/                  # High-resolution icons and branding logos
├── Project_Report.pdf           # Detailed project report in PDF format
└── README.md                    # Project run guide and overview document
```

---

##  Setup & Run Instructions

### 1. Prerequisites
Ensure you have the following installed on your machine:
- Python 3.10+
- WSL (Windows Subsystem for Linux) with **Redis** installed

---

### 2. Backend Setup
1. Open a PowerShell/Terminal window and navigate to the backend folder:
   ```bash
   cd backend
   ```
2. Create a virtual environment and activate it:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
3. Install all python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Verify your `.env` configuration exists. The backend automatically loads settings from `.env`. The database will auto-create and seed an administrator account on first boot.

---

### 3. Start Redis (WSL)
Open your WSL/Ubuntu terminal (or run directly in PowerShell if WSL is configured) and start the Redis service:
```bash
# Update Redis config to bind to 0.0.0.0 and turn off protected mode (allows Windows connection)
sudo sed -i 's/^bind.*/bind 0.0.0.0/' /etc/redis/redis.conf
sudo sed -i 's/^protected-mode.*/protected-mode no/' /etc/redis/redis.conf

# Start the service
sudo service redis-server start
```
*(Verify it is active by running `redis-cli ping` which should return `PONG`).*

---

### 4. Running the Application Services
For local development, keep the following processes running in separate terminals:

*   **Flask API Server (Terminal 1)**:
    ```powershell
    cd backend
    .\.venv\Scripts\Activate.ps1
    python run.py
    ```
    *Runs on `http://127.0.0.1:5000`.*

*   **Frontend HTTP Server (Terminal 2)**:
    ```powershell
    cd frontend
    python -m http.server 5501 --bind 127.0.0.1
    ```
    *Serves the web client at `http://127.0.0.1:5501/index.html`.*

*   **Celery Worker Task Queue (Terminal 3)**:
    ```powershell
    cd backend
    .\.venv\Scripts\Activate.ps1
    python -m celery -A celery_worker.celery_task_queue worker --loglevel=info -P solo
    ```

*   **Celery Beat Scheduler (Terminal 4)**:
    ```powershell
    cd backend
    .\.venv\Scripts\Activate.ps1
    python -m celery -A celery_worker.celery_task_queue beat --loglevel=info
    ```

---


## 🔑 Login Credentials

The application seeds a default administrator on initialization:
- **Default Admin Email**: `admin@trekapp.com`
- **Default Admin Password**: `Admin@SecurePass123`

To test the application:
1. Navigate to **[http://127.0.0.1:5501/index.html](http://127.0.0.1:5501/index.html)** in Chrome.
2. Log in using the admin credentials.
3. Create a **Staff Account** from the Admin interface.
4. Log out and register a new **Trekker Account** or log in with the newly created **Staff Account**.