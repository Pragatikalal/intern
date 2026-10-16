CREATE TABLE IF NOT EXISTS users (
    user_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'analyst' CHECK (role IN ('admin','analyst'))
);

CREATE TABLE IF NOT EXISTS consumers (
    consumer_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    address     TEXT,
    meter_no    TEXT NOT NULL UNIQUE,
    category    TEXT NOT NULL DEFAULT 'Residential'
);

CREATE TABLE IF NOT EXISTS meter_readings (
    reading_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    consumer_id    INTEGER NOT NULL REFERENCES consumers(consumer_id) ON DELETE CASCADE,
    reading_date   TEXT NOT NULL,              -- 'YYYY-MM-DD HH:MM:SS' (daily or hourly)
    units_consumed REAL NOT NULL CHECK (units_consumed >= 0),
    meter_reading  REAL,
    UNIQUE (consumer_id, reading_date)
);
CREATE INDEX IF NOT EXISTS idx_readings_consumer_date ON meter_readings(consumer_id, reading_date);

-- One row per forecast day. run_id groups a forecast run; created_at / metrics give an audit trail.
CREATE TABLE IF NOT EXISTS predictions (
    prediction_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    consumer_id     INTEGER NOT NULL REFERENCES consumers(consumer_id) ON DELETE CASCADE,
    prediction_date TEXT NOT NULL,
    predicted_units REAL NOT NULL,
    model_name      TEXT NOT NULL,
    run_id          TEXT NOT NULL,
    lower_bound     REAL,
    upper_bound     REAL,
    mae             REAL,
    rmse            REAL,
    r2              REAL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    created_by      INTEGER REFERENCES users(user_id)
);
CREATE INDEX IF NOT EXISTS idx_pred_run ON predictions(run_id);
