"""
EarthScape Climate Agency — Main Flask Application
All routes, authentication, prediction logic, and admin features.
"""

import math
import os
import copy
import threading
import warnings
from datetime import datetime, timezone
from functools import wraps
from flask import g

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
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash

from alerts import classify, regenerate_alerts
from config import Config
from db import close_db, get_db
from model_loader import (
    COLS,
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
if not Config.SECRET_KEY:
    raise RuntimeError("SECRET_KEY must be configured in the environment before starting EarthScape.")
app.secret_key = Config.SECRET_KEY
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("FLASK_ENV") == "production"
csrf = CSRFProtect(app)

# Small process-local cache for repeated dashboard and forecast reads. The loader
# bumps dataset_revision after each import; threshold is part of the key so a
# threshold change cannot reuse a stale forecast classification.
_MEMORY_CACHE = {}
_MEMORY_CACHE_LOCK = threading.RLock()
_MEMORY_CACHE_LIMIT = 16

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
    db.audit.insert_one({
        "username": user or session.get("username", "system"),
        "action": action,
        "details": detail,
        "timestamp": _now(),
    })


def _cached_value(db, key, builder):
    """Return a cached value, evicting old keys when the small cache fills."""
    with _MEMORY_CACHE_LOCK:
        if key in _MEMORY_CACHE:
            return copy.deepcopy(_MEMORY_CACHE[key])
    value = builder()
    with _MEMORY_CACHE_LOCK:
        _MEMORY_CACHE[key] = copy.deepcopy(value)
        while len(_MEMORY_CACHE) > _MEMORY_CACHE_LIMIT:
            _MEMORY_CACHE.pop(next(iter(_MEMORY_CACHE)))
    return value


def _data_revision(db):
    """Read the latest data-load audit time without adding a settings document."""
    revision = db.audit.find_one(
        {"action": "data_load"}, {"_id": 0, "timestamp": 1}, sort=[("timestamp", -1)]
    )
    return revision.get("timestamp", "initial") if revision else "initial"


def _dashboard_data(db, threshold):
    """Cache stable dashboard KPIs and bounded chart data by data generation."""
    key = ("dashboard", _data_revision(db), round(float(threshold), 6))

    def build():
        total_records = db.monthly_climate.count_documents({})
        latest = db.monthly_climate.find_one(sort=[("year", -1), ("month", -1)])
        latest_co2_doc = db.monthly_climate.find_one(
            {"co2_ppm": {"$ne": None}}, sort=[("year", -1), ("month", -1)]
        )
        return {
            "total_records": total_records,
            "latest_anomaly": latest.get("temp_anomaly", "N/A") if latest else "N/A",
            "latest_co2": latest_co2_doc.get("co2_ppm", "N/A") if latest_co2_doc else "N/A",
            "latest_co2_month": (
                f"{latest_co2_doc['year']:04d}-{latest_co2_doc['month']:02d}"
                if latest_co2_doc else ""
            ),
            "forecast_count": db.forecast.count_documents({}),
            "next_forecast": db.forecast.find_one(sort=[("month", 1)]) or {},
            "ghg_records": list(db.annual_ghg.find(
                {"country": "World"}, {"_id": 0}
            ).sort("year", 1).limit(500)),
        }

    return _cached_value(db, key, build)


def _forecast_data(db, threshold):
    """Cache stored forecast rows and their threshold-dependent alert levels."""
    key = ("forecast", _data_revision(db), round(float(threshold), 6))

    def build():
        rows = list(db.forecast.find({}, {"_id": 0}).sort([("month", 1)]))
        for row in rows:
            row["level"] = classify(row.get("forecast", 0), threshold)
        return rows

    return _cached_value(db, key, build)


@app.before_request
def _start_request_timer():
    g.request_started = datetime.now(timezone.utc)


@app.after_request
def _record_request_time(response):
    """Persist route timing for lightweight application-level monitoring."""
    started = getattr(g, "request_started", None)
    if started and request.endpoint not in {"static", "health"}:
        try:
            db = get_db()
            if db is not None:
                elapsed_ms = round((datetime.now(timezone.utc) - started).total_seconds() * 1000, 2)
                db.audit.insert_one({
                    "username": session.get("username", "anonymous"),
                    "action": "request_timing",
                    "details": {"endpoint": request.endpoint, "method": request.method,
                                "status": response.status_code, "duration_ms": elapsed_ms},
                    "timestamp": _now(),
                })
        except Exception:
            app.logger.exception("Unable to record request timing")
    return response


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
        app.logger.error("MongoDB connection unavailable")
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
            flash("Database connection failed, please try again later.", "danger")
            return render_template("login.html")

        user = db.users.find_one({"username": username})
        pw_hash = user.get("password_hash") if user else None
        is_active = user.get("is_active", False) if user else False
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


@app.route("/logout", methods=["GET", "POST"])
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
        return render_template("error.html", message="Database connection failed, please try again later.")

    settings = db.settings.find_one({"key": "alert_threshold"}) or {"value": Config.DEFAULT_THRESHOLD}
    threshold = float(settings["value"])
    cached = _dashboard_data(db, threshold)

    # Alert summary
    alert_counts = {"CRITICAL": 0, "WARNING": 0, "OK": 0}
    for a in db.alerts.find({}):
        lvl = a.get("level", "OK")
        alert_counts[lvl] = alert_counts.get(lvl, 0) + 1
    active_critical = db.alerts.count_documents({"level": "CRITICAL", "acknowledged": False})

    recent_alerts = list(db.alerts.find({}).sort([("month", -1)]).limit(5))

    return render_template(
        "dashboard.html",
        total_records=cached["total_records"],
        latest_anomaly=cached["latest_anomaly"],
        latest_co2=cached["latest_co2"],
        latest_co2_month=cached["latest_co2_month"],
        alert_counts=alert_counts,
        active_critical=active_critical,
        forecast_count=cached["forecast_count"],
        next_forecast=cached["next_forecast"],
        threshold=threshold,
        recent_alerts=recent_alerts,
        years=list(range(1880, 2027)),
        ghg_records=cached["ghg_records"],
    )


@app.route("/api/chart/history")
@login_required
def api_chart_history():
    db = _db_or_error()
    if db is None:
        return jsonify({"error": "DB unavailable"}), 503

    start_year = request.args.get("start_year", 1880, type=int)
    end_year = request.args.get("end_year", 2026, type=int)
    if not 1700 <= start_year <= end_year <= 2200:
        return jsonify({"error": "Invalid year range."}), 400

    query = {"year": {"$gte": start_year, "$lte": end_year}}
    docs = list(
        db.monthly_climate.find(query, {"_id": 0})
        .sort([("year", 1), ("month", 1)])
    )

    labels, temps, co2s = [], [], []
    for d in docs:
        labels.append(f"{d.get('year')}-{d.get('month', 1):02d}")
        temps.append(d.get("temp_anomaly"))
        co2s.append(d.get("co2_ppm"))

    return jsonify({
        "labels": labels,
        "temp_anomaly": temps,
        "co2": co2s,
        "co2_ppm": co2s,
        "is_anomaly": [bool(d.get("is_anomaly", False)) for d in docs],
    })


@app.route("/api/chart/forecast")
@login_required
def api_chart_forecast():
    db = _db_or_error()
    if db is None:
        return jsonify({"error": "DB unavailable"}), 503

    # Threshold
    settings = db.settings.find_one({"key": "alert_threshold"})
    threshold = float(settings["value"]) if settings else Config.DEFAULT_THRESHOLD
    forecasts = _forecast_data(db, threshold)

    labels, values, lowers, uppers = [], [], [], []
    for fc in forecasts:
        labels.append(str(fc.get("month", ""))[:7])
        val = float(fc.get("forecast", 0))
        values.append(val)
        lowers.append(float(fc.get("lower", val)))
        uppers.append(float(fc.get("upper", val)))

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
        return render_template("error.html", message="Database connection failed, please try again later.")

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
        total_records=total,
    )


