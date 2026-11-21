#!/usr/bin/env python3
"""Load cleaned notebook CSV outputs into MongoDB with validation and upserts."""
import csv
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv
from pymongo import ASCENDING, MongoClient, UpdateOne

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(ROOT, ".env"))
sys.path.insert(0, ROOT)
from alerts import regenerate_alerts  # noqa: E402

DATA_DIR = os.environ.get("DATA_DIR", os.path.join(ROOT, "data", "cleaned"))
OFFICIAL_FORECAST = [
    ("2026-11-01", 1.501, 1.335, 1.667), ("2026-12-01", 1.540, 1.334, 1.747),
    ("2027-01-01", 1.527, 1.295, 1.758), ("2027-02-01", 1.496, 1.263, 1.729),
    ("2027-03-01", 1.476, 1.242, 1.709), ("2027-04-01", 1.393, 1.160, 1.626),
    ("2027-05-01", 1.356, 1.123, 1.589), ("2027-06-01", 1.345, 1.111, 1.580),
    ("2027-07-01", 1.348, 1.101, 1.594), ("2027-08-01", 1.332, 1.079, 1.585),
    ("2027-09-01", 1.345, 1.092, 1.598), ("2027-10-01", 1.353, 1.099, 1.606),
]


def csv_rows(filename):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Required cleaned CSV not found: {path}")
    with open(path, newline="", encoding="utf-8-sig") as stream:
        yield from csv.DictReader(stream)


def number(row, key, required=False):
    value = row.get(key, "")
    if value is None or str(value).strip() == "":
        if required:
            raise ValueError(f"{key} is empty")
        return None
    return float(value)


def monthly_records():
    records, skipped = [], 0
    for line, row in enumerate(csv_rows("monthly_climate.csv"), start=2):
        try:
            year = int(row.get("year", ""))
            month = int(row.get("month", ""))
            if year < 1880 or not 1 <= month <= 12:
                raise ValueError("invalid year or month")
            temp = number(row, "temp_anomaly", required=True)
            co2 = number(row, "co2_ppm")
            oni = number(row, "oni")
            anomaly_text = str(row.get("is_anomaly", "false")).strip().lower()
            if anomaly_text not in {"true", "false", "1", "0", "yes", "no"}:
                raise ValueError("is_anomaly must be boolean")
            records.append({
                "year": year, "month": month, "date": f"{year:04d}-{month:02d}-01",
                "temp_anomaly": temp, "co2_ppm": co2, "oni": oni,
                "is_anomaly": anomaly_text in {"true", "1", "yes"},
                "anomaly_method": row.get("anomaly_method") or "residual",
                "source": row.get("source") or "NASA GISS / NOAA / CPC ONI",
            })
        except (TypeError, ValueError) as exc:
            skipped += 1
            print(f"monthly_climate.csv:{line}: skipped invalid row ({exc})")
    return records, skipped


def ghg_records():
    records, skipped = [], 0
    for line, row in enumerate(csv_rows("annual_ghg.csv"), start=2):
        try:
            year = int(row.get("year", ""))
            country = (row.get("country") or "").strip()
            if year < 1750 or not country:
                raise ValueError("year or country is missing/invalid")
            co2 = number(row, "co2_emissions")
            total_ghg = number(row, "total_ghg")
            if co2 is None and total_ghg is None:
                raise ValueError("both CO2 emissions and total GHG are empty")
            records.append({
                "year": year, "country": country,
                "co2_emissions": co2,
                "total_ghg": total_ghg,
                "methane": number(row, "methane"),
                "nitrous_oxide": number(row, "nitrous_oxide"),
                "source": row.get("source") or "Our World in Data (OWID)",
            })
        except (TypeError, ValueError) as exc:
            skipped += 1
            print(f"annual_ghg.csv:{line}: skipped invalid row ({exc})")
    return records, skipped


def arctic_records():
    records, skipped = [], 0
    for line, row in enumerate(csv_rows("arctic_ice.csv"), start=2):
        try:
            month = datetime.strptime(row.get("month", "")[:10], "%Y-%m-%d").strftime("%Y-%m-01")
            extent = number(row, "extent_million_km2", required=True)
            if extent <= 0:
                raise ValueError("extent must be positive")
            records.append({"month": month, "extent_million_km2": extent,
                            "source": row.get("source") or "NSIDC Sea Ice Index"})
        except (TypeError, ValueError) as exc:
            skipped += 1
            print(f"arctic_ice.csv:{line}: skipped invalid row ({exc})")
    return records, skipped


