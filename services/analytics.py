"""Business logic: descriptive, diagnostic and peak analytics with Pandas. No SQL, no Flask here."""
import calendar
import numpy as np
import pandas as pd

DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def filter_dates(df, start=None, end=None):
    if start:
        df = df[df["reading_date"] >= pd.to_datetime(start)]
    if end:
        df = df[df["reading_date"] < pd.to_datetime(end) + pd.Timedelta(days=1)]
    return df


def has_hourly(df):
    return (not df.empty) and df["reading_date"].dt.hour.nunique() > 1


def daily_raw(df):
    """Units per calendar day (hourly rows are summed)."""
    if df.empty:
        return pd.Series(dtype=float)
    return df.groupby(df["reading_date"].dt.normalize())["units_consumed"].sum().sort_index()


def daily_series(df):
    """Continuous daily series; missing days are linearly interpolated (used for ML)."""
    s = daily_raw(df)
    if s.empty:
        return s
    return s.reindex(pd.date_range(s.index.min(), s.index.max(), freq="D")).interpolate().rename("units")


def monthly_series(df):
    d = daily_raw(df)
    return d.resample("MS").sum() if not d.empty else d


# ---------- descriptive: what happened ----------
def descriptive(df):
    d = daily_raw(df)
    if d.empty:
        return None
    m = monthly_series(df)
    return {
        "total_units": round(float(d.sum()), 1),
        "avg_daily": round(float(d.mean()), 2),
        "max_day": d.idxmax().strftime("%Y-%m-%d"), "max_day_units": round(float(d.max()), 1),
        "min_day": d.idxmin().strftime("%Y-%m-%d"), "min_day_units": round(float(d.min()), 1),
        "months": int(len(m)),
        "last_month": m.index[-1].strftime("%b %Y"), "last_month_units": round(float(m.iloc[-1]), 1),
        "first_date": d.index.min().strftime("%Y-%m-%d"), "last_date": d.index.max().strftime("%Y-%m-%d"),
        "consumers": int(df["consumer_id"].nunique()),
    }


def series_payload(df, granularity="monthly"):
    if granularity == "daily":
        s = daily_raw(df)
        return {"labels": [i.strftime("%Y-%m-%d") for i in s.index], "values": [round(float(v), 2) for v in s]}
    s = monthly_series(df)
    return {"labels": [i.strftime("%Y-%m") for i in s.index], "values": [round(float(v), 1) for v in s]}


# ---------- peak usage ----------
def peak_analysis(df):
    d = daily_raw(df)
    if d.empty:
        return None
    std = 0 if np.isnan(d.std()) else d.std()
    thr = d.mean() + 1.5 * std
    peaks = d[d > thr].sort_values(ascending=False).head(10)
    dow = d.groupby(d.index.dayofweek).mean().reindex(range(7)).fillna(0)
    mon = d.groupby(d.index.month).mean()
    out = {
        "threshold": round(float(thr), 2),
        "peak_days": [{"date": i.strftime("%Y-%m-%d"), "units": round(float(v), 1)} for i, v in peaks.items()],
        "dow": {"labels": DOW, "values": [round(float(v), 2) for v in dow]},
        "peak_weekday": DOW[int(dow.idxmax())],
        "peak_month": calendar.month_name[int(mon.idxmax())],
        "hourly": None, "peak_hours": [],
    }
    if has_hourly(df):
        hr = df.groupby(df["reading_date"].dt.hour)["units_consumed"].mean().reindex(range(24)).fillna(0)
        out["hourly"] = {"labels": [f"{h:02d}:00" for h in range(24)], "values": [round(float(v), 3) for v in hr]}
        out["peak_hours"] = [f"{h:02d}:00-{(h + 1) % 24:02d}:00" for h in hr.sort_values(ascending=False).head(3).index]
    return out


