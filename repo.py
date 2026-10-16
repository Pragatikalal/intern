"""Repository functions: every SQL statement lives here (database access layer, part 2)."""
import pandas as pd
from db import get_db


# ---------- users ----------
def count_users():
    return get_db().execute("SELECT COUNT(*) FROM users").fetchone()[0]


def create_user(username, password_hash, role):
    db = get_db()
    db.execute("INSERT INTO users (username, password_hash, role) VALUES (?,?,?)",
               (username, password_hash, role))
    db.commit()


def get_user_by_name(username):
    return get_db().execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()


def get_user(user_id):
    return get_db().execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()


# ---------- consumers ----------
def list_consumers():
    return get_db().execute("SELECT * FROM consumers ORDER BY name").fetchall()


def get_consumer(consumer_id):
    return get_db().execute("SELECT * FROM consumers WHERE consumer_id=?", (consumer_id,)).fetchone()


def create_consumer(name, address, meter_no, category):
    db = get_db()
    db.execute("INSERT INTO consumers (name,address,meter_no,category) VALUES (?,?,?,?)",
               (name, address, meter_no, category))
    db.commit()


def update_consumer(consumer_id, name, address, meter_no, category):
    db = get_db()
    db.execute("UPDATE consumers SET name=?, address=?, meter_no=?, category=? WHERE consumer_id=?",
               (name, address, meter_no, category, consumer_id))
    db.commit()


def delete_consumer(consumer_id):
    db = get_db()
    db.execute("DELETE FROM consumers WHERE consumer_id=?", (consumer_id,))
    db.commit()


# ---------- meter readings ----------
def readings_df(consumer_id=None):
    """Readings joined with consumer info as a DataFrame (datetime-typed reading_date)."""
    sql = """SELECT r.consumer_id, c.name, c.category, r.reading_date, r.units_consumed, r.meter_reading
             FROM meter_readings r JOIN consumers c ON c.consumer_id = r.consumer_id"""
    params = ()
    if consumer_id:
        sql += " WHERE r.consumer_id = ?"
        params = (consumer_id,)
    df = pd.read_sql_query(sql + " ORDER BY r.reading_date", get_db(), params=params)
    df["reading_date"] = pd.to_datetime(df["reading_date"])
    return df


def insert_readings(rows):
    """rows: iterable of (consumer_id, reading_date_str, units, meter_reading). Upserts on (consumer, date)."""
    db = get_db()
    db.executemany("""INSERT INTO meter_readings (consumer_id, reading_date, units_consumed, meter_reading)
                      VALUES (?,?,?,?)
                      ON CONFLICT(consumer_id, reading_date) DO UPDATE SET
                        units_consumed=excluded.units_consumed, meter_reading=excluded.meter_reading""", rows)
    db.commit()


def reading_count():
    return get_db().execute("SELECT COUNT(*) FROM meter_readings").fetchone()[0]


# ---------- predictions ----------
def save_predictions(rows):
    db = get_db()
    db.executemany("""INSERT INTO predictions (consumer_id, prediction_date, predicted_units, model_name,
                      run_id, lower_bound, upper_bound, mae, rmse, r2, created_by)
                      VALUES (:consumer_id,:prediction_date,:predicted_units,:model_name,:run_id,
                              :lower_bound,:upper_bound,:mae,:rmse,:r2,:created_by)""", rows)
    db.commit()


def list_runs(consumer_id=None, limit=100):
    sql = """SELECT p.run_id, p.consumer_id, c.name, p.model_name,
                    MIN(p.prediction_date) AS start_date, MAX(p.prediction_date) AS end_date,
                    COUNT(*) AS days, ROUND(SUM(p.predicted_units),1) AS total_units,
                    MAX(p.rmse) AS rmse, MAX(p.r2) AS r2, MAX(p.created_at) AS created_at, u.username
             FROM predictions p JOIN consumers c ON c.consumer_id=p.consumer_id
             LEFT JOIN users u ON u.user_id=p.created_by"""
    params = []
    if consumer_id:
        sql += " WHERE p.consumer_id=?"
        params.append(consumer_id)
    sql += " GROUP BY p.run_id ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    return get_db().execute(sql, params).fetchall()


def get_run(run_id):
    return get_db().execute("""SELECT p.*, c.name FROM predictions p
                               JOIN consumers c ON c.consumer_id=p.consumer_id
                               WHERE run_id=? ORDER BY prediction_date""", (run_id,)).fetchall()
