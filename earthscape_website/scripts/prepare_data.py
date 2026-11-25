#!/usr/bin/env python3
"""Convert the supplied NASA, NOAA MLO, and OWID source files to app CSVs."""
import argparse
import csv
import math
import os
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "source"
OUTPUT = ROOT / "data" / "cleaned"
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
NOTEBOOK_FORECAST = [
    ("2026-11-01", 1.501, 1.335, 1.667), ("2026-12-01", 1.540, 1.334, 1.747),
    ("2027-01-01", 1.527, 1.295, 1.758), ("2027-02-01", 1.496, 1.263, 1.729),
    ("2027-03-01", 1.476, 1.242, 1.709), ("2027-04-01", 1.393, 1.160, 1.626),
    ("2027-05-01", 1.356, 1.123, 1.589), ("2027-06-01", 1.345, 1.111, 1.580),
    ("2027-07-01", 1.348, 1.101, 1.594), ("2027-08-01", 1.332, 1.079, 1.585),
    ("2027-09-01", 1.345, 1.092, 1.598), ("2027-10-01", 1.353, 1.099, 1.606),
]


def numeric(value):
    if value is None or str(value).strip() in {"", "***", "-", "NA", "N/A"}:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def read_nasa(path):
    """Read NASA's global annual-by-month table (the first line is a title)."""
    rows = {}
    with path.open(newline="", encoding="utf-8-sig") as stream:
        first = stream.readline()
        if first.lstrip().startswith("Year,"):
            stream.seek(0)
        reader = csv.DictReader(stream)
        if not reader.fieldnames or "Year" not in reader.fieldnames:
            raise ValueError(f"Unrecognized NASA monthly table: {path}")
        for source_row in reader:
            try:
                year = int(source_row["Year"])
            except (KeyError, TypeError, ValueError):
                continue
            for month, label in enumerate(MONTHS, 1):
                temp = numeric(source_row.get(label))
                if temp is not None:
                    rows[(year, month)] = temp
    return rows


def read_mlo(path):
    """Read NOAA's comment-prefixed monthly Mauna Loa CSV; use its average ppm."""
    rows = {}
    with path.open(encoding="utf-8-sig") as stream:
        header_line = next((line for line in stream if line.lstrip().startswith("year,month,")), None)
        if header_line is None:
            raise ValueError(f"Could not find NOAA MLO CSV header in {path}")
        reader = csv.DictReader([header_line, *stream])
        for row in reader:
            try:
                key = (int(row["year"]), int(row["month"]))
            except (KeyError, TypeError, ValueError):
                continue
            ppm = numeric(row.get("average"))
            if ppm is not None and ppm > 0 and 1 <= key[1] <= 12:
                rows[key] = ppm
    return rows


def read_oni(path):
    """Read notebook-style date-indexed NOAA ONI or a year,month,oni CSV."""
    rows = {}
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        fields = set(reader.fieldnames or [])
        date_column = next((f for f in fields if f.strip().lower() in {"", "date", "unnamed: 0"}), None)
        value_column = "0" if "0" in fields else "oni" if "oni" in fields else None
        standard = {"year", "month", "oni"}.issubset(fields)
        if not standard and (date_column is None or value_column is None):
            raise ValueError("ONI file must have year,month,oni columns or a date-index/value layout.")
        for row in reader:
            if standard:
                try:
                    key = (int(row["year"]), int(row["month"]))
                except (TypeError, ValueError):
                    continue
                value = numeric(row.get("oni"))
            else:
                try:
                    parts = row[date_column].strip()[:7].split("-")
                    key = (int(parts[0]), int(parts[1]))
                except (KeyError, TypeError, ValueError, IndexError):
                    continue
                value = numeric(row.get(value_column))
            if value is not None and 1 <= key[1] <= 12:
                rows[key] = value
    return rows


def rolling_median(values, window=120, min_periods=30):
    """Centered rolling median matching pandas rolling(window, center=True)."""
    result = []
    left = (window - 1) // 2
    right = window // 2
    for index in range(len(values)):
        sample = [x for x in values[max(0, index-left):min(len(values), index+right+1)] if x is not None]
        result.append(median(sample) if len(sample) >= min_periods else None)
    return result


def residual_flags(temp_by_key):
    """Flag robust outliers in residuals from the trailing 12-month temperature level."""
    values = list(temp_by_key.values())
    deviations = []
    for i, value in enumerate(values):
        baseline = sum(values[i-12:i])/12 if i >= 12 else None
        deviations.append(value-baseline if baseline is not None else None)
    flags = []
    for i, deviation in enumerate(deviations):
        history = [x for x in deviations[max(0, i-120):i] if x is not None]
        if deviation is None or len(history) < 60:
            flags.append(False)
            continue
        center = median(history)
        mad = median([abs(x-center) for x in history]) * 1.4826
        flags.append(bool(mad > 0 and abs(deviation-center)/mad > 3.0))
    return dict(zip(temp_by_key, flags))


def fill_short_gaps(rows, max_gap=6):
    """Linear interpolation for bounded short gaps, as used by the notebook."""
    keys = sorted(rows)
    values = [rows[k] for k in keys]
    i = 0
    while i < len(values):
        if values[i] is not None:
            i += 1
            continue
        start = i
        while i < len(values) and values[i] is None:
            i += 1
        gap = i - start
        if start > 0 and i < len(values) and gap <= max_gap:
            lo, hi = values[start-1], values[i]
            for offset in range(gap):
                values[start+offset] = lo + (hi-lo) * (offset+1)/(gap+1)
    return dict(zip(keys, values))


