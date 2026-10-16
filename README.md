# EnergyIQ - Electricity Consumption Analytics & Demand Prediction (Project 17)

Flask + Pandas + scikit-learn + Jinja + Chart.js, SQLite storage.

## Run
    pip install -r requirements.txt
    python seed_data.py        # demo users, 5 consumers, 1 year of hourly readings (admin / admin12345)
    python app.py              # http://127.0.0.1:5000
Set `SECRET_KEY` in the environment for any non-demo use. Delete `instance/energy.db` to reset.

## Layout (separation of concerns)
| Layer | Files |
|---|---|
| Presentation | `views.py`, `auth.py` (routes), `templates/`, `static/` |
| Business logic | `services/analytics.py` (Pandas), `services/forecast.py` (ML), `services/ingest.py` (CSV validation) |
| Database access | `db.py` (connection), `repo.py` (all SQL), `schema.sql` |

## CSV format
`meter_no, reading_date, units_consumed[, meter_reading]` - daily (`2026-03-01`) or hourly (`2026-03-01 18:00`). See `sample_upload.csv`.

## Notes
- `predictions` adds `run_id, lower_bound, upper_bound, mae, rmse, r2, created_at, created_by` to the spec's columns for history/audit.
- Models are trained per consumer, so category needs no encoding there; weekday/month are cyclically encoded and features scaled for linear models. Best model by hold-out RMSE is saved to `models/`.
- Roles: first registered user is `admin` (manage consumers); others are `analyst`.
