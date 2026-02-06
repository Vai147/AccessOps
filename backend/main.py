"""
AccessOps FastAPI backend.

Endpoints:
  GET  /api/health   — liveness probe
  GET  /api/metrics  — recent time-series metrics
  POST /api/detect   — run anomaly detection pipeline
  GET  /api/alerts   — active alerts with remediation suggestions
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ml.anomaly_detector import AnomalyDetector
from ml.preprocessing import MetricsPreprocessor
from services.metrics_service import MetricsService
from services.remediation_engine import RemediationEngine

# ---------------------------------------------------------------------------
# Application setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AccessOps API",
    description="Accessible AI-Powered Incident Intelligence Platform — backend API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Singletons
# ---------------------------------------------------------------------------

metrics_service = MetricsService()
preprocessor = MetricsPreprocessor()
anomaly_detector = AnomalyDetector(contamination=0.08)
remediation_engine = RemediationEngine()

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class DetectRequest(BaseModel):
    window_minutes: int = 60


class MetricPoint(BaseModel):
    timestamp: str
    cpu_usage: float
    memory_usage: float
    latency_ms: float
    error_rate: float


class AnomalyResult(BaseModel):
    anomaly_scores: list[float]
    anomaly_labels: list[int]
    anomaly_indices: list[int]
    forecast_bounds: dict[str, Any]
    per_column_flags: dict[str, Any]
    metrics: list[dict[str, Any]]
    summary: dict[str, Any]


class Alert(BaseModel):
    id: str
    timestamp: str
    metric_name: str
    value: float
    anomaly_score: float
    severity: str
    explanation: str
    remediation: dict[str, Any]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fit_and_detect(window_minutes: int) -> tuple[Any, Any, Any]:
    """Run the full ML pipeline and return (df_raw, results, df_features)."""
    # 1. Fetch metrics (larger history for fitting)
    fit_window = max(window_minutes * 2, 120)
    df_fit_raw = metrics_service.get_metrics(window_minutes=fit_window)

    # 2. Preprocess for fitting
    df_fit_clean = preprocessor.handle_missing(df_fit_raw)
    df_fit_features = preprocessor.extract_features(df_fit_clean)
    df_fit_norm = preprocessor.normalize(df_fit_features, fit=True)

    # 3. Fit anomaly detector
    base_cols = ["cpu_usage", "memory_usage", "latency_ms", "error_rate"]
    anomaly_detector.fit(df_fit_norm[base_cols])

    # 4. Fetch detection window
    df_detect_raw = metrics_service.get_metrics(window_minutes=window_minutes)
    df_detect_clean = preprocessor.handle_missing(df_detect_raw)
    df_detect_features = preprocessor.extract_features(df_detect_clean)
    df_detect_norm = preprocessor.normalize(df_detect_features, fit=False)

    # 5. Detect anomalies
    results = anomaly_detector.detect(df_detect_norm[base_cols])

    return df_detect_raw, results, df_detect_features


def _build_alerts(
    df_raw: Any,
    results: dict[str, Any],
) -> list[dict[str, Any]]:
    """Convert ML results into structured alert objects."""
    alerts: list[dict[str, Any]] = []
    metric_cols = ["cpu_usage", "memory_usage", "latency_ms", "error_rate"]

    for idx in results["anomaly_indices"]:
        if idx >= len(df_raw):
            continue

        row = df_raw.iloc[idx]
        score = results["anomaly_scores"][idx]
        ts = df_raw.index[idx]

        # Find the metric with the highest individual z-deviation
        dominant_metric = metric_cols[0]
        max_dev = 0.0
        for col in metric_cols:
            col_mean = df_raw[col].mean()
            col_std = df_raw[col].std() or 1.0
            dev = abs((row[col] - col_mean) / col_std)
            if dev > max_dev:
                max_dev = dev
                dominant_metric = col

        explanation = anomaly_detector.explain(
            {
                "metric_name": dominant_metric,
                "value": float(row[dominant_metric]),
                "score": score,
                "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S UTC"),
            }
        )

        remediation = remediation_engine.suggest(
            metric_name=dominant_metric,
            anomaly_score=score,
            context={
                "current_value": float(row[dominant_metric]),
                "timestamp": str(ts),
                "row_index": idx,
            },
        )

        alerts.append(
            {
                "id": str(uuid.uuid4()),
                "timestamp": ts.isoformat(),
                "metric_name": dominant_metric,
                "value": round(float(row[dominant_metric]), 4),
                "anomaly_score": score,
                "severity": remediation["severity"],
                "explanation": explanation,
                "remediation": remediation,
            }
        )

    # Sort most critical first
    alerts.sort(key=lambda a: a["anomaly_score"], reverse=True)
    return alerts


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health_check() -> dict[str, Any]:
    """Liveness probe."""
    return {
        "status": "healthy",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "version": "1.0.0",
        "services": {
            "metrics_service": "ok",
            "anomaly_detector": "ok",
            "remediation_engine": "ok",
        },
    }


@app.get("/api/metrics")
async def get_metrics(window_minutes: int = 30) -> dict[str, Any]:
    """
    Return recent time-series metrics.

    Query parameters
    ----------------
    window_minutes : int  (default 30) — how many minutes of history to return
    """
    if window_minutes < 1 or window_minutes > 1440:
        raise HTTPException(status_code=400, detail="window_minutes must be between 1 and 1440")

    df = metrics_service.get_metrics(window_minutes=window_minutes)
    metadata = metrics_service.get_metric_metadata()

    records = []
    for ts, row in df.iterrows():
        records.append(
            {
                "timestamp": ts.isoformat(),
                "cpu_usage": round(float(row["cpu_usage"]), 3),
                "memory_usage": round(float(row["memory_usage"]), 3),
                "latency_ms": round(float(row["latency_ms"]), 3),
                "error_rate": round(float(row["error_rate"]), 6),
            }
        )

    return {
        "window_minutes": window_minutes,
        "data_points": len(records),
        "metrics": records,
        "metadata": metadata,
        "fetched_at": datetime.now(tz=timezone.utc).isoformat(),
    }


@app.post("/api/detect")
async def detect_anomalies(request: DetectRequest) -> dict[str, Any]:
    """
    Run the full ML anomaly detection pipeline.

    Body
    ----
    window_minutes : int  — detection window size (default 60)
    """
    if request.window_minutes < 5 or request.window_minutes > 1440:
        raise HTTPException(
            status_code=400, detail="window_minutes must be between 5 and 1440"
        )

    try:
        df_raw, results, _ = _fit_and_detect(request.window_minutes)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Detection pipeline failed: {exc}") from exc

    # Serialise raw metrics alongside scores
    metrics_out = []
    for i, (ts, row) in enumerate(df_raw.iterrows()):
        metrics_out.append(
            {
                "timestamp": ts.isoformat(),
                "cpu_usage": round(float(row["cpu_usage"]), 3),
                "memory_usage": round(float(row["memory_usage"]), 3),
                "latency_ms": round(float(row["latency_ms"]), 3),
                "error_rate": round(float(row["error_rate"]), 6),
                "anomaly_score": results["anomaly_scores"][i],
                "is_anomaly": results["anomaly_labels"][i] == -1,
            }
        )

    n_anomalies = len(results["anomaly_indices"])
    avg_score = (
        sum(results["anomaly_scores"][i] for i in results["anomaly_indices"]) / n_anomalies
        if n_anomalies
        else 0.0
    )

    return {
        "window_minutes": request.window_minutes,
        "total_points": len(df_raw),
        "anomaly_count": n_anomalies,
        "anomaly_rate": round(n_anomalies / max(len(df_raw), 1), 4),
        "average_anomaly_score": round(avg_score, 4),
        "anomaly_indices": results["anomaly_indices"],
        "forecast_bounds": results["forecast_bounds"],
        "per_column_flags": {
            col: [bool(f) for f in flags]
            for col, flags in results["per_column_flags"].items()
        },
        "metrics": metrics_out,
        "detected_at": datetime.now(tz=timezone.utc).isoformat(),
    }


@app.get("/api/alerts")
async def get_alerts(window_minutes: int = 60) -> dict[str, Any]:
    """
    Return active anomaly alerts with remediation suggestions.

    Query parameters
    ----------------
    window_minutes : int  (default 60) — how many minutes back to look
    """
    if window_minutes < 5 or window_minutes > 1440:
        raise HTTPException(
            status_code=400, detail="window_minutes must be between 5 and 1440"
        )

    try:
        df_raw, results, _ = _fit_and_detect(window_minutes)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Alert generation failed: {exc}") from exc

    alerts = _build_alerts(df_raw, results)

    severity_counts: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for alert in alerts:
        sev = alert.get("severity", "low")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    return {
        "alert_count": len(alerts),
        "severity_summary": severity_counts,
        "alerts": alerts,
        "window_minutes": window_minutes,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
