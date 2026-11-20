# 🌍 EarthScape Climate Agency — Web Application

> **Real-time climate monitoring, forecasting, and alerting platform built with Flask + MongoDB.**

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)
![Flask](https://img.shields.io/badge/Flask-3.x-green?logo=flask)
![MongoDB](https://img.shields.io/badge/MongoDB-7.x-brightgreen?logo=mongodb)
![Chart.js](https://img.shields.io/badge/Chart.js-4.x-orange)
![Bootstrap](https://img.shields.io/badge/Bootstrap-5.3-purple?logo=bootstrap)

---

## 📋 Overview

EarthScape Climate Agency is a comprehensive web application that provides climate analysts and administrators with tools to:

- **Monitor** global temperature anomalies, CO₂ concentrations, and ENSO (ONI) indices
- **Visualize** historical trends (1880–2026) with interactive Chart.js dashboards
- **Forecast** future temperature anomalies using ARIMA/ETS models (12-month horizon)
- **Detect** anomalies and trigger threshold-based alerts in real time
- **Manage** users, settings, and data through a role-based admin panel
- **Process** large climate datasets using PySpark (Hadoop-equivalent batch processing)

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🏠 **Landing Page** | Public-facing page with KPI stats band, mission overview, and CTA |
| 📊 **Dashboard** | Interactive charts for temperature history, CO₂, dual-axis correlations |
| 🔮 **Forecast** | 12-month forecast with confidence bands and threshold lines |
| 🔴 **Live Monitor** | Real-time sensor feed simulation with spike detection & quarantine |
| ⚠️ **Alerts** | Auto-generated alerts for threshold breaches, anomalies, ENSO extremes |
| 👤 **User Roles** | Admin (full CRUD) and Analyst (read + limited write) |
| ⚙️ **Settings** | Configurable thresholds, forecast horizon, alert preferences |
| 📤 **Export** | Backup all collections to timestamped JSON files |
| 🎨 **Earth Theme** | Custom "Earth & Forest" design system with Fraunces + Nunito Sans |

---

## 🛠 Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.10+, Flask 3.x, Flask-Login, Flask-WTF |
| **Database** | MongoDB 7.x with PyMongo |
| **Frontend** | Bootstrap 5.3, Chart.js 4.x, Jinja2 templates |
| **Big Data** | PySpark (Hadoop-equivalent; see [Assumptions](#assumptions)) |
| **Auth** | Werkzeug password hashing, session-based login |
| **Env Config** | python-dotenv (.env file) |

---

## 📁 Folder Structure

```
earthscape_website/
├── app.py                      # Flask application factory & routes
├── config.py                   # Configuration classes (Dev/Prod)
├── requirements.txt            # Python dependencies
├── .env                        # Environment variables (not in git)
├── README.md                   # ← You are here
├── USER_GUIDE.md               # Step-by-step usage guide
│
├── models/                     # Data models & DB helpers
│   ├── __init__.py
│   ├── user.py                 # User model (Flask-Login)
│   ├── climate_data.py         # Climate CRUD operations
│   └── forecast.py             # Forecast CRUD operations
│
├── routes/                     # Flask Blueprints
│   ├── __init__.py
│   ├── auth.py                 # Login / logout / register
│   ├── dashboard.py            # Dashboard views
│   ├── api.py                  # JSON API endpoints
│   ├── alerts.py               # Alert management
│   ├── admin.py                # Admin panel
│   └── forecast.py             # Forecast views
│
├── templates/                  # Jinja2 HTML templates
│   ├── base.html               # Master layout
│   ├── index.html              # Landing page
│   ├── login.html              # Login page
│   ├── dashboard.html          # Main dashboard
│   ├── history.html            # Historical data explorer
│   ├── forecast.html           # Forecast view
│   ├── live.html               # Live monitor
│   ├── alerts.html             # Alert list
│   ├── settings.html           # Settings panel
│   └── admin/                  # Admin sub-templates
│       ├── users.html
│       └── data.html
│
├── static/
│   ├── css/
│   │   └── style.css           # Earth & Forest theme
│   ├── js/
│   │   └── charts.js           # Chart.js initialization
│   └── img/                    # Static images
│
├── scripts/
│   ├── load_data.py            # Synthetic data generator & loader
│   ├── create_admin.py         # Create default admin/analyst users
│   ├── export_backup.py        # Export all collections to JSON
│   └── spark_batch.py          # PySpark batch processing job
│
├── spark_jobs/                 # PySpark job definitions
│   └── anomaly_detection.py
│
├── backups/                    # Auto-generated backup directory
│   └── backup_YYYYMMDD_HHMMSS/
│
└── tests/                      # Unit & integration tests
    ├── test_routes.py
    └── test_models.py
```

---

## 🚀 Installation (Windows)

### Prerequisites

- **Python 3.10+** — [Download](https://www.python.org/downloads/)
- **MongoDB 7.x** — [Download Community](https://www.mongodb.com/try/download/community) or use MongoDB Atlas
- **Git** — [Download](https://git-scm.com/download/win)

### Step-by-Step Setup

```powershell
# 1. Clone / navigate to the project
cd "C:\Users\asp.APTECHNK1\Desktop\climate weather e-project"

# 2. Create a virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r earthscape_website\requirements.txt

# 4. Configure environment
#    Copy the example and edit values:
copy earthscape_website\.env.example earthscape_website\.env
#    Edit .env with your MongoDB URI, secret key, etc.

# 5. Ensure MongoDB is running
#    (If using local MongoDB)
net start MongoDB
#    Or start mongod manually

# 6. Load synthetic data
cd earthscape_website
python scripts/load_data.py

# 7. Create default users
python scripts/create_admin.py

# 8. Run the application
python app.py
```

The app will start at **http://127.0.0.1:5000**

---

## 🔐 Environment Setup (.env)

Create a `.env` file in `earthscape_website/`:

```ini
# Flask
FLASK_SECRET_KEY=your-super-secret-key-change-me
FLASK_ENV=development
FLASK_DEBUG=1

# MongoDB
MONGO_URI=mongodb://localhost:27017/earthscape

# PySpark (optional)
SPARK_MASTER=local[*]
SPARK_APP_NAME=EarthScapeClimate

# Alert Settings
ALERT_THRESHOLD=1.50
```

---

## 👤 Default Admin Credentials

| Username | Password | Role |
|----------|----------|------|
| `admin` | `Admin@123` | Admin |
| `analyst` | `Analyst@123` | Analyst |

> [!CAUTION]
> **Change default passwords immediately in production environments!**

---

## 📡 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/chart/history` | GET | Temperature + CO₂ time series (supports `start_year`, `end_year` params) |
| `/api/chart/forecast` | GET | 12-month forecast with confidence bands |
| `/api/alerts` | GET | Active alerts list |
| `/api/settings` | GET/POST | Read/update application settings |
| `/api/kpi` | GET | Dashboard KPI summary |

---

## 🔮 12-Month Forecast (Nov 2026 → Oct 2027)

| Month | Forecast (°C) | Lower Bound | Upper Bound | Status |
|-------|--------------|-------------|-------------|--------|
| 2026-11 | 1.501 | 1.335 | 1.667 | 🔴 Above threshold |
| 2026-12 | 1.540 | 1.334 | 1.747 | 🔴 Above threshold |
| 2027-01 | 1.527 | 1.295 | 1.758 | 🔴 Above threshold |
| 2027-02 | 1.496 | 1.263 | 1.729 | 🟡 Near threshold |
| 2027-03 | 1.476 | 1.242 | 1.709 | 🟡 Near threshold |
| 2027-04 | 1.393 | 1.160 | 1.626 | 🟢 Below threshold |
| 2027-05 | 1.356 | 1.123 | 1.589 | 🟢 Below threshold |
| 2027-06 | 1.345 | 1.111 | 1.580 | 🟢 Below threshold |
| 2027-07 | 1.348 | 1.101 | 1.594 | 🟢 Below threshold |
| 2027-08 | 1.332 | 1.079 | 1.585 | 🟢 Below threshold |
| 2027-09 | 1.345 | 1.092 | 1.598 | 🟢 Below threshold |
| 2027-10 | 1.353 | 1.099 | 1.606 | 🟢 Below threshold |

Threshold = **1.50 °C** (configurable in Settings).

---

## 🔄 Assumptions

### Hadoop → PySpark

The original SRS specifies **Hadoop** for big-data processing. This implementation uses **PySpark** as a modern, functionally equivalent alternative:

| SRS Requirement | Implementation |
|----------------|----------------|
| Hadoop MapReduce batch jobs | PySpark batch processing (`spark_batch.py`) |
| HDFS data storage | MongoDB collections (accessible via PySpark MongoDB connector) |
| Hive queries | PySpark SQL DataFrames |
| Cluster processing | `local[*]` mode (scales to cluster with config change) |

**Rationale:** PySpark provides the same distributed computing capabilities with simpler setup, native Python integration, and direct MongoDB connectivity — eliminating the need for a full Hadoop cluster in development.

---

## 📋 SRS Traceability Matrix

| SRS ID | Requirement | Implementation | Status |
|--------|-------------|----------------|--------|
| FR-01 | User authentication & role-based access | Flask-Login + MongoDB users collection | ✅ |
| FR-02 | Dashboard with real-time KPIs | `/dashboard` route + Chart.js | ✅ |
| FR-03 | Historical climate data visualization | `/history` + `/api/chart/history` | ✅ |
| FR-04 | Temperature anomaly detection | `is_anomaly` flag + statistical residual | ✅ |
| FR-05 | CO₂ concentration tracking | Keeling curve data + CO₂ chart | ✅ |
| FR-06 | ENSO (ONI) index monitoring | ONI values in monthly_climate | ✅ |
| FR-07 | 12-month temperature forecast | ARIMA/ETS → forecast collection | ✅ |
| FR-08 | Threshold-based alerting | Configurable threshold + auto-alerts | ✅ |
| FR-09 | Big data batch processing | PySpark jobs (Hadoop equivalent) | ✅ |
| FR-10 | Live sensor monitoring | `/live` page + simulated feed | ✅ |
| FR-11 | Data export & backup | `export_backup.py` → JSON files | ✅ |
| FR-12 | Admin user management | CRUD via `/admin/users` | ✅ |
| FR-13 | Settings management | `/settings` + DB persistence | ✅ |
| NFR-01 | Responsive UI | Bootstrap 5 responsive grid | ✅ |
| NFR-02 | Secure password storage | Werkzeug PBKDF2 hashing | ✅ |
| NFR-03 | CSRF protection | Flask-WTF CSRF tokens | ✅ |
| NFR-04 | Environment-based config | python-dotenv .env file | ✅ |

---

## 🔒 Security Notes

- **Passwords** are hashed using Werkzeug's PBKDF2-SHA256 (never stored in plain text)
- **Sessions** use Flask's signed cookies with `FLASK_SECRET_KEY`
- **CSRF** protection enabled on all forms via Flask-WTF
- **Role checks** enforce admin-only access to user management and settings
- **Input validation** on all form submissions
- **MongoDB injection** mitigated via PyMongo's parameterized queries
- `.env` file excluded from version control (add to `.gitignore`)

---

## 🧪 Test Data

The `load_data.py` script generates:

| Collection | Records | Description |
|------------|---------|-------------|
| `monthly_climate` | ~1,762 | Monthly temp anomaly, CO₂, ONI (1880–2026) |
| `forecast` | 12 | Temperature forecast (Nov 2026 – Oct 2027) |
| `alerts` | ~20–40 | Auto-generated from recent breaches |
| `settings` | 1 | Global configuration document |
| `users` | 2 | Admin + Analyst (via `create_admin.py`) |

Data uses **UPSERT** operations — safe to re-run without creating duplicates.

---

## 🎬 Demo Video Script

For a 5–7 minute walkthrough:

| Time | Section | What to Show |
|------|---------|-------------|
| 0:00 | Intro | Project overview, tech stack slide |
| 0:30 | Landing Page | Scroll through public page, KPI stats band |
| 1:00 | Login | Login as admin, show auth flow |
| 1:30 | Dashboard | KPI cards, temperature history chart, year filter, chart type toggle |
| 2:30 | CO₂ & Dual-Axis | Switch to CO₂ tab, show dual-axis correlation |
| 3:00 | Forecast | Forecast chart with confidence bands, threshold line |
| 3:30 | Live Monitor | Start live feed, show spike detection, pause/resume |
| 4:00 | Alerts | Show alert list, severity badges, acknowledge action |
| 4:30 | Settings | Change threshold, show effect on alerts |
| 5:00 | Admin Panel | User management CRUD, role assignment |
| 5:30 | PySpark Job | Run `spark_batch.py`, show output |
| 6:00 | Export | Run `export_backup.py`, show JSON files |
| 6:30 | Wrap-up | Summary, SRS traceability, Q&A |

---

## 📄 License

This project is developed for academic/educational purposes as part of the Climate Weather E-Project.

---

<p align="center">
  <strong>🌱 EarthScape Climate Agency — Monitoring Our Planet's Pulse</strong>
</p>