# ==========================================================================
# ANALYSIS & LIVE ROUTES
# ==========================================================================

@app.route("/analysis")
@login_required
def analysis():
    db = _db_or_error()
    if db is None:
        return render_template("error.html", message="Database connection failed, please try again later.")

    # Pull processing results from the analysis collection (or compute on the fly)
    results = db.analysis_results.find_one({"key": "latest"}) or {}

    # Correlations
    docs = list(db.monthly_climate.find(
        {"temp_anomaly": {"$ne": None}, "co2_ppm": {"$ne": None}},
        {"_id": 0, "temp_anomaly": 1, "co2_ppm": 1}
    ))
    corr = None
    if len(docs) > 10:
        temps = [d["temp_anomaly"] for d in docs]
        co2s = [d["co2_ppm"] for d in docs]
        corr = round(float(np.corrcoef(temps, co2s)[0, 1]), 4)

    # Anomaly stats
    anomalies = list(db.monthly_climate.find(
        {"is_anomaly": True}, {"_id": 0, "year": 1, "month": 1, "date": 1,
                               "temp_anomaly": 1, "anomaly_method": 1}
    ).sort([("date", -1)]).limit(100))
    anomaly_count = db.monthly_climate.count_documents({"is_anomaly": True})
    ghg = list(db.annual_ghg.find({"country": "World"}).sort("year", 1))
    ghg_summary = {
        "first_year": ghg[0].get("year") if ghg else None,
        "last_year": ghg[-1].get("year") if ghg else None,
        "first_total": ghg[0].get("total_ghg") if ghg else None,
        "last_total": ghg[-1].get("total_ghg") if ghg else None,
    }

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
    arctic_records = list(db.arctic_ice.find({}, {"_id": 0}).sort("month", 1).limit(1000))

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
        arctic_records=arctic_records,
        ghg_summary=ghg_summary,
        anomalies=anomalies,
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
    # Use a bounded, indexed time window; the latest row feeds the selected horizon.
    docs = list(
        db.monthly_climate.find(
            {"temp_anomaly": {"$ne": None}},
            {"_id": 0, "year": 1, "month": 1, "temp_anomaly": 1, "oni": 1},
        )
        .sort([("year", 1), ("month", 1)])
    )

    if len(docs) < 25 or not any(d.get("oni") is not None for d in docs):
        return None, None

    df = pd.DataFrame(docs)
    df["date"] = pd.to_datetime(
        df["year"].astype(str) + "-" + df["month"].astype(str).str.zfill(2) + "-01"
    )
    df = df.set_index("date").sort_index()

    ta = df["temp_anomaly"].astype(float)
    oni = pd.to_numeric(df["oni"], errors="coerce")
    last_observed = ta.index[-1]
    target_date = last_observed + pd.DateOffset(months=horizon)
    # Mirror notebook make_forecast/direct_xy: each target uses feature row t-(h-1).
    feature_date = target_date - pd.DateOffset(months=horizon - 1)
    full_index = pd.date_range(ta.index[0], target_date, freq="MS")
    ta = ta.reindex(full_index)
    oni = oni.reindex(full_index).ffill(limit=15)

    base = ta.shift(1).rolling(12).mean()
    features = pd.DataFrame({"dev_lag1": ta.shift(1) - base,
                             "dev_lag2": ta.shift(2) - base,
                             "dev_lag3": ta.shift(3) - base,
                             "dev_lag6": ta.shift(6) - base,
                             "dev_lag12": ta.shift(12) - base,
                             "dev_roll3": ta.shift(1).rolling(3).mean() - base,
                             "dev_roll6": ta.shift(1).rolling(6).mean() - base,
                             "vol12": ta.shift(1).rolling(12).std(),
                             "oni_l3": oni.shift(3),
                             "oni_l4": oni.shift(4),
                             "oni_l6": oni.shift(6),
                             "oni_chg": oni.shift(3) - oni.shift(6)}, index=full_index)
    row = features.loc[[feature_date]].copy()
    if row.empty or row.isna().any(axis=None):
        return None, None
    # Seasonal columns are keyed to the forecast target, exactly as direct_xy.
    row["m_sin"] = np.sin(2 * np.pi * target_date.month / 12)
    row["m_cos"] = np.cos(2 * np.pi * target_date.month / 12)
    expected_cols = list(COLS) + ["m_sin", "m_cos"]
    if any(column not in row.columns for column in expected_cols):
        return None, None
    return row[expected_cols], target_date, float(base.loc[feature_date])