def connect_db():
    uri = os.environ.get("MONGO_URI")
    if not uri:
        raise RuntimeError("Set MONGO_URI in earthscape_website/.env before loading data.")
    client = MongoClient(uri, serverSelectionTimeoutMS=8000)
    client.admin.command("ping")
    db = client["earthscape"]
    # Index natural keys before bulk upserts to keep first and repeat loads fast and unique.
    db.monthly_climate.create_index([("date", ASCENDING)])
    db.monthly_climate.create_index([("year", ASCENDING), ("month", ASCENDING)], unique=True)
    db.annual_ghg.create_index([("year", ASCENDING), ("country", ASCENDING)], unique=True)
    db.arctic_ice.create_index([("month", ASCENDING)], unique=True)
    db.forecast.create_index([("month", ASCENDING)], unique=True)
    db.alerts.create_index([("month", ASCENDING)], unique=True)
    return client, db


def main():
    monthly, bad_monthly = monthly_records()
    ghg, bad_ghg = ghg_records()
    arctic, bad_arctic = arctic_records()
    if not monthly or not ghg or not arctic:
        raise RuntimeError("Monthly climate, annual GHG, and Arctic ice CSVs must contain valid rows; no database changes made.")
    client, db = connect_db()
    try:
        now = datetime.now(timezone.utc)
        # Record a generation marker in the existing audit collection so app
        # processes invalidate cached values without expanding the settings schema.
        db.audit.insert_one({
            "username": "system", "action": "data_load",
            "details": {"started_at": now.isoformat()}, "timestamp": now,
        })
        db.monthly_climate.bulk_write([
            UpdateOne({"year": r["year"], "month": r["month"]}, {"$set": r}, upsert=True)
            for r in monthly
        ], ordered=False)
        db.annual_ghg.bulk_write([
            UpdateOne({"year": r["year"], "country": r["country"]}, {"$set": r}, upsert=True)
            for r in ghg
        ], ordered=False)
        db.arctic_ice.bulk_write([
            UpdateOne({"month": r["month"]}, {"$set": r}, upsert=True)
            for r in arctic
        ], ordered=False)

        forecast_rows = []
        forecast_path = os.path.join(DATA_DIR, "forecast.csv")
        if os.path.exists(forecast_path):
            for line, row in enumerate(csv_rows("forecast.csv"), start=2):
                try:
                    month = datetime.strptime(row["month"][:7] + "-01", "%Y-%m-%d").strftime("%Y-%m-01")
                    forecast_rows.append({"month": month, "forecast": number(row, "forecast", True),
                                          "lower": number(row, "lower", True), "upper": number(row, "upper", True),
                                          "model_version": row.get("model_version") or "v3_direct"})
                except (KeyError, TypeError, ValueError) as exc:
                    print(f"forecast.csv:{line}: skipped invalid row ({exc})")
        else:
            forecast_rows = [dict(month=m, forecast=f, lower=lo, upper=hi, model_version="v3_direct")
                             for m, f, lo, hi in OFFICIAL_FORECAST]
        if len(forecast_rows) != 12:
            raise RuntimeError("Forecast data must contain exactly 12 valid months.")
        db.forecast.bulk_write([
            UpdateOne({"month": r["month"]}, {"$set": {**r, "generated_at": now}}, upsert=True)
            for r in forecast_rows
        ], ordered=False)

        db.settings.update_one({"key": "alert_threshold"}, {"$setOnInsert": {
            "key": "alert_threshold", "value": 1.50, "updated_by": "system_seed", "updated_at": now,
        }}, upsert=True)
        result = regenerate_alerts(db)
        print(f"Loaded {len(monthly)} monthly rows ({bad_monthly} skipped), {len(ghg)} GHG rows ({bad_ghg} skipped), "
              f"{len(arctic)} Arctic-ice rows ({bad_arctic} skipped), "
              f"12 forecast months; alerts {result['critical']} CRITICAL / {result['warning']} WARNING / {result['ok']} OK.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