# ---------- diagnostic: why it happened ----------
def diagnostic(df):
    d = daily_raw(df)
    if len(d) < 14:
        return []
    ins = []
    wk = d[d.index.dayofweek < 5].mean()
    we = d[d.index.dayofweek >= 5].mean()
    if wk > 0:
        diff = (we - wk) / wk * 100
        ins.append(f"Weekend days average {we:.1f} units vs {wk:.1f} on weekdays "
                   f"({diff:+.1f}%), so usage is {'occupancy/leisure driven' if diff > 5 else 'work-pattern driven' if diff < -5 else 'largely independent of weekday'}.")
    m = monthly_series(df)
    if len(m) >= 3:
        full = m.iloc[:-1] if d.index.max().day < 28 else m   # ignore a partial last month
        if len(full) >= 2:
            chg = (full.iloc[-1] - full.iloc[-2]) / full.iloc[-2] * 100
            ins.append(f"{full.index[-1]:%b %Y} changed {chg:+.1f}% vs {full.index[-2]:%b %Y}.")
        hi, lo = full.idxmax(), full.idxmin()
        ins.append(f"Seasonality: highest month {hi:%b %Y} ({full.max():.0f} units) vs lowest {lo:%b %Y} "
                   f"({full.min():.0f}); a {(full.max() / full.min() - 1) * 100:.0f}% swing suggests weather-related load (cooling/heating).")
    cv = d.std() / d.mean() * 100 if d.mean() else 0
    ins.append(f"Day-to-day variability (coefficient of variation) is {cv:.1f}%.")
    thr = d.mean() + 1.5 * d.std()
    share = d[d > thr].sum() / d.sum() * 100
    ins.append(f"{(d > thr).sum()} peak days (> {thr:.1f} units) contribute {share:.1f}% of total consumption.")
    if has_hourly(df):
        h = df.groupby(df["reading_date"].dt.hour)["units_consumed"].sum()
        eve = h.loc[17:22].sum() / h.sum() * 100
        ins.append(f"Evening hours (17:00-22:59) account for {eve:.1f}% of usage, vs {6 / 24 * 100:.0f}% if usage were flat.")
    return ins


# ---------- consumer comparison ----------
def comparison(df):
    if df.empty:
        return []
    rows = []
    for cid, g in df.groupby("consumer_id"):
        d = daily_raw(g)
        rows.append({"consumer_id": int(cid), "name": g["name"].iloc[0], "category": g["category"].iloc[0],
                     "total": round(float(d.sum()), 1), "avg_daily": round(float(d.mean()), 2),
                     "peak_daily": round(float(d.max()), 1)})
    out = pd.DataFrame(rows)
    out["category_avg"] = out.groupby("category")["avg_daily"].transform("mean").round(2)
    out["vs_category_pct"] = ((out["avg_daily"] / out["category_avg"] - 1) * 100).round(1)
    return out.sort_values("avg_daily", ascending=False).to_dict("records")


# ---------- estimated usage alerts ----------
def alerts(df, spike_pct=20, projection_pct=15):
    """Alerts per consumer, evaluated as of the last date present in that consumer's data."""
    out = []
    for cid, g in df.groupby("consumer_id"):
        d = daily_raw(g)
        if len(d) < 40:
            continue
        name, last = g["name"].iloc[0], d.index.max()
        recent, base = d.iloc[-7:].mean(), d.iloc[-37:-7].mean()
        if base > 0 and (recent / base - 1) * 100 > spike_pct:
            out.append({"level": "warning", "consumer": name, "consumer_id": int(cid),
                        "message": f"Last 7 days average {recent:.1f} units/day, {(recent / base - 1) * 100:.0f}% above the prior 30-day average ({base:.1f})."})
        # projected month-end vs previous month
        mstart = last.replace(day=1)
        cur = d[d.index >= mstart]
        prev_end = mstart - pd.Timedelta(days=1)
        prev = d[(d.index >= prev_end.replace(day=1)) & (d.index <= prev_end)]
        dim = calendar.monthrange(last.year, last.month)[1]
        if len(prev) >= 25 and last.day >= 5 and last.day < dim:
            proj = cur.sum() / last.day * dim
            if (proj / prev.sum() - 1) * 100 > projection_pct:
                out.append({"level": "danger", "consumer": name, "consumer_id": int(cid),
                            "message": f"Estimated {last:%B} usage is {proj:.0f} units, {(proj / prev.sum() - 1) * 100:.0f}% more than {prev_end:%B} ({prev.sum():.0f})."})
        if d.iloc[-1] > d.mean() + 2 * d.std():
            out.append({"level": "info", "consumer": name, "consumer_id": int(cid),
                        "message": f"Latest day ({last:%Y-%m-%d}) was {d.iloc[-1]:.1f} units, unusually high."})
    return out


# ---------- reports ----------
def monthly_report(df):
    """Consumer x month pivot of units, with total column."""
    if df.empty:
        return pd.DataFrame()
    t = df.copy()
    t["month"] = t["reading_date"].dt.to_period("M").astype(str)
    p = t.pivot_table(index="name", columns="month", values="units_consumed", aggfunc="sum", fill_value=0).round(1)
    p["Total"] = p.sum(axis=1).round(1)
    return p
