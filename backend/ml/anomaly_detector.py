"""
AnomalyDetector: Combines IsolationForest (multivariate) with ARIMA (univariate)
for robust time-series anomaly detection on Prometheus-style metrics.
"""

from __future__ import annotations

import warnings
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tools.sm_exceptions import ConvergenceWarning

warnings.filterwarnings("ignore", category=ConvergenceWarning)
warnings.filterwarnings("ignore", category=UserWarning)


class AnomalyDetector:
    """
    Two-stage anomaly detector:
      Stage 1 — IsolationForest on all metric columns simultaneously (multivariate).
      Stage 2 — ARIMA forecast on each column to produce upper/lower bounds;
                 points outside 2-sigma forecast intervals are flagged.
    """

    def __init__(
        self,
        contamination: float = 0.08,
        n_estimators: int = 200,
        random_state: int = 42,
        arima_order: tuple[int, int, int] = (2, 1, 2),
    ) -> None:
        self.contamination = contamination
        self.n_estimators = n_estimators
        self.random_state = random_state
        self.arima_order = arima_order

        self._iso_forest: IsolationForest | None = None
        self._arima_models: dict[str, Any] = {}
        self._feature_columns: list[str] = []
        self._is_fitted: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fit(self, data: pd.DataFrame) -> "AnomalyDetector":
        """
        Fit both IsolationForest and per-column ARIMA models on historical data.

        Parameters
        ----------
        data : pd.DataFrame
            Must contain only numeric metric columns.  Index should be a
            DatetimeIndex (or integer).

        Returns
        -------
        self
        """
        self._feature_columns = [c for c in data.columns if pd.api.types.is_numeric_dtype(data[c])]
        if not self._feature_columns:
            raise ValueError("data contains no numeric columns to fit on")

        X = data[self._feature_columns].values

        # Stage 1 — IsolationForest
        self._iso_forest = IsolationForest(
            n_estimators=self.n_estimators,
            contamination=self.contamination,
            random_state=self.random_state,
            n_jobs=-1,
        )
        self._iso_forest.fit(X)

        # Stage 2 — ARIMA per column
        self._arima_models = {}
        for col in self._feature_columns:
            series = data[col].dropna()
            if len(series) < 10:
                continue
            try:
                model = ARIMA(series, order=self.arima_order)
                fitted = model.fit()
                self._arima_models[col] = fitted
            except Exception:
                # Fall back gracefully — ARIMA is enhancement, not critical path
                pass

        self._is_fitted = True
        return self

    def detect(self, data: pd.DataFrame) -> dict[str, Any]:
        """
        Detect anomalies in new data.

        Returns
        -------
        dict with keys:
          - ``anomaly_scores``  : list[float]  — higher = more anomalous (0–1 range)
          - ``anomaly_labels``  : list[int]    — 1 = normal, -1 = anomaly
          - ``forecast_bounds`` : dict[str, dict]  — per-column {"upper": [], "lower": [], "forecast": []}
          - ``anomaly_indices`` : list[int]    — row indices flagged as anomalies
          - ``per_column_flags``: dict[str, list[bool]] — ARIMA-based flags per column
        """
        if not self._is_fitted:
            raise RuntimeError("Call fit() before detect()")

        present_cols = [c for c in self._feature_columns if c in data.columns]
        X = data[present_cols].ffill().fillna(0).values

        # IsolationForest scores: sklearn returns negative; flip & normalise to [0,1]
        raw_scores = self._iso_forest.decision_function(X)          # lower = more anomalous
        anomaly_scores = self._normalise_scores(raw_scores)         # higher = more anomalous
        anomaly_labels = self._iso_forest.predict(X).tolist()       # -1 / +1

        anomaly_indices = [i for i, lbl in enumerate(anomaly_labels) if lbl == -1]

        # ARIMA forecast bounds
        forecast_bounds: dict[str, dict] = {}
        per_column_flags: dict[str, list[bool]] = {}

        for col in present_cols:
            if col not in self._arima_models:
                continue
            series = data[col].ffill().fillna(0)
            n = len(series)
            try:
                fitted_model = self._arima_models[col]
                # In-sample forecast for the window we're evaluating
                forecast_result = fitted_model.apply(series).get_forecast(steps=0)
                in_sample = fitted_model.apply(series)
                pred = in_sample.fittedvalues
                resid_std = float(np.std(in_sample.resid))

                upper = (pred + 2 * resid_std).tolist()
                lower = (pred - 2 * resid_std).tolist()
                forecast = pred.tolist()

                bounds_upper = upper[-n:] if len(upper) >= n else upper + [upper[-1]] * (n - len(upper))
                bounds_lower = lower[-n:] if len(lower) >= n else lower + [lower[-1]] * (n - len(lower))
                bounds_forecast = forecast[-n:] if len(forecast) >= n else forecast + [forecast[-1]] * (n - len(forecast))

                flags = [
                    float(series.iloc[i]) > bounds_upper[i] or float(series.iloc[i]) < bounds_lower[i]
                    for i in range(min(n, len(bounds_upper)))
                ]

            except Exception:
                bounds_upper = [float(series.max())] * n
                bounds_lower = [float(series.min())] * n
                bounds_forecast = [float(series.mean())] * n
                flags = [False] * n

            forecast_bounds[col] = {
                "upper": [round(v, 4) for v in bounds_upper],
                "lower": [round(v, 4) for v in bounds_lower],
                "forecast": [round(v, 4) for v in bounds_forecast],
            }
            per_column_flags[col] = flags

        return {
            "anomaly_scores": [round(s, 4) for s in anomaly_scores.tolist()],
            "anomaly_labels": anomaly_labels,
            "forecast_bounds": forecast_bounds,
            "anomaly_indices": anomaly_indices,
            "per_column_flags": per_column_flags,
        }

    def explain(self, anomaly: dict[str, Any]) -> str:
        """
        Generate a human-readable explanation for a single anomaly record.

        Parameters
        ----------
        anomaly : dict with keys: metric_name, value, score, timestamp (optional)

        Returns
        -------
        str — plain-English description suitable for display or voice narration
        """
        metric = anomaly.get("metric_name", "unknown metric")
        value = anomaly.get("value", None)
        score = anomaly.get("score", 0.0)
        timestamp = anomaly.get("timestamp", "")

        severity = self._score_to_severity(score)
        time_str = f" at {timestamp}" if timestamp else ""

        value_str = ""
        if value is not None:
            value_str = f" The observed value was {value:.2f}."

        explanation_map = {
            "cpu_usage": (
                f"{severity} anomaly detected in CPU usage{time_str}.{value_str} "
                "The CPU utilisation pattern deviated significantly from the learned baseline. "
                "This may indicate a runaway process, resource contention, or a traffic spike."
            ),
            "memory_usage": (
                f"{severity} anomaly detected in memory usage{time_str}.{value_str} "
                "Memory consumption is outside the expected range. "
                "Possible causes include a memory leak, large object allocation, or unexpected workload growth."
            ),
            "latency_ms": (
                f"{severity} anomaly detected in request latency{time_str}.{value_str} "
                "Response times are abnormally high or erratic. "
                "This could be caused by database slowness, network issues, or downstream service degradation."
            ),
            "error_rate": (
                f"{severity} anomaly detected in error rate{time_str}.{value_str} "
                "The proportion of failed requests is unusually high. "
                "Investigate recent deployments, dependency health, and error logs immediately."
            ),
        }

        base = explanation_map.get(
            metric,
            (
                f"{severity} anomaly detected in {metric}{time_str}.{value_str} "
                "The metric deviated significantly from its expected behaviour based on historical patterns."
            ),
        )

        confidence = min(100, int(score * 100))
        return f"{base} Anomaly confidence: {confidence}%."

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_scores(raw: np.ndarray) -> np.ndarray:
        """Flip IsolationForest decision scores so higher = more anomalous, then scale to [0,1]."""
        flipped = -raw  # negative scores are more anomalous in sklearn
        min_v, max_v = flipped.min(), flipped.max()
        if max_v == min_v:
            return np.zeros_like(flipped)
        return (flipped - min_v) / (max_v - min_v)

    @staticmethod
    def _score_to_severity(score: float) -> str:
        if score >= 0.85:
            return "CRITICAL"
        if score >= 0.65:
            return "HIGH"
        if score >= 0.40:
            return "MEDIUM"
        return "LOW"
