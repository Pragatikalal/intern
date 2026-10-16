"""Presentation layer: routes validate input, call services/repo, render templates or JSON."""
import io
import sqlite3
import uuid
import pandas as pd
from flask import (Blueprint, Response, current_app, flash, g, jsonify, redirect,
                   render_template, request, url_for)
import repo
from auth import login_required, role_required
from services import analytics, forecast, ingest

bp = Blueprint("main", __name__)
CATEGORIES = ["Residential", "Commercial", "Industrial", "Educational"]


def _cid():
    v = request.args.get("consumer_id", "")
    return int(v) if v.isdigit() else None


def _filtered(cid=None):
    df = repo.readings_df(cid if cid is not None else _cid())
    return analytics.filter_dates(df, request.args.get("start"), request.args.get("end"))


# ---------------- dashboard ----------------
@bp.route("/")
@bp.route("/dashboard")
@login_required
def dashboard():
    cid = _cid()
    df = repo.readings_df(cid)
    return render_template("dashboard.html", consumers=repo.list_consumers(), cid=cid,
                           summary=analytics.descriptive(df), alerts=analytics.alerts(df))


# ---------------- consumers ----------------
@bp.route("/consumers")
@login_required
def consumers():
    return render_template("consumers.html", consumers=repo.list_consumers(), categories=CATEGORIES,
                           edit=repo.get_consumer(request.args.get("edit", type=int)) if request.args.get("edit") else None)


@bp.route("/consumers/save", methods=["POST"])
@role_required("admin")
def consumer_save():
    f = request.form
    name, meter, cat = f.get("name", "").strip(), f.get("meter_no", "").strip(), f.get("category", "")
    if not name or not meter or cat not in CATEGORIES:
        flash("Name, meter number and a valid category are required.", "danger")
        return redirect(url_for("main.consumers"))
    try:
        if f.get("consumer_id"):
            repo.update_consumer(int(f["consumer_id"]), name, f.get("address", "").strip(), meter, cat)
            flash("Consumer updated.", "success")
        else:
            repo.create_consumer(name, f.get("address", "").strip(), meter, cat)
            flash("Consumer added.", "success")
    except sqlite3.IntegrityError:
        flash("That meter number already exists.", "danger")
    return redirect(url_for("main.consumers"))


@bp.route("/consumers/<int:consumer_id>/delete", methods=["POST"])
@role_required("admin")
def consumer_delete(consumer_id):
    repo.delete_consumer(consumer_id)
    flash("Consumer and linked readings/predictions deleted.", "info")
    return redirect(url_for("main.consumers"))


# ---------------- upload / data entry ----------------
@bp.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    report = None
    if request.method == "POST":
        file = request.files.get("file")
        if not file or not file.filename:
            flash("Choose a CSV file.", "danger")
        elif not ingest.allowed(file.filename, current_app.config["ALLOWED_EXTENSIONS"]):
            flash("Only .csv files are accepted.", "danger")
        else:
            path = ingest.save_upload(file, current_app.config["UPLOAD_FOLDER"])
            meter_map = {c["meter_no"]: c["consumer_id"] for c in repo.list_consumers()}
            try:
                rows, report = ingest.parse_csv(path, meter_map, current_app.config["MAX_UPLOAD_ROWS"])
                repo.insert_readings(rows)
                flash(f"Imported {report['imported']} of {report['total']} rows.", "success")
            except ValueError as exc:
                flash(str(exc), "danger")
    return render_template("upload.html", consumers=repo.list_consumers(), report=report,
                           reading_count=repo.reading_count())


@bp.route("/readings/add", methods=["POST"])
@login_required
def reading_add():
    try:
        cid = int(request.form["consumer_id"])
        date = pd.to_datetime(request.form["reading_date"])
        units = float(request.form["units_consumed"])
        meter = request.form.get("meter_reading")
        if units < 0 or repo.get_consumer(cid) is None:
            raise ValueError
        repo.insert_readings([(cid, date.strftime("%Y-%m-%d %H:%M:%S"), units, float(meter) if meter else None)])
        flash("Reading saved.", "success")
    except (ValueError, KeyError):
        flash("Invalid reading: check the consumer, date and non-negative units.", "danger")
    return redirect(url_for("main.upload"))


