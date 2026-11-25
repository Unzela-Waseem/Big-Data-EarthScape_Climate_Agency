# EarthScape User Guide

This guide covers the web portal after an Admin has configured MongoDB, loaded the cleaned data, and created user accounts. The app has two roles: **Admin** and **Analyst**.

## Role permissions

| Action | Admin | Analyst |
|---|---:|---:|
| Dashboard, explorer, analysis, live monitor, predictions, forecast, alerts, model performance | Yes | Yes |
| Submit feedback and view own requests/replies | Yes | Yes |
| Change alert threshold, manage users, read/reply/close all feedback | Yes | No |
| Acknowledge alerts, request a retrain, view system health | Yes | No |

These permissions are checked on the server. Opening an Admin-only URL as an Analyst returns a 403 page.

## Sign in and navigate

1. Open the portal URL supplied by the person who deployed EarthScape.
2. Sign in with the account created by the Admin. Passwords are case-sensitive.
3. Use the left navigation to open Overview, Data Explorer, Analysis, Live Monitor, Prediction, Forecast, Model Performance, Alerts, or My Feedback.
4. Use the account control in the upper corner to log out when finished.

The dashboard summarizes loaded monthly climate records, the latest temperature anomaly and CO₂ reading, forecast alerts, and annual GHG records. Filters control the historical charts. The line/bar selector changes the temperature chart style. Charts display the units and NASA baseline where applicable.

## Analyst tasks

### Browse climate data and analysis

- **Data Explorer:** choose a year, browse the paginated monthly table, and inspect temperature anomaly, CO₂ in ppm, ONI, and the anomaly flag.
- **Analysis:** review the loaded temperature/CO₂ correlation, residual anomaly flags, ENSO/ONI summary, annual GHG trend, and the regional/gridded results supplied by the notebook.
- **Live Monitor:** press Replay or Pause to replay stored observations. A sudden point-to-point jump is marked as quarantined for demonstration; this page does not receive a live external climate feed.

### Generate and inspect a prediction

1. Open **Prediction** and select a horizon from 1 to 12 months.
2. Submit to run the saved `v3_direct` models. The result shows the forecast anomaly, uncertainty bounds, target month, model version, and alert level.
3. If recent feature data is insufficient, the app displays the matching stored forecast and labels it as a stored result. It does not present that fallback as a newly calculated prediction.
4. Open **Forecast** to see the stored 12-month trajectory, intervals, threshold, levels, and monthly values.

All temperature anomalies use the NASA GISTEMP 1951–1980 baseline. This is different from the Paris Agreement's 1.5 °C above pre-industrial reference.

### Submit and track feedback

1. Open **My Feedback**, choose Support, Issue, or Feedback, and enter a subject and message.
2. Submit the form. Your own submissions and any Admin response appear below it.
3. A status of Open means it is waiting for an Admin; Replied means an Admin has responded; Closed means the request is complete.

## Admin tasks

Admins can perform every Analyst task, plus the following:

- **Manage users:** create Admin or Analyst accounts, change roles, and activate or deactivate accounts. Use a unique temporary password of at least 12 characters and share it securely.
- **Alert threshold:** enter a positive temperature-anomaly threshold. Saving it regenerates the alerts from all stored forecast months. The default is 1.50 °C on the GISTEMP 1951–1980 baseline.
- **Alerts:** acknowledge individual alerts. Acknowledgement records that an Admin reviewed the item; it does not change the forecast or its severity.
- **Support inbox:** filter by status, reply to a user, and close completed feedback.
- **Model Performance:** inspect the champion information and request a retrain. The request is recorded in the audit log; model training and evaluation still run in the offline notebook workflow.
- **System Health:** refresh MongoDB connection, model/metadata status, collection counts, and diagnostic timestamp.

## Alert levels

For forecast value `F` and configured threshold `T`:

| Level | Rule |
|---|---|
| CRITICAL | `F >= T` |
| WARNING | `0.9 × T <= F < T` |
| OK | `F < 0.9 × T` |

At the default threshold of 1.50 °C, the supplied SRS forecast yields 3 CRITICAL, 5 WARNING, and 4 OK months.

## Data and availability

The supplied NASA, NOAA MLO, NOAA CPC ONI, OWID, and NSIDC files are converted into app-ready CSVs in `data/cleaned/`. The ONI feed is aligned to months and supports the bundled model's ENSO inputs. If MongoDB is empty, the operator runs `python scripts/load_data.py` after configuring `.env`. The monthly export applies the notebook's robust anomaly flagging while keeping observations in the history. See [data/cleaned/README.md](data/cleaned/README.md) for the exact sources, headers, and regeneration steps.

If the database is unavailable, wait briefly and retry or contact the Admin. If only the model is unavailable, data browsing and forecasts already stored in MongoDB may remain available, but newly computed predictions are disabled. Do not send a MongoDB URI, password, or `.env` file in feedback.

## FAQ

**I cannot sign in.** Check the exact username and password with the Admin. The account may be inactive. The seed script does not print credentials; they are set locally through `.env`.

**Why is there no prediction result?** The model files may be missing/incompatible or the monthly climate and ONI history may not be loaded. The Prediction page shows whether the model loaded and uses the matching stored forecast if current feature history is unavailable.

**Why are charts empty?** Confirm the cleaned files exist and that the operator ran `python scripts/load_data.py` against the configured MongoDB database.

**What does CRITICAL or WARNING mean?** Each forecast month is compared with the current Admin threshold using the rules above. These levels classify the supplied forecast; they are not a separate scientific assessment.

**Who can change the threshold or manage accounts?** Admin only. Analysts can view results and submit/track their own feedback.

**I see a database connection error.** The application could not reach MongoDB Atlas. The Admin/operator should verify Atlas availability, network/IP access, database-user permissions, and the locally configured `MONGO_URI`; never paste the URI into a support message.

**Does Live Monitor stream current measurements?** No. It replays stored observations to demonstrate the monitor and quarantine interaction.
