"""
EarthScape Climate Agency — Alert Generation Logic
Rule:
    threshold T (from settings collection, default 1.50)
    forecast F  >=  T        → CRITICAL
    forecast F  >= 0.9 * T   → WARNING
    otherwise                → OK

With default threshold 1.50 and the standard 12-month forecast the
distribution is 3 CRITICAL, 5 WARNING, 4 OK.
"""

from datetime import datetime, timezone


def classify(forecast_value, threshold):
    """Return alert level string for a single forecast value."""
    if forecast_value >= threshold:
        return "CRITICAL"
    if forecast_value >= 0.9 * threshold:
        return "WARNING"
    return "OK"


def regenerate_alerts(db, threshold=None):
    """
    Rebuild the ``alerts`` collection from the current ``forecast``
    documents and the active threshold.

    Parameters
    ----------
    db : pymongo.database.Database
        The *earthscape* database handle.
    threshold : float or None
        If *None*, the value is read from the ``settings`` collection
        (key ``"alert_threshold"``), falling back to 1.50.

    Returns
    -------
    dict
        ``{"inserted": int, "critical": int, "warning": int, "ok": int}``
    """
    if db is None:
        return {"inserted": 0, "critical": 0, "warning": 0, "ok": 0, "error": "No DB"}

    # --- Resolve threshold ---------------------------------------------------
    if threshold is None:
        settings = db.settings.find_one({"key": "alert_threshold"})
        threshold = float(settings["value"]) if settings else 1.50

    # --- Fetch forecasts -----------------------------------------------------
    forecasts = list(db.forecast.find({}).sort([("horizon", 1)]))
    if not forecasts:
        return {"inserted": 0, "critical": 0, "warning": 0, "ok": 0,
                "error": "No forecast documents"}

    # --- Build new alerts ----------------------------------------------------
    now = datetime.now(timezone.utc)
    alerts = []
    counts = {"CRITICAL": 0, "WARNING": 0, "OK": 0}

    for fc in forecasts:
        forecast_val = float(fc.get("forecast", 0))
        level = classify(forecast_val, threshold)
        counts[level] += 1
        month = fc.get("month") or fc.get("date")
        if hasattr(month, "strftime"):
            month = month.strftime("%Y-%m-01")
        elif month:
            month = str(month)[:7] + "-01"
        message = {
            "CRITICAL": f"Forecast {forecast_val:.3f} °C meets or exceeds the {threshold:.2f} °C threshold.",
            "WARNING": f"Forecast {forecast_val:.3f} °C is within 10% of the {threshold:.2f} °C threshold.",
            "OK": f"Forecast {forecast_val:.3f} °C is below the warning range.",
        }[level]
        alerts.append({
            "month": month,
            "forecast_value": forecast_val,
            "threshold_used": threshold,
            "level": level,
            "message": message,
            "acknowledged": False,
            "created_at": now,
        })

    # --- Replace old alerts (no duplicates) ----------------------------------
    db.alerts.delete_many({})
    if alerts:
        db.alerts.insert_many(alerts)

    return {
        "inserted": len(alerts),
        "critical": counts["CRITICAL"],
        "warning": counts["WARNING"],
        "ok": counts["OK"],
    }
