# 🏔️ Trekking Management Application V2

A comprehensive, multi-role Progressive Web Application (PWA) designed to streamline trekking operations. The system manages trekking routes, expeditions, bookings, staff allocations, and automated communications.

Built using a **Flask (Python) RESTful API** backend, a responsive **HTML5/Vanilla CSS/JavaScript (Vue.js CDN)** frontend, **Redis** caching, and **Celery** background workers.

---

## 🌟 Key Features

### 👤 Multi-Role Dashboard Architecture
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

### 🛡️ Transactional Slot Integrity
- Implements strict transaction locks to **prevent overbooking** beyond capacity.
- Automates lifecycle status transitions (e.g., automatically marks a trek as `Closed` when capacity is reached and re-opens it if a booking is cancelled).

### ⚡ Caching & Performance
- **Redis caching** is applied on heavily accessed public trek discovery endpoints.
- Features active cache invalidation hooks triggered upon admin changes, new bookings, or cancellations to ensure users always see accurate slot counts.

### 🤖 Asynchronous Tasks (Celery & Redis)
- **Daily Reminders**: Scheduled Celery Beat job enqueued daily at 08:00 IST to notify confirmed trekkers of upcoming treks starting within 48 hours via email/Google Chat webhook.
- **Monthly Admin Reports**: Automated report compiled on the 1st of every month summarizing monthly registrations, bookings, and revenue, delivered to the admin via email.
- **CSV Export**: User-triggered background task that generates a CSV of a trekker's booking history and emails it to them once ready.

### 📱 Progressive Web App (PWA)
- Fully offline-capable using a **Cache-First service worker strategy** with an offline fallback page.
- Seamless "Add to Home Screen" support with high-resolution app icons and manifest file.

---

## 🛠️ Technology Stack

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
│   │   ├── __init__.py          # Application Factory & CORS configuration
│   │   ├── config.py            # Hierarchical environments config (Dev/Prod/Test)
│   │   ├── models.py            # SQLite database models & SQLAlchemy schemas
│   │   ├── auth_routes.py       # JWT Login, registration, and refresh endpoints
│   │   ├── admin_routes.py      # Route/Expedition CRUD & user blacklisting endpoints
│   │   ├── staff_routes.py      # Expedition status updates & participant checks
│   │   ├── trekker_routes.py    # Search, slot booking, and CSV triggers
│   │   ├── tasks.py             # Celery async tasks (Email reminder, PDF/HTML reports, CSV builder)
│   │   └── mail_utils.py        # Shared SMTP mail client
│   ├── instance/
│   │   └── trekking_platform.db # SQLite database file (auto-seeded on startup)
│   ├── celery_worker.py         # Celery client hook
│   ├── run.py                   # Main backend server entry point
│   ├── test_app.py              # Automated integration test suite
│   ├── requirements.txt         # Production library dependencies
│   └── .env                     # Local environment configurations (CORS, keys, ports)
├── frontend/
│   ├── index.html               # Main single page application index
│   ├── app.js                   # Client side controller, router & API services
│   ├── index.css                # Custom glassmorphism stylesheet
│   ├── manifest.json            # PWA manifest
│   ├── sw.js                    # Cache-First Service Worker
│   ├── offline.html             # Offline fallback page
│   └── assets/                  # App icons and graphics
├── Project_Report.md            # Mandatory project report document
└── README.md                    # Setup and application instructions
```

---

## 🚀 Setup & Run Instructions

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
    python -m http.server 8080 --bind 127.0.0.1
    ```
    *Serves the web client at `http://127.0.0.1:8080`.*

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

### 5. Running the Test Suite
To execute the automated API testing suite:
```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m unittest test_app.py
```
*(All tests use an isolated in-memory SQLite database configuration to verify endpoint responses without affecting your local database).*

---

## 🔑 Login Credentials

The application seeds a default administrator on initialization:
- **Default Admin Email**: `admin@trekapp.com`
- **Default Admin Password**: `Admin@SecurePass123`

To test the application:
1. Navigate to **[http://127.0.0.1:8080](http://127.0.0.1:8080)** in Chrome (preferably Incognito to bypass PWA caching).
2. Log in using the admin credentials.
3. Create a **Staff Account** from the Admin interface.
4. Log out and register a new **Trekker Account** or log in with the newly created **Staff Account**.

---

## 📜 AI Usage Declaration
This project was developed with the assistance of **Antigravity (Google DeepMind)**. 
AI assistance was utilized for:
- Initial database ER structuring.
- Refactoring service worker relative file caching paths.
- Debugging local loopback CORS bindings between WSL Redis and the Windows host system.
- Designing the custom CSS variables for the glassmorphism dark theme.
- Creating the automated API integration test coverage.
- Generating the PWA high-resolution image resources.