@app.route("/predict", methods=["GET", "POST"])
@login_required
def predict():
    if not MODEL_READY:
        return render_template(
            "predict.html",
            error="Model files not available. Prediction is disabled.",
            result=None,
            model_ready=False,
        )

    db = _db_or_error()
    if db is None:
        return render_template("error.html", message="Database connection failed, please try again later.")

    result = None
    if request.method == "POST":
        horizon = request.form.get("horizon", 1, type=int)
        horizon = max(1, min(horizon, 12))

        built = _build_features(db, horizon)
        features, target_date, base = built if built[0] is not None else (None, None, None)

        if features is None:
            # Fallback to stored forecast
            stored = list(db.forecast.find({}).sort("month", 1))
            stored = stored[horizon - 1] if len(stored) >= horizon else None
            if stored:
                settings = db.settings.find_one({"key": "alert_threshold"})
                threshold = float(settings["value"]) if settings else Config.DEFAULT_THRESHOLD
                result = {
                    "horizon": horizon,
                    "forecast": stored.get("forecast"),
                    "lower": stored.get("lower"),
                    "upper": stored.get("upper"),
                    "level": classify(stored.get("forecast", 0), threshold),
                    "source": "stored_forecast",
                    "target_date": str(stored.get("month", ""))[:7],
                    "model_version": stored.get("model_version", "v3_direct"),
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
                forecast_val = round(base + float(np.mean(preds)), 4)
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
                    "model_version": "v3_direct",
                    "generated_at": _now().isoformat(),
                }

    return render_template("predict.html", result=result, horizons=list(range(1, 13)), model_ready=True)