# ---------------- analytics ----------------
@bp.route("/analytics")
@login_required
def analytics_page():
    df = _filtered()
    return render_template("analytics.html", consumers=repo.list_consumers(), cid=_cid(),
                           start=request.args.get("start", ""), end=request.args.get("end", ""),
                           summary=analytics.descriptive(df), peaks=analytics.peak_analysis(df),
                           insights=analytics.diagnostic(df),
                           comparison=analytics.comparison(analytics.filter_dates(
                               repo.readings_df(None), request.args.get("start"), request.args.get("end"))))


@bp.route("/api/consumption")
@login_required
def api_consumption():
    return jsonify(analytics.series_payload(_filtered(), request.args.get("granularity", "monthly")))


@bp.route("/api/peaks")
@login_required
def api_peaks():
    return jsonify(analytics.peak_analysis(_filtered()))


@bp.route("/api/comparison")
@login_required
def api_comparison():
    df = analytics.filter_dates(repo.readings_df(None), request.args.get("start"), request.args.get("end"))
    return jsonify(analytics.comparison(df))


# ---------------- prediction ----------------
@bp.route("/predict", methods=["GET", "POST"])
@login_required
def predict():
    if request.method == "POST":
        try:
            cid, horizon = int(request.form["consumer_id"]), int(request.form.get("horizon", 30))
            if repo.get_consumer(cid) is None or not 1 <= horizon <= 90:
                raise ValueError("Pick a consumer and a horizon between 1 and 90 days.")
            series = analytics.daily_series(repo.readings_df(cid))
            result = forecast.train_and_forecast(series, horizon, current_app.config["MODEL_FOLDER"], cid)
        except (ValueError, KeyError) as exc:
            flash(str(exc), "danger")
            return redirect(url_for("main.predict"))
        run_id, b = uuid.uuid4().hex[:12], result["best"]
        repo.save_predictions([{
            "consumer_id": cid, "prediction_date": r["date"], "predicted_units": r["predicted"],
            "model_name": b["model"], "run_id": run_id, "lower_bound": r["lower"], "upper_bound": r["upper"],
            "mae": b["mae"], "rmse": b["rmse"], "r2": b["r2"], "created_by": g.user["user_id"]}
            for r in result["forecast"]])
        # model comparison is shown once, right after training (flashed via query-free session-less redirect)
        return render_template("prediction_run.html", run=repo.get_run(run_id), run_id=run_id,
                               comparison=result["comparison"], history=_history_for_chart(cid))
    return render_template("predict.html", consumers=repo.list_consumers())


def _history_for_chart(cid, days=60):
    s = analytics.daily_raw(repo.readings_df(cid)).tail(days)
    return {"labels": [i.strftime("%Y-%m-%d") for i in s.index], "values": [round(float(v), 2) for v in s]}


@bp.route("/history")
@login_required
def history():
    return render_template("history.html", runs=repo.list_runs(_cid()), consumers=repo.list_consumers(), cid=_cid())


@bp.route("/history/<run_id>")
@login_required
def history_run(run_id):
    run = repo.get_run(run_id)
    if not run:
        flash("Prediction run not found.", "danger")
        return redirect(url_for("main.history"))
    return render_template("prediction_run.html", run=run, run_id=run_id, comparison=None,
                           history=_history_for_chart(run[0]["consumer_id"]))


# ---------------- reports ----------------
def _report_frame():
    df = _filtered()
    return analytics.monthly_report(df), df


@bp.route("/reports")
@login_required
def reports():
    pivot, df = _report_frame()
    return render_template("reports.html", consumers=repo.list_consumers(), cid=_cid(),
                           start=request.args.get("start", ""), end=request.args.get("end", ""),
                           pivot=pivot, summary=analytics.descriptive(df), alerts=analytics.alerts(df),
                           comparison=analytics.comparison(df))


@bp.route("/reports/download")
@login_required
def reports_download():
    pivot, _ = _report_frame()
    buf = io.StringIO()
    pivot.to_csv(buf)
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=energy_report.csv"})
