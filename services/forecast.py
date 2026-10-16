"""Demand forecasting: trains candidate regressors, compares metrics, persists the best model."""
import os
import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

MIN_DAYS = 45


def _features(date, hist):
    """Feature row for `date` given history up to the previous day.
    Cyclical encoding turns weekday/month into continuous variables; lags capture momentum."""
    dow, mon = date.dayofweek, date.month
    return [np.sin(2 * np.pi * dow / 7), np.cos(2 * np.pi * dow / 7),
            np.sin(2 * np.pi * mon / 12), np.cos(2 * np.pi * mon / 12),
            float(dow >= 5), hist[-1], hist[-7], float(np.mean(hist[-7:]))]


def _dataset(series):
    vals = series.values.astype(float)
    X, y, d = [], [], []
    for i in range(7, len(vals)):
        X.append(_features(series.index[i], vals[:i]))
        y.append(vals[i])
        d.append(series.index[i])
    return np.array(X), np.array(y)


def _candidates():
    return {
        "Linear Regression": Pipeline([("scale", StandardScaler()), ("m", LinearRegression())]),
        "Ridge Regression": Pipeline([("scale", StandardScaler()), ("m", Ridge(alpha=1.0))]),
        "Random Forest": RandomForestRegressor(n_estimators=200, min_samples_leaf=2, random_state=42, n_jobs=-1),
        "Gradient Boosting": GradientBoostingRegressor(random_state=42),
    }


def train_and_forecast(series, horizon, model_dir, consumer_id):
    if len(series) < MIN_DAYS:
        raise ValueError(f"At least {MIN_DAYS} days of data are required (found {len(series)}).")
    X, y = _dataset(series)
    split = int(len(X) * 0.8)                     # chronological split: never test on the past
    Xtr, Xte, ytr, yte = X[:split], X[split:], y[:split], y[split:]

    comparison = []
    for name, model in _candidates().items():
        model.fit(Xtr, ytr)
        pred = model.predict(Xte)
        mse = mean_squared_error(yte, pred)
        comparison.append({"model": name, "mae": round(mean_absolute_error(yte, pred), 3),
                           "mse": round(mse, 3), "rmse": round(float(np.sqrt(mse)), 3),
                           "r2": round(r2_score(yte, pred), 4)})
    best = min(comparison, key=lambda r: r["rmse"])
    for r in comparison:
        r["best"] = r["model"] == best["model"]

    final = _candidates()[best["model"]].fit(X, y)    # refit best model on all data
    os.makedirs(model_dir, exist_ok=True)
    joblib.dump({"model": final, "name": best["model"], "metrics": best, "trained_on": str(series.index.max().date())},
                os.path.join(model_dir, f"consumer_{consumer_id}_best.joblib"))

    hist = list(series.values.astype(float))
    last, band = series.index.max(), 1.96 * best["rmse"]
    out = []
    for k in range(1, horizon + 1):
        day = last + pd.Timedelta(days=k)
        yhat = max(0.0, float(final.predict([_features(day, hist)])[0]))
        hist.append(yhat)                             # recursive multi-step forecast
        out.append({"date": day.strftime("%Y-%m-%d"), "predicted": round(yhat, 2),
                    "lower": round(max(0.0, yhat - band), 2), "upper": round(yhat + band, 2)})
    return {"best": best, "comparison": comparison, "forecast": out}