@app.route("/forecast")
@login_required
def forecast():
    db = _db_or_error()
    if db is None:
        return render_template("error.html", message="Database connection failed, please try again later.")

    settings = db.settings.find_one({"key": "alert_threshold"})
    threshold = float(settings["value"]) if settings else Config.DEFAULT_THRESHOLD
    forecasts = _forecast_data(db, threshold)
    chart_data = {
        "labels": [str(f.get("month", ""))[:7] for f in forecasts],
        "forecast": [f.get("forecast") for f in forecasts],
        "lower": [f.get("lower") for f in forecasts],
        "upper": [f.get("upper") for f in forecasts],
        "threshold": threshold,
    }
    return render_template("forecast.html", forecasts=forecasts, threshold=threshold, forecast_chart_data=chart_data)


@app.route("/models")
@login_required
def models_page():
    db = _db_or_error()
    if db is None:
        return render_template("error.html", message="Database connection failed, please try again later.")

    champion = {"version": "v3_direct", "name": "Direct Ensemble (Ridge + Random Forest + Gradient Boosting)"}
    metrics = {"rmse": 0.101, "r2": 0.701, "skill_vs_persistence": 0.204, "interval_coverage": 0.906}
    description = "A direct multi-horizon ensemble with one set of three fitted models for each horizon (1–12 months)."
    feature_set = METADATA.get("feature_set", "C_B+ENSO") if META_READY else "N/A"
    recent_actions = list(db.audit.find({}).sort("timestamp", -1).limit(10))

    # Notebook comparison scores are historical test-set results; live predictions use v3_direct only.
    comparison = [
        {"name": "Ridge", "rmse": 0.1054, "r2": 0.6990, "skill": 0.1411},
        {"name": "Random Forest", "rmse": 0.1048, "r2": 0.7024, "skill": 0.1506},
        {"name": "Gradient Boosting", "rmse": 0.1074, "r2": 0.6877, "skill": 0.1089},
        {"name": "LSTM", "rmse": 0.1127, "r2": 0.6560, "skill": 0.0183},
        {"name": "Ensemble", "rmse": 0.1050, "r2": 0.7012, "skill": 0.1474},
    ]

    return render_template(
        "models.html",
        model_ready=MODEL_READY,
        meta_ready=META_READY,
        champion=champion,
        metrics=metrics,
        description=description,
        feature_set=feature_set,
        comparison=comparison,
        anomaly_metrics={"precision": 0.89, "recall": 0.82, "f1": 0.84},
        trained_until=METADATA.get("trained_until", "unknown"),
        recent_actions=recent_actions,
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
        return render_template("error.html", message="Database connection failed, please try again later.")

    alerts_list = list(db.alerts.find({}).sort([("month", 1)]).limit(500))
    # Convert ObjectId to string for templates
    for a in alerts_list:
        a["_id"] = str(a["_id"])
        a["id"] = a["_id"]
    counts = {level: db.alerts.count_documents({"level": level}) for level in ("CRITICAL", "WARNING", "OK")}

    return render_template(
        "alerts.html",
        alerts=alerts_list,
        alert_counts=counts,
        is_admin=session.get("role") == "admin",
    )


@app.route("/alerts/<alert_id>/ack", methods=["POST"], endpoint="ack_alert")
@app.route("/alerts/<alert_id>/acknowledge", methods=["POST"], endpoint="acknowledge_alert")
@admin_required
def ack_alert(alert_id):
    db = _db_or_error()
    if db is None:
        return render_template("error.html", message="Database connection failed, please try again later.")

    db.alerts.update_one(
        {"_id": ObjectId(alert_id)},
        {"$set": {
            "acknowledged": True,
        }},
    )
    _audit(db, "alert_acknowledge", detail=f"Acknowledged alert {alert_id}")
    flash("Alert acknowledged.", "success")
    return redirect(url_for("alerts_page"))


@app.route("/threshold", methods=["GET", "POST"])
@admin_required
def threshold():
    db = _db_or_error()
    if db is None:
        return render_template("error.html", message="Database connection failed, please try again later.")

    if request.method == "POST":
        new_val = request.form.get("threshold", request.form.get("new_threshold"), type=float)
        if new_val is not None and new_val > 0:
            db.settings.update_one(
                {"key": "alert_threshold"},
                {"$set": {"value": new_val, "updated_by": session["username"], "updated_at": _now()}},
                upsert=True,
            )
            result = regenerate_alerts(db, new_val)
            _audit(
                db, "threshold_change",
            detail={"new_threshold": new_val, "counts": result},
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

    counts = {level: db.alerts.count_documents({"level": level}) for level in ("CRITICAL", "WARNING", "OK")}
    return render_template("threshold.html", threshold=current, alert_counts=counts)


# ==========================================================================
# USER MANAGEMENT
# ==========================================================================

@app.route("/users")
@admin_required
def users():
    db = _db_or_error()
    if db is None:
        return render_template("error.html", message="Database connection failed, please try again later.")
    users_list = list(db.users.find({}, {"password_hash": 0, "password": 0}).sort("username", 1))
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
        return render_template("error.html", message="Database connection failed, please try again later.")
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "analyst").strip().lower()
    full_name = request.form.get("full_name", "").strip()[:120]
    email = request.form.get("email", "").strip()[:254]
    if not username or role not in {"admin", "analyst"}:
        flash("Enter a username and choose a valid role.", "danger")
    elif len(password) < 12:
        flash("Use a password with at least 12 characters.", "danger")
    elif db.users.find_one({"username": username}):
        flash(f"User '{username}' already exists.", "warning")
    else:
        db.users.insert_one({
            "username": username,
            "password_hash": generate_password_hash(password),
            "role": role,
            "full_name": full_name,
            "email": email,
            "is_active": True,
            "created_at": _now(),
        })
        _audit(db, "user_create", detail={"username": username, "role": role})
        flash(f"User '{username}' created as {role}.", "success")
    return redirect(url_for("users"))


@app.route("/users/<user_id>/role", methods=["POST"])
@admin_required
def change_role(user_id):
    db = _db_or_error()
    if db is not None:
        new_role = request.form.get("role", "analyst").strip().lower()
        if not ObjectId.is_valid(user_id):
            abort(404)
        if new_role not in {"admin", "analyst"}:
            flash("Role must be Admin or Analyst.", "danger")
        elif user_id == session.get("user_id") and new_role != "admin":
            flash("You cannot remove your own Admin role.", "danger")
        else:
            db.users.update_one({"_id": ObjectId(user_id)}, {"$set": {"role": new_role}})
            _audit(db, "user_role_change", detail={"user_id": user_id, "role": new_role})
            flash("Role updated.", "success")
    return redirect(url_for("users"))


@app.route("/users/<user_id>/deactivate", methods=["POST"])
@admin_required
def deactivate_user(user_id):
    db = _db_or_error()
    if db is not None:
        if not ObjectId.is_valid(user_id):
            abort(404)
        if user_id == session.get("user_id"):
            flash("You cannot deactivate your own account.", "danger")
        else:
            db.users.update_one({"_id": ObjectId(user_id)}, {"$set": {"is_active": False}})
            _audit(db, "user_deactivate", detail=f"Deactivated user {user_id}")
            flash("User deactivated.", "success")
    return redirect(url_for("users"))


@app.route("/users/<user_id>/activate", methods=["POST"])
@admin_required
def activate_user(user_id):
    db = _db_or_error()
    if db is not None:
        if not ObjectId.is_valid(user_id):
            abort(404)
        db.users.update_one({"_id": ObjectId(user_id)}, {"$set": {"is_active": True}})
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
                {"$set": {"admin_reply": reply_text, "status": "replied"}},
            )
            _audit(db, "feedback_reply", detail={"feedback_id": feedback_id})
            flash("Reply sent.", "success")
    return redirect(url_for("admin_feedback"))


