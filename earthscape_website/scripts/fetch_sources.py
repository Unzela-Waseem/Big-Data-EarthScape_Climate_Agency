#!/usr/bin/env python3
"""Fetch optional GISTEMP NetCDF and recent Open-Meteo daily city weather."""

from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sys
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from db import get_db  # noqa: E402
from live_weather import LOCATIONS  # noqa: E402

SOURCE_NC = PROJECT_ROOT / "data" / "source" / "gistemp_grid.nc"
DAILY_SOURCE = "Open-Meteo daily weather API (model-derived)"
NASA_SOURCE = "NASA GISTEMP NetCDF grid"


def _get_json(url):
    request = Request(url, headers={"User-Agent": "EarthScape-Climate-Agency/1.0"})
    with urlopen(request, timeout=25) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_gistemp_netcdf(db):
    """Convert an optional gridded NASA dataset into weighted monthly anomalies."""
    if not SOURCE_NC.is_file():
        print(f"NASA NetCDF skipped: {SOURCE_NC.name} is not present.")
        return 0
    try:
        import xarray as xr
    except ImportError:
        print("NASA NetCDF skipped: install xarray and netCDF4 to read the optional file.")
        return 0

    try:
        with xr.open_dataset(SOURCE_NC) as dataset:
            time_name = next((name for name in dataset.coords if name.lower() in {"time", "date"}), None)
            lat_name = next((name for name in dataset.coords if name.lower() in {"lat", "latitude"}), None)
            lon_name = next((name for name in dataset.coords if name.lower() in {"lon", "longitude"}), None)
            if not all((time_name, lat_name, lon_name)):
                raise ValueError("NetCDF must have time, latitude and longitude coordinates")
            time_dim = dataset[time_name].dims[0]
            lat_dim = dataset[lat_name].dims[0]
            lon_dim = dataset[lon_name].dims[0]
            candidates = ["tempanomaly", "temp_anomaly", "temperature_anomaly", "anomaly", "tas"]
            variable = next((dataset[name] for name in candidates if name in dataset.data_vars), None)
            if variable is None:
                variable = next((v for v in dataset.data_vars.values()
                                 if time_dim in v.dims and lat_dim in v.dims and lon_dim in v.dims), None)
            if variable is None:
                raise ValueError("No gridded temperature variable with time/latitude/longitude dimensions")
            variable = variable.squeeze(drop=True)
            extra_dims = [dim for dim in variable.dims if dim not in {time_dim, lat_dim, lon_dim}]
            if extra_dims:
                variable = variable.isel({dim: 0 for dim in extra_dims})
            variable = variable.transpose(time_dim, lat_dim, lon_dim)
            values = np.asarray(variable.values, dtype=float)
            latitudes = np.asarray(dataset[lat_name].values, dtype=float)
            weights = np.cos(np.deg2rad(latitudes)).clip(0)
            valid = np.isfinite(values)
            numerator = np.nansum(values * weights[None, :, None], axis=(1, 2))
            denominator = np.sum(valid * weights[None, :, None], axis=(1, 2))
            global_mean = np.divide(numerator, denominator, out=np.full_like(numerator, np.nan), where=denominator > 0)
            dates = pd.to_datetime(dataset[time_name].values)
            series = pd.Series(global_mean, index=dates).groupby(pd.Index(dates).to_period("M")).mean()
            baseline = series[(series.index >= "1951-01") & (series.index <= "1980-12")]
            if baseline.empty:
                raise ValueError("No 1951–1980 values available to calculate the GISTEMP anomaly baseline")
            monthly_baseline = baseline.groupby(baseline.index.month).mean()
            rows = []
            for period, mean in series.items():
                if pd.isna(mean) or period.month not in monthly_baseline:
                    continue
                anomaly = float(mean - monthly_baseline[period.month])
                rows.append({
                    "year": int(period.year), "month": int(period.month),
                    "date": f"{period.year:04d}-{period.month:02d}-01",
                    "temp_anomaly": anomaly, "source": NASA_SOURCE,
                })
    except Exception as exc:  # noqa: BLE001
        print(f"NASA NetCDF skipped: {type(exc).__name__}: {exc}")
        return 0

    inserted = updated = 0
    for row in rows:
        # Keep the established primary climate features when a month exists,
        # while retaining the independent gridded NASA value for traceability.
        result = db.monthly_climate.update_one(
            {"year": row["year"], "month": row["month"]},
            {"$set": {"gistemp_grid_anomaly": row["temp_anomaly"], "gistemp_grid_source": NASA_SOURCE},
             "$setOnInsert": row}, upsert=True,
        )
        inserted += int(result.upserted_id is not None)
        updated += int(result.upserted_id is None and result.modified_count > 0)
    print(f"NASA GISTEMP NetCDF: {len(rows)} monthly points scanned; {inserted} inserted, {updated} stored alongside existing months.")
    return inserted + updated


def fetch_station_daily(db, today=None):
    """Fetch the prior 30 calendar days for the three configured cities."""
    today = today or date.today()
    end_date = today - timedelta(days=1)
    start_date = today - timedelta(days=30)
    fetched_at = datetime.now(timezone.utc)
    inserted = updated = skipped = 0
    for city, location in LOCATIONS.items():
        params = urlencode({
            "latitude": location["latitude"], "longitude": location["longitude"],
            "start_date": start_date.isoformat(), "end_date": end_date.isoformat(),
            "daily": "temperature_2m_mean,temperature_2m_max,temperature_2m_min",
            "temperature_unit": "celsius", "timezone": "auto",
        })
        try:
            payload = _get_json(f"https://archive-api.open-meteo.com/v1/archive?{params}")
            daily = payload.get("daily") or {}
            dates = daily.get("time") or []
            means = daily.get("temperature_2m_mean") or []
            maxima = daily.get("temperature_2m_max") or []
            minima = daily.get("temperature_2m_min") or []
            for index, day in enumerate(dates):
                mean = means[index] if index < len(means) else None
                if mean is None:
                    skipped += 1
                    continue
                doc = {
                    "city": city, "date": day,
                    "temp_mean": float(mean),
                    "temp_max": float(maxima[index]) if index < len(maxima) and maxima[index] is not None else None,
                    "temp_min": float(minima[index]) if index < len(minima) and minima[index] is not None else None,
                    "source": DAILY_SOURCE, "fetched_at": fetched_at,
                }
                result = db.station_daily.update_one(
                    {"city": city, "date": day}, {"$set": doc}, upsert=True,
                )
                inserted += int(result.upserted_id is not None)
                updated += int(result.upserted_id is None and result.modified_count > 0)
        except Exception as exc:  # noqa: BLE001
            print(f"{location['name']} daily weather failed ({type(exc).__name__}); continuing.")
    print(f"Open-Meteo daily weather: inserted {inserted}, updated {updated}, skipped {skipped} rows across {len(LOCATIONS)} cities.")
    print(f"Date window requested: {start_date.isoformat()} through {end_date.isoformat()} (model-derived; not station instruments).")
    return {"inserted": inserted, "updated": updated, "skipped": skipped}


def main():
    db = get_db()
    if db is None:
        print("MongoDB unavailable; no sources were loaded.", file=sys.stderr)
        return 1
    fetch_gistemp_netcdf(db)
    fetch_station_daily(db)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
