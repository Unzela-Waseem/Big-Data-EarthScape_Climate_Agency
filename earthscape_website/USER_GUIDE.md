# 📖 EarthScape Climate Agency — User Guide

> Step-by-step instructions for Admins and Analysts.

---

## Table of Contents

1. [Getting Started](#1-getting-started)
2. [Logging In](#2-logging-in)
3. [Dashboard Overview](#3-dashboard-overview)
4. [Historical Data Explorer](#4-historical-data-explorer)
5. [Forecast View](#5-forecast-view)
6. [Live Monitor](#6-live-monitor)
7. [Alerts Management](#7-alerts-management)
8. [Settings (Admin)](#8-settings-admin)
9. [User Management (Admin)](#9-user-management-admin)
10. [Data Export & Backup](#10-data-export--backup)
11. [Permission Reference](#11-permission-reference)
12. [FAQ](#12-faq)

---

## 1. Getting Started

### First-Time Setup

1. Ensure the application is running (`python app.py`)
2. Open your browser and navigate to **http://127.0.0.1:5000**
3. You will see the **Landing Page** with public climate statistics
4. Click **Login** in the navigation bar to access the full platform

### Default Accounts

| Username | Password | Role |
|----------|----------|------|
| `admin` | `Admin@123` | Administrator |
| `analyst` | `Analyst@123` | Climate Analyst |

> [!IMPORTANT]
> Change the default passwords after your first login via the Admin panel.

---

## 2. Logging In

1. Navigate to **http://127.0.0.1:5000/login**
2. Enter your **Username** and **Password**
3. Click the **Sign In** button
4. On success, you will be redirected to the **Dashboard**

**If login fails:**
- Verify your credentials are correct (passwords are case-sensitive)
- Contact your administrator if your account is locked or inactive
- Check that the MongoDB database is running

---

## 3. Dashboard Overview

The dashboard is your primary hub, showing key climate metrics at a glance.

### KPI Cards (Top Row)

| Card | Description |
|------|-------------|
| 🌡️ **Latest Temp Anomaly** | Most recent monthly temperature anomaly (°C) |
| 🏭 **Latest CO₂** | Current atmospheric CO₂ concentration (ppm) |
| 🌊 **Current ONI** | El Niño Southern Oscillation index |
| ⚠️ **Active Alerts** | Number of unacknowledged alerts |

### Charts

- **Temperature History** — Full historical temperature anomaly trend (1880–present)
- **CO₂ Concentration** — Atmospheric CO₂ levels (1958–present)
- **GHG Composition** — Greenhouse gas breakdown (bar chart)

### Using Filters

1. Set the **Start Year** and **End Year** in the filter bar
2. Click **Apply Filter** to zoom into a specific time range
3. Use the **Chart Type** dropdown to switch between Line and Bar views
4. Click **Reset** to return to the full date range

---

## 4. Historical Data Explorer

**Path:** Dashboard → History (sidebar)

This page provides detailed exploration of historical climate data.

### Features

- **Temperature vs CO₂ dual-axis chart** — See the correlation between warming and CO₂
- **Data table** — Sortable, paginated view of all monthly records
- **Year range filter** — Focus on specific decades or periods
- **Anomaly highlighting** — Flagged records shown with red triangles on charts

### How to Use

1. Click **History** in the sidebar
2. Use the year filters to narrow your view
3. Toggle between **Line** and **Bar** chart types
4. Scroll down to see the data table
5. Click column headers to sort

---

## 5. Forecast View

**Path:** Dashboard → Forecast (sidebar)

Shows the 12-month temperature forecast with confidence intervals.

### Reading the Forecast Chart

| Element | Meaning |
|---------|---------|
| **Solid pine line** | Central forecast value |
| **Green shaded band** | 95% confidence interval (lower to upper bound) |
| **Red dashed line** | Alert threshold (default: 1.50°C) |

### Forecast Table

Below the chart, a detailed table shows:
- **Month** — Forecast period
- **Forecast** — Predicted temperature anomaly
- **Lower / Upper** — Confidence bounds
- **Status** — Whether the forecast exceeds the threshold

> [!NOTE]
> Rows where the forecast exceeds the threshold are highlighted in red.

---

## 6. Live Monitor

**Path:** Dashboard → Live (sidebar)

Simulates a real-time sensor feed for temperature monitoring.

### Controls

| Button | Action |
|--------|--------|
| **Start / Resume** | Begin the live data feed |
| **Pause** | Stop the feed without clearing data |
| **Threshold input** | Set the spike detection threshold |

### Spike Detection

- Points exceeding the threshold appear as **red dots** on the chart
- The **Spike Counter** in the top-right tracks total detected spikes
- Spikes are automatically "quarantined" (flagged for review)

### How It Works

1. Navigate to the **Live** page
2. The feed starts automatically
3. Watch for red dots indicating threshold breaches
4. Use **Pause** to freeze the display for analysis
5. Adjust the threshold value to change sensitivity

---

## 7. Alerts Management

**Path:** Dashboard → Alerts (sidebar)

### Alert Types

| Type | Icon | Description |
|------|------|-------------|
| **Threshold Breach** | 🔴 | Temperature exceeded configured threshold |
| **Statistical Anomaly** | 🟡 | Unusual deviation detected |
| **ENSO Extreme** | 🟡 | Strong El Niño or La Niña event |

### Alert Severity

| Severity | Badge Color | Meaning |
|----------|-------------|---------|
| **Critical** | Red | Immediate attention required |
| **Warning** | Orange | Monitor closely |
| **Info** | Green | Informational |

### Managing Alerts

1. View all alerts sorted by date (newest first)
2. Click **Acknowledge** to mark an alert as reviewed
3. Use the severity filter to focus on critical alerts
4. Acknowledged alerts move to the "Resolved" tab

> [!TIP]
> Set up alert email notifications in **Settings** to receive threshold breach alerts automatically.

---

## 8. Settings (Admin)

**Path:** Dashboard → Settings (sidebar) — *Admin only*

### Configurable Options

| Setting | Default | Description |
|---------|---------|-------------|
| **Alert Threshold** | 1.50 °C | Temperature anomaly threshold for alerts |
| **Forecast Horizon** | 12 months | Number of months to forecast |
| **Live Refresh Rate** | 2 seconds | Interval for live feed updates |
| **Alert Email** | (empty) | Email address for alert notifications |
| **Email Alerts** | Off | Enable/disable email notifications |

### How to Update

1. Navigate to **Settings**
2. Modify the desired values
3. Click **Save Settings**
4. A confirmation message appears on success

> [!WARNING]
> Changing the threshold will regenerate alerts. Existing acknowledged alerts are not affected.

---

## 9. User Management (Admin)

**Path:** Dashboard → Admin → Users — *Admin only*

### View Users

A table listing all registered users with:
- Username, email, role, status
- Created/updated timestamps
- Action buttons (Edit / Deactivate)

### Create a New User

1. Click **Add User**
2. Fill in: Username, Email, Full Name, Password, Role
3. Click **Create**
4. Share credentials securely with the new user

### Edit a User

1. Click **Edit** next to the user
2. Modify fields (leave password blank to keep existing)
3. Click **Update**

### Deactivate a User

1. Click **Deactivate** next to the user
2. Confirm the action
3. The user will no longer be able to log in

> [!CAUTION]
> Deactivating the last admin account will lock you out! Always ensure at least one active admin exists.

---

## 10. Data Export & Backup

### From the Command Line

```powershell
cd earthscape_website
python scripts/export_backup.py
```

This creates a timestamped folder in `backups/` containing JSON files for every collection:

```
backups/
└── backup_20261120_143000/
    ├── monthly_climate.json
    ├── forecast.json
    ├── alerts.json
    ├── settings.json
    ├── users.json
    └── _backup_meta.json
```

### Restoring from Backup

1. Open MongoDB shell or Compass
2. Import the JSON files from the backup folder
3. Use `mongoimport` for bulk restoration:

```powershell
mongoimport --db earthscape --collection monthly_climate --file backup_folder/monthly_climate.json --jsonArray
```

---

## 11. Permission Reference

### Role-Based Access Matrix

| Feature | Admin | Analyst | Public (not logged in) |
|---------|:-----:|:-------:|:-----:|
| Landing Page | ✅ | ✅ | ✅ |
| Login / Logout | ✅ | ✅ | ✅ |
| Dashboard | ✅ | ✅ | ❌ |
| Historical Data | ✅ | ✅ | ❌ |
| Forecast View | ✅ | ✅ | ❌ |
| Live Monitor | ✅ | ✅ | ❌ |
| View Alerts | ✅ | ✅ | ❌ |
| Acknowledge Alerts | ✅ | ✅ | ❌ |
| Settings (view) | ✅ | 🔒 Read-only | ❌ |
| Settings (edit) | ✅ | ❌ | ❌ |
| User Management | ✅ | ❌ | ❌ |
| Create Users | ✅ | ❌ | ❌ |
| Edit/Deactivate Users | ✅ | ❌ | ❌ |
| Data Export | ✅ | ❌ | ❌ |
| API Access | ✅ | ✅ | ❌ |

---

## 12. FAQ

### General

**Q: What browser should I use?**
A: Any modern browser — Chrome, Firefox, Edge, or Safari. We recommend Chrome or Edge for the best Chart.js rendering performance.

**Q: Can multiple users be logged in at the same time?**
A: Yes, Flask sessions are per-browser. Multiple users can access the system simultaneously.

**Q: How often is the data updated?**
A: The synthetic test data covers 1880–2026. In production, you would configure a data pipeline to ingest real climate data monthly.

### Charts

**Q: Why is the CO₂ chart empty before 1958?**
A: Systematic CO₂ measurements began in 1958 with the Keeling Curve at Mauna Loa Observatory. Pre-1958 data is set to null.

**Q: Can I export the charts as images?**
A: Right-click on any chart and select "Save Image As…" to save a PNG snapshot.

**Q: What do the red triangles on the temperature chart mean?**
A: They indicate statistically flagged anomalies — months where the temperature deviation was unusually high relative to the trend.

### Live Monitor

**Q: Is the live feed real sensor data?**
A: In this demo, it uses simulated data from historical records. In production, you would connect to real MQTT/WebSocket sensor feeds.

**Q: What happens to quarantined spikes?**
A: Spikes are visually flagged (red dots) and counted. In a production system, they would be logged and trigger alert workflows.

### Administration

**Q: How do I reset a user's password?**
A: As an admin, go to Admin → Users → Edit the user → Enter a new password → Update.

**Q: Can I add more roles beyond Admin and Analyst?**
A: The current system supports two roles. Additional roles can be added by extending the `role` field in the User model and adding corresponding permission checks.

**Q: How do I reload the test data?**
A: Run `python scripts/load_data.py` again. It uses UPSERT operations, so it safely updates existing records without creating duplicates.

### Troubleshooting

**Q: The app won't start — "Connection refused" error**
A: Ensure MongoDB is running. On Windows: `net start MongoDB` or start `mongod.exe` manually.

**Q: Charts are not loading**
A: Check the browser console (F12) for errors. Ensure the Flask server is running and the API endpoints are accessible.

**Q: "CSRF token missing" error on form submission**
A: Clear your browser cookies and log in again. This can happen if the session expires.

---

<p align="center">
  <em>For additional support, contact the EarthScape development team.</em>
</p>