@app.route("/admin/feedback/<feedback_id>/close", methods=["POST"])
@admin_required
def close_feedback(feedback_id):
    db = _db_or_error()
    if db is not None:
        db.feedback.update_one(
            {"_id": ObjectId(feedback_id)},
            {"$set": {"status": "closed"}},
        )
        _audit(db, "feedback_close", detail={"feedback_id": feedback_id})
        flash("Feedback closed.", "success")
    return redirect(url_for("admin_feedback"))


@app.route("/feedback", methods=["GET", "POST"])
@login_required
def feedback():
    db = _db_or_error()
    if db is None:
        return render_template("error.html", message="Database connection failed, please try again later.")

    if request.method == "POST":
        subject = request.form.get("subject", "").strip()[:160]
        message = request.form.get("message", "").strip()[:5000]
        category = request.form.get("category", "feedback").strip().lower()
        if subject and message and category in {"support", "issue", "feedback"}:
            db.feedback.insert_one({
                "user_id": session["user_id"],
                "username": session["username"],
                "category": category,
                "subject": subject,
                "message": message,
                "status": "open",
                "admin_reply": None,
                "created_at": _now(),
            })
            _audit(db, "feedback_submit", detail={"category": category})
            flash("Feedback submitted. Thank you!", "success")
        else:
            flash("Choose a valid category and enter a subject and message.", "danger")

    my_feedback = list(
        db.feedback.find({"user_id": session["user_id"]}).sort([("created_at", -1)])
    )
    for fb in my_feedback:
        fb["_id"] = str(fb["_id"])

    return render_template("feedback.html", feedbacks=my_feedback)