def read_arctic(path):
    """Read NSIDC monthly extent in million square kilometres."""
    rows = {}
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.reader(stream)
        header = next(reader, [])
        if len(header) < 2:
            raise ValueError("NSIDC extent CSV must contain date and extent columns.")
        for row in reader:
            if len(row) < 2:
                continue
            try:
                date = row[0].strip()[:7] + "-01"
                year, month = map(int, date[:7].split("-"))
            except (TypeError, ValueError):
                continue
            value = numeric(row[1])
            if value is not None and 1 <= month <= 12:
                rows[(year, month)] = value
    return rows


def write_monthly(path, nasa_path, mlo_path, oni_path=None):
    temp = read_nasa(nasa_path)
    co2 = fill_short_gaps(read_mlo(mlo_path), max_gap=6)
    oni = read_oni(oni_path) if oni_path else {}
    # CPC notebook code month-aligns ONI and forward-fills at most three newest months.
    if oni:
        oni = fill_short_gaps(oni, max_gap=0)
        ordered_oni = sorted(oni)
        last_key = ordered_oni[-1]
        last_value = oni[last_key]
        for key in sorted(temp):
            if key > last_key and (key[0]-last_key[0])*12+key[1]-last_key[1] <= 3:
                oni[key] = last_value
    flags = residual_flags(temp)
    keys = sorted(temp)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=[
            "year", "month", "temp_anomaly", "co2_ppm", "oni", "is_anomaly", "anomaly_method", "source",
        ])
        writer.writeheader()
        for year, month in keys:
            writer.writerow({
                "year": year, "month": month, "temp_anomaly": temp[(year, month)],
                "co2_ppm": co2.get((year, month), ""), "oni": oni.get((year, month), ""),
                "is_anomaly": str(flags[(year, month)]).lower(),
                "anomaly_method": "residual_robust_z_120m",
                "source": "NASA GISTEMP; NOAA GML Mauna Loa; NOAA CPC ONI",
            })
    return len(keys), len(co2), len(oni)


def write_annual(path, owid_path):
    count = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with owid_path.open(newline="", encoding="utf-8-sig") as source, path.open("w", newline="", encoding="utf-8") as target:
        reader = csv.DictReader(source)
        required = {"country", "year", "co2", "methane", "nitrous_oxide", "total_ghg"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise ValueError(f"OWID file is missing expected fields: {sorted(required)}")
        writer = csv.DictWriter(target, fieldnames=[
            "year", "country", "co2_emissions", "total_ghg", "methane", "nitrous_oxide", "source",
        ])
        writer.writeheader()
        for row in reader:
            co2 = numeric(row.get("co2"))
            total = numeric(row.get("total_ghg"))
            if co2 is None and total is None:
                continue
            writer.writerow({
                "year": row["year"], "country": row["country"],
                "co2_emissions": "" if co2 is None else co2,
                "total_ghg": "" if total is None else total,
                "methane": "" if numeric(row.get("methane")) is None else numeric(row.get("methane")),
                "nitrous_oxide": "" if numeric(row.get("nitrous_oxide")) is None else numeric(row.get("nitrous_oxide")),
                "source": "Our World in Data (OWID)",
            })
            count += 1
    return count


def write_arctic(path, source_path):
    rows = read_arctic(source_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["month", "extent_million_km2", "source"])
        writer.writeheader()
        for (year, month), extent in sorted(rows.items()):
            writer.writerow({"month": f"{year:04d}-{month:02d}-01", "extent_million_km2": extent,
                             "source": "NSIDC Sea Ice Index"})
    return len(rows)


def write_forecast(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["month", "forecast", "lower", "upper", "model_version"])
        writer.writeheader()
        for month, forecast, lower, upper in NOTEBOOK_FORECAST:
            writer.writerow({"month": month, "forecast": forecast, "lower": lower,
                             "upper": upper, "model_version": "v3_direct"})
    return len(NOTEBOOK_FORECAST)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nasa", type=Path, default=SOURCE / "nasa_gistemp.csv")
    parser.add_argument("--mlo", type=Path, default=SOURCE / "noaa_mlo_co2.csv")
    parser.add_argument("--owid", type=Path, default=SOURCE / "owid_co2.csv")
    parser.add_argument("--oni", type=Path, default=SOURCE / "noaa_oni.csv")
    parser.add_argument("--arctic", type=Path, default=SOURCE / "nsidc_arctic_extent.csv")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    for source_path in (args.nasa, args.mlo, args.owid, args.oni, args.arctic):
        if not source_path.is_file():
            parser.error(f"Source file not found: {source_path}")
    monthly_count, co2_count, oni_count = write_monthly(
        args.output / "monthly_climate.csv", args.nasa, args.mlo, args.oni,
    )
    ghg_count = write_annual(args.output / "annual_ghg.csv", args.owid)
    arctic_count = write_arctic(args.output / "arctic_ice.csv", args.arctic)
    forecast_count = write_forecast(args.output / "forecast.csv")
    print(f"Wrote {monthly_count} NASA monthly records ({co2_count} MLO CO2 values, {oni_count} ONI values).")
    print(f"Wrote {ghg_count} OWID annual country/year rows.")
    print(f"Wrote {arctic_count} NSIDC monthly sea-ice extent rows.")
    print(f"Wrote {forecast_count} stored v3_direct forecast months from the notebook output.")


if __name__ == "__main__":
    main()
