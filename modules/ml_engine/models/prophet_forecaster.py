"""
modules/ml_engine/models/prophet_forecaster.py
───────────────────────────────────────────────
Prophet-based short-term metric forecasting.
Predicts future values and detects when a metric
is heading toward an anomalous region before it crosses the threshold.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta

import pandas as pd
from prophet import Prophet


class ProphetForecaster:
    """
    Trains one Prophet model per metric type per service.
    Used for 30-minute ahead forecasting and early anomaly prediction.
    """

    def __init__(
        self,
        service_name: str,
        metric_name: str,
        changepoint_prior_scale: float = 0.05,
        seasonality_prior_scale: float = 10.0,
    ) -> None:
        self.service_name = service_name
        self.metric_name = metric_name
        self._model: Prophet | None = None
        self._changepoint_prior = changepoint_prior_scale
        self._seasonality_prior = seasonality_prior_scale
        self._fitted = False

    def fit(self, timestamps: list[datetime], values: list[float]) -> dict[str, float]:
        """
        Train Prophet on a (timestamp, value) time series.
        Requires at least 2 data points.
        """
        if len(timestamps) < 2:
            raise ValueError("Prophet requires at least 2 data points to fit")

        df = pd.DataFrame({"ds": pd.to_datetime(timestamps), "y": values})
        df = df.sort_values("ds").reset_index(drop=True)

        self._model = Prophet(
            changepoint_prior_scale=self._changepoint_prior,
            seasonality_prior_scale=self._seasonality_prior,
            daily_seasonality=True,
            weekly_seasonality=True,
            interval_width=0.90,
        )
        self._model.fit(df)
        self._fitted = True

        # Compute fit quality on training data
        forecast = self._model.predict(df)
        residuals = (df["y"] - forecast["yhat"]).abs()
        return {
            "mae": float(residuals.mean()),
            "max_error": float(residuals.max()),
            "n_samples": float(len(df)),
        }

    def forecast(self, horizon_minutes: int = 30) -> list[dict[str, float | str]]:
        """
        Forecast the next `horizon_minutes` of metric values at 1-minute resolution.
        Returns list of {ds, yhat, yhat_lower, yhat_upper} dicts.
        """
        if not self._fitted or not self._model:
            raise RuntimeError("Model must be fitted before forecasting")

        last_date = datetime.utcnow()
        future = pd.DataFrame(
            {
                "ds": pd.date_range(
                    start=last_date,
                    periods=horizon_minutes,
                    freq="1min",
                )
            }
        )
        forecast = self._model.predict(future)
        results = []
        for _, row in forecast.iterrows():
            results.append(
                {
                    "timestamp": str(row["ds"]),
                    "predicted_value": float(max(0.0, row["yhat"])),
                    "lower_bound": float(max(0.0, row["yhat_lower"])),
                    "upper_bound": float(max(0.0, row["yhat_upper"])),
                }
            )
        return results

    def will_breach_threshold(
        self,
        threshold: float,
        horizon_minutes: int = 30,
    ) -> tuple[bool, int | None]:
        """
        Check if the forecast will breach a given threshold within the horizon.
        Returns (will_breach, minutes_until_breach | None).
        """
        predictions = self.forecast(horizon_minutes)
        for i, pred in enumerate(predictions):
            if pred["predicted_value"] >= threshold:
                return True, i + 1
        return False, None

    def save(self, directory: str) -> str:
        """Serialize model as JSON in the given directory."""
        if not self._fitted or not self._model:
            raise RuntimeError("Cannot save unfitted model")
        os.makedirs(directory, exist_ok=True)
        filename = f"{self.service_name}_{self.metric_name}.json"
        path = os.path.join(directory, filename)
        model_json = self._model.to_json()
        with open(path, "w") as f:
            json.dump(
                {
                    "service_name": self.service_name,
                    "metric_name": self.metric_name,
                    "prophet_json": model_json,
                    "changepoint_prior": self._changepoint_prior,
                    "seasonality_prior": self._seasonality_prior,
                },
                f,
            )
        return path

    @classmethod
    def load(cls, path: str) -> "ProphetForecaster":
        with open(path) as f:
            data = json.load(f)
        instance = cls(
            service_name=data["service_name"],
            metric_name=data["metric_name"],
            changepoint_prior_scale=data["changepoint_prior"],
            seasonality_prior_scale=data["seasonality_prior"],
        )
        instance._model = Prophet()
        instance._model = instance._model.from_json(data["prophet_json"])
        instance._fitted = True
        return instance