@app.route("/admin/feedback", methods=["GET", "POST"])
@admin_required
def admin_feedback():
    db = _db_or_error()
    if db is None:
        return render_template("error.html", message="Database connection failed, please try again later.")

    if request.method == "POST":
        fb_id = request.form.get("feedback_id")
        action = request.form.get("action", "reply")

        if action == "reply":
            reply_text = request.form.get("reply", "").strip()
            if reply_text:
                db.feedback.update_one(
                    {"_id": ObjectId(fb_id)},
                    {"$set": {"admin_reply": reply_text, "status": "replied"}},
                )
                _audit(db, "feedback_reply", detail={"feedback_id": fb_id})
                flash("Reply sent.", "success")

        elif action == "close":
            db.feedback.update_one(
                {"_id": ObjectId(fb_id)},
                {"$set": {"status": "closed"}},
            )
            _audit(db, "feedback_close", detail={"feedback_id": fb_id})
            flash("Feedback closed.", "success")

    status_filter = request.args.get("status", "")
    feedback_query = {"status": status_filter} if status_filter in {"open", "replied", "closed"} else {}
    all_feedback = list(db.feedback.find(feedback_query).sort([("created_at", -1)]).limit(500))
    for fb in all_feedback:
        fb["_id"] = str(fb["_id"])
        fb["id"] = fb["_id"]

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
            "annual_ghg": db.annual_ghg.count_documents({}),
            "arctic_ice": db.arctic_ice.count_documents({}),
            "forecast": db.forecast.count_documents({}),
            "alerts": db.alerts.count_documents({}),
            "users": db.users.count_documents({}),
            "feedback": db.feedback.count_documents({}),
            "settings": db.settings.count_documents({}),
            "audit": db.audit.count_documents({}),
            "analysis_results": db.analysis_results.count_documents({}),
        }

    return render_template("health.html", info=info)


# ==========================================================================
# MAIN
# ==========================================================================

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=os.environ.get("FLASK_DEBUG") == "1")
