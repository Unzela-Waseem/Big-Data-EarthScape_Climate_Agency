# Prepared climate data

These app-ready CSVs are generated from the supplied notebook sources under `data/source/` by running `python scripts/prepare_data.py`.

Current source/output counts:

- NASA GISTEMP: 1,762 monthly temperature records, 1880-01 through 2026-10.
- NOAA GML Mauna Loa: 823 monthly CO₂ observations (use the `average` ppm field).
- NOAA CPC ONI: 921 monthly values, 1950-01 through 2026-09; October 2026 is forward-filled once as in the notebook.
- OWID: 44,008 country/year rows with at least CO₂ emissions or total GHG available.
- NSIDC: 576 Arctic sea-ice extent records, 1978-11 through 2026-10, in million km².

## Output schemas

`monthly_climate.csv`:

```text
year,month,temp_anomaly,co2_ppm,oni,is_anomaly,anomaly_method,source
```

NASA temperature values are °C anomalies on the 1951–1980 GISTEMP baseline. NOAA MLO values are ppm. The ONI CSV is monthly date-indexed, as produced by the provided notebook; the preparation script reads its index and aligns month keys. CO₂/ONI are kept blank where no measurement exists, except the notebook's one-month latest ONI forward fill. `is_anomaly` is computed by applying robust-z scoring to residuals from a trailing 12-month mean, using the trailing 120-month median/MAD and threshold 3. The detector flags observations but does not remove them; its stored method label is `residual_robust_z_120m`.

`annual_ghg.csv`:

```text
year,country,co2_emissions,total_ghg,methane,nitrous_oxide,source
```

These fields come from OWID `co2`, `total_ghg`, `methane`, and `nitrous_oxide`; original missing values remain blank. The loader keeps country/year values when either CO₂ or total GHG is available. Dashboard totals are filtered to `country=World`.

`arctic_ice.csv`:

```text
month,extent_million_km2,source
```

Values are the provided NSIDC monthly Arctic extent series. The website charts these observed extents; the notebook remains the source for the reported regional warming and impact-model skill metrics.

`forecast.csv` contains the 12 stored `v3_direct` forecast rows and interval bounds from the executed notebook output. The Prediction page can compute on demand from the pickle and loaded history; this stored series powers the Forecast page and is the documented fallback.

## Regenerate and load

```bash
python scripts/prepare_data.py
python scripts/load_data.py
```

The preparation script defaults to the supplied files under `data/source/`; optional `--nasa`, `--mlo`, `--oni`, `--owid`, `--arctic`, and `--output` flags select alternate files/folders. The loader validates inputs and upserts MongoDB by month or year/country. Configure the rotated Atlas URI in local `.env` before loading. No model retraining occurs: the website's `v3_direct` prediction endpoint loads and uses `model/direct_models.pkl`.
