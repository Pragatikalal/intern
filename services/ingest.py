"""Validation and parsing of uploaded meter CSVs."""
import os
import uuid
import pandas as pd
from werkzeug.utils import secure_filename

REQUIRED = {"meter_no", "reading_date", "units_consumed"}


def allowed(filename, allowed_ext):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_ext


def save_upload(file_storage, folder):
    """Store under a sanitised, collision-proof name."""
    os.makedirs(folder, exist_ok=True)
    safe = secure_filename(file_storage.filename) or "upload.csv"
    path = os.path.join(folder, f"{uuid.uuid4().hex[:10]}_{safe}")
    file_storage.save(path)
    return path


def parse_csv(path, meter_map, max_rows):
    """Returns (rows, report). rows = tuples ready for repo.insert_readings."""
    try:
        df = pd.read_csv(path, nrows=max_rows + 1)
    except Exception as exc:
        raise ValueError(f"Could not read CSV: {exc}")
    df.columns = [c.strip().lower() for c in df.columns]
    missing = REQUIRED - set(df.columns)
    if missing:
        raise ValueError("Missing required column(s): " + ", ".join(sorted(missing)))
    if len(df) > max_rows:
        raise ValueError(f"File exceeds the {max_rows:,} row limit.")
    total = len(df)

    df["reading_date"] = pd.to_datetime(df["reading_date"], errors="coerce")
    df["units_consumed"] = pd.to_numeric(df["units_consumed"], errors="coerce")
    df["meter_reading"] = pd.to_numeric(df.get("meter_reading"), errors="coerce") if "meter_reading" in df else float("nan")
    bad = df["reading_date"].isna() | df["units_consumed"].isna() | (df["units_consumed"] < 0)
    df["consumer_id"] = df["meter_no"].astype(str).str.strip().map(meter_map)
    unknown = (~bad) & df["consumer_id"].isna()
    good = df[~bad & ~unknown].drop_duplicates(["consumer_id", "reading_date"], keep="last")

    rows = [(int(r.consumer_id), r.reading_date.strftime("%Y-%m-%d %H:%M:%S"), float(r.units_consumed),
             None if pd.isna(r.meter_reading) else float(r.meter_reading)) for r in good.itertuples()]
    return rows, {"total": total, "imported": len(rows), "invalid": int(bad.sum()),
                  "unknown_meter": int(unknown.sum()),
                  "unknown_meters": sorted(df.loc[unknown, "meter_no"].astype(str).unique())[:5]}
