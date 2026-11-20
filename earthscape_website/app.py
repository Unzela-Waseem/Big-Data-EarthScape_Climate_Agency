"""
EarthScape Climate Agency — Main Flask Application
All routes, authentication, prediction logic, and admin features.
"""

import math
import warnings
from datetime import datetime, timezone
from functools import wraps

import numpy as np
import pandas as pd
from bson import ObjectId
from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from alerts import classify, regenerate_alerts
from config import Config
from db import close_db, get_db
from model_loader import (
    FEATURE_COLS,
    HALF,
    HS,
    META_READY,
    METADATA,
    MODEL_READY,
    MODELS,
)

# Suppress sklearn version warnings
warnings.filterwarnings("ignore")

# ==========================================================================
# App factory
# ==========================================================================
app = Flask(__name__)
app.secret_key = Config.SECRET_KEY

# ---------------------------------------------------------------------------
# Teardown
# ---------------------------------------------------------------------------
@app.teardown_appcontext
def _teardown(exc):  # noqa: ARG001
    pass  # connection pooling — close_db() called at shutdown only


# ==========================================================================
# Helpers / Decorators
# ==========================================================================

def _now():
    return datetime.now(timezone.utc)


def _audit(db, action, user=None, detail=""):
    """Write an audit-log entry."""
    if db is None:
        return
    db.audit_log.insert_one({
        "action": action,
        "user": user or session.get("username", "system"),
        "detail": detail,
        "timestamp": _now(),
    })


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))
        if session.get("role") != "admin":
            abort(403)
        return f(*args, **kwargs)
    return decorated


# ==========================================================================
# Error Handlers
# ==========================================================================

@app.errorhandler(403)
def forbidden(e):  # noqa: ARG001
    return render_template("403.html"), 403


@app.errorhandler(404)
def not_found(e):  # noqa: ARG001
    return render_template("404.html"), 404


@app.errorhandler(500)
def server_error(e):  # noqa: ARG001
    return render_template("500.html"), 500


def _db_or_error():
    """Return db handle or render a friendly error page and return None."""
    db = get_db()
    if db is None:
        return None
    return db


# ==========================================================================
# AUTH ROUTES
# ==========================================================================

@app.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return render_template("home.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        db = _db_or_error()
        if db is None:
            flash("Database unavailable. Please try later.", "danger")
            return render_template("login.html")

        user = db.users.find_one({"username": username})
        pw_hash = user.get("password") or user.get("password_hash") if user else None
        is_active = user.get("active", user.get("is_active", True)) if user else False
        if user and is_active and pw_hash and check_password_hash(pw_hash, password):
            session["user_id"] = str(user["_id"])
            session["username"] = user["username"]
            session["role"] = user.get("role", "analyst")
            _audit(db, "login", username)
            flash(f"Welcome back, {username}!", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid username or password.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    db = get_db()
    username = session.get("username", "unknown")
    if db is not None:
        _audit(db, "logout", username)
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


# ==========================================================================
# DASHBOARD & DATA ROUTES
# ==========================================================================

@app.route("/dashboard")
@login_required
def dashboard():
    db = _db_or_error()
    if db is None:
        return render_template("error.html", message="Database is currently unavailable.")

    # KPI cards
    total_records = db.monthly_climate.count_documents({})
    latest = db.monthly_climate.find_one(sort=[("year", -1), ("month", -1)])
    latest_anomaly = latest.get("temp_anomaly", "N/A") if latest else "N/A"
    latest_co2 = latest.get("co2", "N/A") if latest else "N/A"

    # Alert summary
    alert_counts = {"CRITICAL": 0, "WARNING": 0, "OK": 0}
    for a in db.alerts.find({}):
        lvl = a.get("level", "OK")
        alert_counts[lvl] = alert_counts.get(lvl, 0) + 1

    # Forecast count
    forecast_count = db.forecast.count_documents({})

    return render_template(
        "dashboard.html",
        total_records=total_records,
        latest_anomaly=latest_anomaly,
        latest_co2=latest_co2,
        alert_counts=alert_counts,
        forecast_count=forecast_count,
    )


@app.route("/api/chart/history")
@login_required
def api_chart_history():
    db = _db_or_error()
    if db is None:
        return jsonify({"error": "DB unavailable"}), 503

    start_year = request.args.get("start_year", 1880, type=int)
    end_year = request.args.get("end_year", 2100, type=int)

    query = {"year": {"$gte": start_year, "$lte": end_year}}
    docs = list(
        db.monthly_climate.find(query, {"_id": 0})
        .sort([("year", 1), ("month", 1)])
    )

    labels, temps, co2s = [], [], []
    for d in docs:
        labels.append(f"{d.get('year')}-{d.get('month', 1):02d}")
        temps.append(d.get("temp_anomaly"))
        co2s.append(d.get("co2"))

    return jsonify({
        "labels": labels,
        "temp_anomaly": temps,
        "co2": co2s,
    })


@app.route("/api/chart/forecast")
@login_required
def api_chart_forecast():
    db = _db_or_error()
    if db is None:
        return jsonify({"error": "DB unavailable"}), 503

    forecasts = list(db.forecast.find({}, {"_id": 0}).sort([("horizon", 1)]))

    # Threshold
    settings = db.settings.find_one({"key": "alert_threshold"})
    threshold = float(settings["value"]) if settings else Config.DEFAULT_THRESHOLD

    labels, values, lowers, uppers = [], [], [], []
    for fc in forecasts:
        labels.append(f"{fc.get('year')}-{fc.get('month', 1):02d}")
        val = fc.get("forecast", fc.get("predicted", 0))
        half = fc.get("half", 0)
        values.append(val)
        lowers.append(val - half)
        uppers.append(val + half)

    return jsonify({
        "labels": labels,
        "forecast": values,
        "lower": lowers,
        "upper": uppers,
        "threshold": threshold,
    })


@app.route("/explorer")
@login_required
def explorer():
    db = _db_or_error()
    if db is None:
        return render_template("error.html", message="Database is currently unavailable.")

    page = request.args.get("page", 1, type=int)
    year_filter = request.args.get("year", None, type=int)

    query = {}
    if year_filter:
        query["year"] = year_filter

    total = db.monthly_climate.count_documents(query)
    total_pages = max(1, math.ceil(total / Config.PAGE_SIZE))
    page = max(1, min(page, total_pages))
    skip = (page - 1) * Config.PAGE_SIZE

    docs = list(
        db.monthly_climate.find(query, {"_id": 0})
        .sort([("year", -1), ("month", -1)])
        .skip(skip)
        .limit(Config.PAGE_SIZE)
    )

    # Distinct years for filter dropdown
    years = sorted(db.monthly_climate.distinct("year"), reverse=True)

    return render_template(
        "explorer.html",
        records=docs,
        page=page,
        total_pages=total_pages,
        year_filter=year_filter,
        years=years,
        total=total,
    )


# ==========================================================================
# ANALYSIS & LIVE ROUTES
# ==========================================================================

@app.route("/analysis")
@login_required
def analysis():
    db = _db_or_error()
    if db is None:
        return render_template("error.html", message="Database is currently unavailable.")

    # Pull processing results from the analysis collection (or compute on the fly)
    results = db.analysis_results.find_one({"key": "latest"}) or {}

    # Correlations
    docs = list(db.monthly_climate.find(
        {"temp_anomaly": {"$ne": None}, "co2": {"$ne": None}},
        {"_id": 0, "temp_anomaly": 1, "co2": 1}
    ))
    corr = None
    if len(docs) > 10:
        temps = [d["temp_anomaly"] for d in docs]
        co2s = [d["co2"] for d in docs]
        corr = round(float(np.corrcoef(temps, co2s)[0, 1]), 4)

    # Anomaly stats
    all_temps = list(db.monthly_climate.find(
        {"temp_anomaly": {"$ne": None}},
        {"_id": 0, "year": 1, "month": 1, "temp_anomaly": 1}
    ).sort([("year", -1), ("month", -1)]).limit(120))

    anomaly_count = sum(1 for d in all_temps if d.get("temp_anomaly", 0) > 1.0)

    # ENSO summary
    enso_docs = list(db.monthly_climate.find(
        {"oni": {"$ne": None}},
        {"_id": 0, "oni": 1}
    ).sort([("year", -1), ("month", -1)]).limit(60))
    oni_values = [d["oni"] for d in enso_docs if d.get("oni") is not None]
    enso_summary = {}
    if oni_values:
        enso_summary = {
            "latest_oni": oni_values[0] if oni_values else None,
            "avg_oni_5yr": round(float(np.mean(oni_values)), 3),
            "max_oni_5yr": round(float(max(oni_values)), 3),
            "min_oni_5yr": round(float(min(oni_values)), 3),
            "el_nino_months": sum(1 for v in oni_values if v >= 0.5),
            "la_nina_months": sum(1 for v in oni_values if v <= -0.5),
        }

    # Arctic summary (from SRS FR-4: Arctic 0.656 °C/decade vs Tropics 0.158 °C/decade)
    arctic_summary = results.get("arctic_summary", {
        "arctic_rate": 0.656,
        "tropics_rate": 0.158,
        "sea_ice_skill": 0.53,
    })

    spark_summary = {
        "total_records": "1,762",
        "date_range": "1880-01 → 2026-10",
        "columns": 12,
        "missing_filled": "Interpolation & spline (0 dropped rows)",
        "sources": "NASA GISS, NOAA CO2, OWID GHG, CPC ONI",
    }

    return render_template(
        "analysis.html",
        correlation=corr,
        anomaly_count=anomaly_count,
        enso_summary=enso_summary,
        arctic_summary=arctic_summary,
        spark_summary=spark_summary,
        results=results,
    )


@app.route("/live")
@login_required
def live():
    return render_template("live.html")


@app.route("/api/live_data")
@login_required
def live_data():
    db = _db_or_error()
    if db is None:
        return jsonify({"records": []})
    recent = list(db.monthly_climate.find({}, {"_id": 0}).sort([("year", -1), ("month", -1)]).limit(36))
    recent.reverse()
    return jsonify({"records": recent})


# ==========================================================================
# ML & PREDICTION ROUTES
# ==========================================================================

def _build_features(db, horizon):
    """
    Build the feature row for a given forecast horizon using the EXACT
    recipe:
      base = mean of temp_anomaly over 12 months ending last month
      dev_lagk = temp_anomaly shifted k − base
      dev_roll3/6 = shifted rolling mean − base
      vol12 = shift(1) rolling-12 std
      ONI features: lags 3,4,6; oni_chg = ONI_shift3 − ONI_shift6
      Add m_sin, m_cos of TARGET month
    """
    # Need enough history: at least 24 + horizon months
    needed = 36 + horizon
    docs = list(
        db.monthly_climate.find(
            {"temp_anomaly": {"$ne": None}},
            {"_id": 0, "year": 1, "month": 1, "temp_anomaly": 1, "oni": 1},
        )
        .sort([("year", 1), ("month", 1)])
    )

    if len(docs) < needed:
        return None, None

    df = pd.DataFrame(docs)
    df["date"] = pd.to_datetime(
        df["year"].astype(str) + "-" + df["month"].astype(str).str.zfill(2) + "-01"
    )
    df = df.set_index("date").sort_index()

    ta = df["temp_anomaly"].astype(float)
    oni = df["oni"].astype(float) if "oni" in df.columns else None

    # base = mean of temp_anomaly over 12 months ending last month
    base = ta.shift(1).rolling(12).mean()

    # dev_lags
    dev_lag1 = ta.shift(1) - base
    dev_lag2 = ta.shift(2) - base
    dev_lag3 = ta.shift(3) - base
    dev_lag6 = ta.shift(6) - base
    dev_lag12 = ta.shift(12) - base

    # dev_rolls
    dev_roll3 = ta.shift(1).rolling(3).mean() - base
    dev_roll6 = ta.shift(1).rolling(6).mean() - base

    # vol12
    vol12 = ta.shift(1).rolling(12).std()

    features = pd.DataFrame({
        "dev_lag1": dev_lag1,
        "dev_lag2": dev_lag2,
        "dev_lag3": dev_lag3,
        "dev_lag6": dev_lag6,
        "dev_lag12": dev_lag12,
        "dev_roll3": dev_roll3,
        "dev_roll6": dev_roll6,
        "vol12": vol12,
    }, index=df.index)

    # ONI features
    if oni is not None and oni.notna().sum() > 10:
        features["oni_l3"] = oni.shift(3)
        features["oni_l4"] = oni.shift(4)
        features["oni_l6"] = oni.shift(6)
        features["oni_chg"] = oni.shift(3) - oni.shift(6)
    else:
        return None, None  # ONI missing → caller should fallback

    # Shift features back by (horizon - 1) months from target
    features = features.shift(horizon - 1)

    # Target month for m_sin / m_cos
    target_idx = features.index
    target_month = target_idx.month
    features["m_sin"] = np.sin(2 * np.pi * target_month / 12)
    features["m_cos"] = np.cos(2 * np.pi * target_month / 12)

    # Take the LAST complete row
    features = features.dropna()
    if features.empty:
        return None, None

    row = features.iloc[[-1]]
    target_date = row.index[0]

    # Ensure column order matches model expectations
    col_order = FEATURE_COLS + ["m_sin", "m_cos"]
    row = row[col_order]

    return row, target_date


@app.route("/predict", methods=["GET", "POST"])
@login_required
def predict():
    if not MODEL_READY:
        return render_template(
            "predict.html",
            error="Model files not available. Prediction is disabled.",
            result=None,
        )

    db = _db_or_error()
    if db is None:
        return render_template("error.html", message="Database is currently unavailable.")

    result = None
    if request.method == "POST":
        horizon = request.form.get("horizon", 1, type=int)
        horizon = max(1, min(horizon, 12))

        features, target_date = _build_features(db, horizon)

        if features is None:
            # Fallback to stored forecast
            stored = db.forecast.find_one({"horizon": horizon})
            if stored:
                settings = db.settings.find_one({"key": "alert_threshold"})
                threshold = float(settings["value"]) if settings else Config.DEFAULT_THRESHOLD
                result = {
                    "horizon": horizon,
                    "forecast": round(stored.get("forecast", stored.get("predicted", 0)), 4),
                    "lower": round(stored.get("forecast", 0) - stored.get("half", 0), 4),
                    "upper": round(stored.get("forecast", 0) + stored.get("half", 0), 4),
                    "level": classify(stored.get("forecast", 0), threshold),
                    "source": "stored_forecast",
                    "target_date": f"{stored.get('year')}-{stored.get('month', 1):02d}",
                }
            else:
                result = {"error": "ONI data missing and no stored forecast available."}
        else:
            # Run ensemble: Ridge, RF, GB → average
            model_set = MODELS.get(horizon, {})
            preds = []
            for name in ["Ridge", "RF", "GB"]:
                m = model_set.get(name)
                if m is not None:
                    preds.append(float(m.predict(features.values)[0]))

            if not preds:
                result = {"error": f"No models found for horizon {horizon}."}
            else:
                forecast_val = round(float(np.mean(preds)), 4)
                half_width = HALF.get(horizon, 0)
                settings = db.settings.find_one({"key": "alert_threshold"})
                threshold = float(settings["value"]) if settings else Config.DEFAULT_THRESHOLD
                level = classify(forecast_val, threshold)

                result = {
                    "horizon": horizon,
                    "forecast": forecast_val,
                    "lower": round(forecast_val - half_width, 4),
                    "upper": round(forecast_val + half_width, 4),
                    "level": level,
                    "source": "live_prediction",
                    "target_date": target_date.strftime("%Y-%m") if target_date else "N/A",
                }

    return render_template("predict.html", result=result, horizons=list(range(1, 13)))


@app.route("/forecast")
@login_required
def forecast():
    db = _db_or_error()
    if db is None:
        return render_template("error.html", message="Database is currently unavailable.")

    forecasts = list(db.forecast.find({}, {"_id": 0}).sort([("horizon", 1)]))

    settings = db.settings.find_one({"key": "alert_threshold"})
    threshold = float(settings["value"]) if settings else Config.DEFAULT_THRESHOLD

    for fc in forecasts:
        val = fc.get("forecast", fc.get("predicted", 0))
        fc["level"] = classify(val, threshold)

    return render_template("forecast.html", forecasts=forecasts, threshold=threshold)


@app.route("/models")
@login_required
def models_page():
    db = _db_or_error()
    if db is None:
        return render_template("error.html", message="Database is currently unavailable.")

    champion = METADATA.get("champion", "Ensemble") if META_READY else "N/A"
    metrics = METADATA.get("metrics", {}) if META_READY else {}
    description = METADATA.get("description", "") if META_READY else ""
    feature_set = METADATA.get("feature_set", "C_B+ENSO") if META_READY else "N/A"

    # Build comparison table from metadata
    comparison = []
    if META_READY:
        for h in METADATA.get("horizons", list(range(1, 13))):
            h_metrics = metrics.get(str(h), metrics.get(h, {}))
            comparison.append({
                "horizon": h,
                "ridge_mae": h_metrics.get("Ridge", {}).get("mae", "N/A"),
                "rf_mae": h_metrics.get("RF", {}).get("mae", "N/A"),
                "gb_mae": h_metrics.get("GB", {}).get("mae", "N/A"),
                "ensemble_mae": h_metrics.get("Ensemble", {}).get("mae", "N/A"),
            })

    return render_template(
        "models.html",
        model_ready=MODEL_READY,
        meta_ready=META_READY,
        champion=champion,
        metrics=metrics,
        description=description,
        feature_set=feature_set,
        comparison=comparison,
        is_admin=session.get("role") == "admin",
    )


@app.route("/models/retrain", methods=["POST"])
@admin_required
def retrain():
    db = _db_or_error()
    if db is not None:
        _audit(db, "model_retrain_request", detail="Retrain request registered by Admin. Offline PySpark/Notebook pipeline triggered.")
    flash("Retrain request logged in audit trail. Actual model training runs in the offline Jupyter notebook pipeline.", "info")
    return redirect(url_for("models_page"))


# ==========================================================================
# ALERTS & THRESHOLD ROUTES
# ==========================================================================

@app.route("/alerts")
@login_required
def alerts_page():
    db = _db_or_error()
    if db is None:
        return render_template("error.html", message="Database is currently unavailable.")

    alerts_list = list(db.alerts.find({}).sort([("horizon", 1)]))
    # Convert ObjectId to string for templates
    for a in alerts_list:
        a["_id"] = str(a["_id"])

    return render_template(
        "alerts.html",
        alerts=alerts_list,
        is_admin=session.get("role") == "admin",
    )


@app.route("/alerts/<alert_id>/ack", methods=["POST"], endpoint="ack_alert")
@app.route("/alerts/<alert_id>/acknowledge", methods=["POST"], endpoint="acknowledge_alert")
@admin_required
def ack_alert(alert_id):
    db = _db_or_error()
    if db is None:
        return render_template("error.html", message="Database is currently unavailable.")

    db.alerts.update_one(
        {"_id": ObjectId(alert_id)},
        {"$set": {
            "acknowledged": True,
            "ack_by": session.get("username"),
            "ack_at": _now(),
        }},
    )
    flash("Alert acknowledged.", "success")
    return redirect(url_for("alerts_page"))


@app.route("/threshold", methods=["GET", "POST"])
@admin_required
def threshold():
    db = _db_or_error()
    if db is None:
        return render_template("error.html", message="Database is currently unavailable.")

    if request.method == "POST":
        new_val = request.form.get("threshold", type=float)
        if new_val is not None and new_val > 0:
            db.settings.update_one(
                {"key": "alert_threshold"},
                {"$set": {"value": new_val, "updated_at": _now()}},
                upsert=True,
            )
            result = regenerate_alerts(db, new_val)
            _audit(
                db, "threshold_change",
                detail=f"New threshold: {new_val} → {result['critical']}C/{result['warning']}W/{result['ok']}OK",
            )
            flash(
                f"Threshold updated to {new_val:.2f}. "
                f"Alerts regenerated: {result['critical']} Critical, "
                f"{result['warning']} Warning, {result['ok']} OK.",
                "success",
            )
        else:
            flash("Invalid threshold value.", "danger")

    settings = db.settings.find_one({"key": "alert_threshold"})
    current = float(settings["value"]) if settings else Config.DEFAULT_THRESHOLD

    return render_template("threshold.html", threshold=current)


# ==========================================================================
# USER MANAGEMENT
# ==========================================================================

@app.route("/users", methods=["GET", "POST"])
@admin_required
def users():
    db = _db_or_error()
    if db is None:
        return render_template("error.html", message="Database is currently unavailable.")

    if request.method == "POST":
        action = request.form.get("action", "create")

        if action == "create":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            role = request.form.get("role", "analyst")

            if not username or not password:
                flash("Username and password are required.", "danger")
            elif db.users.find_one({"username": username}):
                flash(f"User '{username}' already exists.", "warning")
            else:
                db.users.insert_one({
                    "username": username,
                    "password": generate_password_hash(password),
                    "role": role,
                    "active": True,
                    "created_at": _now(),
                })
                _audit(db, "user_create", detail=f"Created user '{username}' with role '{role}'")
                flash(f"User '{username}' created as {role}.", "success")

        elif action == "change_role":
            uid = request.form.get("user_id")
            new_role = request.form.get("role", "analyst")
            db.users.update_one(
                {"_id": ObjectId(uid)},
                {"$set": {"role": new_role}},
            )
            _audit(db, "user_role_change", detail=f"User {uid} → role {new_role}")
            flash("Role updated.", "success")

        elif action == "deactivate":
            uid = request.form.get("user_id")
            db.users.update_one(
                {"_id": ObjectId(uid)},
                {"$set": {"active": False}},
            )
            _audit(db, "user_deactivate", detail=f"Deactivated user {uid}")
            flash("User deactivated.", "success")

        elif action == "activate":
            uid = request.form.get("user_id")
            db.users.update_one(
                {"_id": ObjectId(uid)},
                {"$set": {"active": True}},
            )
            _audit(db, "user_activate", detail=f"Activated user {uid}")
            flash("User activated.", "success")

    users_list = list(db.users.find({}))
    for u in users_list:
        u["_id"] = str(u["_id"])

    return render_template("users.html", users=users_list)


# ==========================================================================
# FEEDBACK
# ==========================================================================

@app.route("/users/create", methods=["POST"])
@admin_required
def create_user():
    db = _db_or_error()
    if db is None:
        return render_template("error.html", message="Database is currently unavailable.")
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "analyst")
    email = request.form.get("email", "")
    full_name = request.form.get("full_name", "")
    if not username or not password:
        flash("Username and password are required.", "danger")
    elif db.users.find_one({"username": username}):
        flash(f"User '{username}' already exists.", "warning")
    else:
        hashed = generate_password_hash(password)
        db.users.insert_one({
            "username": username,
            "password": hashed,
            "password_hash": hashed,
            "role": role,
            "email": email,
            "full_name": full_name,
            "active": True,
            "is_active": True,
            "created_at": _now(),
        })
        _audit(db, "user_create", detail=f"Created user '{username}' with role '{role}'")
        flash(f"User '{username}' created as {role}.", "success")
    return redirect(url_for("users"))


@app.route("/users/<user_id>/role", methods=["POST"])
@admin_required
def change_role(user_id):
    db = _db_or_error()
    if db is not None:
        new_role = request.form.get("role", "analyst")
        db.users.update_one({"_id": ObjectId(user_id)}, {"$set": {"role": new_role}})
        _audit(db, "user_role_change", detail=f"User {user_id} → role {new_role}")
        flash("Role updated.", "success")
    return redirect(url_for("users"))


@app.route("/users/<user_id>/deactivate", methods=["POST"])
@admin_required
def deactivate_user(user_id):
    db = _db_or_error()
    if db is not None:
        db.users.update_one({"_id": ObjectId(user_id)}, {"$set": {"active": False, "is_active": False}})
        _audit(db, "user_deactivate", detail=f"Deactivated user {user_id}")
        flash("User deactivated.", "success")
    return redirect(url_for("users"))


@app.route("/users/<user_id>/activate", methods=["POST"])
@admin_required
def activate_user(user_id):
    db = _db_or_error()
    if db is not None:
        db.users.update_one({"_id": ObjectId(user_id)}, {"$set": {"active": True, "is_active": True}})
        _audit(db, "user_activate", detail=f"Activated user {user_id}")
        flash("User activated.", "success")
    return redirect(url_for("users"))


@app.route("/admin/feedback/<feedback_id>/reply", methods=["POST"])
@admin_required
def reply_feedback(feedback_id):
    db = _db_or_error()
    if db is not None:
        reply_text = request.form.get("reply", "").strip()
        if reply_text:
            db.feedback.update_one(
                {"_id": ObjectId(feedback_id)},
                {"$set": {"reply": reply_text, "status": "replied", "replied_by": session["username"], "replied_at": _now()}},
            )
            flash("Reply sent.", "success")
    return redirect(url_for("admin_feedback"))


@app.route("/admin/feedback/<feedback_id>/close", methods=["POST"])
@admin_required
def close_feedback(feedback_id):
    db = _db_or_error()
    if db is not None:
        db.feedback.update_one(
            {"_id": ObjectId(feedback_id)},
            {"$set": {"status": "closed", "closed_by": session["username"], "closed_at": _now()}},
        )
        flash("Feedback closed.", "success")
    return redirect(url_for("admin_feedback"))


@app.route("/feedback", methods=["GET", "POST"])
@login_required
def feedback():
    db = _db_or_error()
    if db is None:
        return render_template("error.html", message="Database is currently unavailable.")

    if request.method == "POST":
        subject = request.form.get("subject", "").strip()
        message = request.form.get("message", "").strip()
        if subject and message:
            db.feedback.insert_one({
                "user": session["username"],
                "subject": subject,
                "message": message,
                "status": "open",
                "reply": None,
                "created_at": _now(),
            })
            flash("Feedback submitted. Thank you!", "success")
        else:
            flash("Subject and message are required.", "danger")

    my_feedback = list(
        db.feedback.find({"user": session["username"]}).sort([("created_at", -1)])
    )
    for fb in my_feedback:
        fb["_id"] = str(fb["_id"])

    return render_template("feedback.html", feedbacks=my_feedback)


@app.route("/admin/feedback", methods=["GET", "POST"])
@admin_required
def admin_feedback():
    db = _db_or_error()
    if db is None:
        return render_template("error.html", message="Database is currently unavailable.")

    if request.method == "POST":
        fb_id = request.form.get("feedback_id")
        action = request.form.get("action", "reply")

        if action == "reply":
            reply_text = request.form.get("reply", "").strip()
            if reply_text:
                db.feedback.update_one(
                    {"_id": ObjectId(fb_id)},
                    {"$set": {"reply": reply_text, "replied_by": session["username"], "replied_at": _now()}},
                )
                flash("Reply sent.", "success")

        elif action == "close":
            db.feedback.update_one(
                {"_id": ObjectId(fb_id)},
                {"$set": {"status": "closed", "closed_by": session["username"], "closed_at": _now()}},
            )
            flash("Feedback closed.", "success")

    all_feedback = list(db.feedback.find({}).sort([("created_at", -1)]))
    for fb in all_feedback:
        fb["_id"] = str(fb["_id"])

    return render_template("admin_feedback.html", feedbacks=all_feedback)


# ==========================================================================
# HEALTH CHECK
# ==========================================================================

@app.route("/health")
@admin_required
def health():
    db = get_db()
    db_status = "connected" if db is not None else "disconnected"

    model_status = "loaded" if MODEL_READY else "not loaded"
    meta_status = "loaded" if META_READY else "not loaded"

    info = {
        "app": "EarthScape Climate Agency",
        "status": "running",
        "db_status": db_status,
        "model_status": model_status,
        "meta_status": meta_status,
        "timestamp": _now().isoformat(),
    }

    if db is not None:
        info["collections"] = {
            "monthly_climate": db.monthly_climate.count_documents({}),
            "forecast": db.forecast.count_documents({}),
            "alerts": db.alerts.count_documents({}),
            "users": db.users.count_documents({}),
            "feedback": db.feedback.count_documents({}),
        }

    return render_template("health.html", info=info)


# ==========================================================================
# MAIN
# ==========================================================================

if __name__ == "__main__":
    app.run(debug=True, port=5000)
