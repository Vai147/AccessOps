"""
MetricsService: Collects real-time system metrics using psutil and maintains
a rolling in-memory history buffer for the anomaly detection pipeline.
"""

from __future__ import annotations

import time
import threading
from collections import deque
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import psutil


# Warm up psutil cpu_percent (first call always returns 0.0)
psutil.cpu_percent(interval=None)


class MetricsService:
    """
    Collects real system metrics every 10 seconds via psutil and stores them
    in a rolling buffer. Produces four core metrics:
      - cpu_usage      (0–100 %)
      - memory_usage   (0–100 %)
      - latency_ms     (disk I/O wait time as a latency proxy, ms)
      - error_rate     (CPU iowait fraction as an error proxy, 0–1)
    """

    SCRAPE_INTERVAL_SECONDS: int = 10
    MAX_HISTORY_MINUTES: int = 180  # keep up to 3 hours of samples

    def __init__(self) -> None:
        max_points = (self.MAX_HISTORY_MINUTES * 60) // self.SCRAPE_INTERVAL_SECONDS
        self._buffer: deque[dict] = deque(maxlen=max_points)
        self._lock = threading.Lock()

        # Seed buffer with recent history estimate then start live collection
        self._seed_buffer()
        self._start_collector()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_metrics(self, window_minutes: int = 30) -> pd.DataFrame:
        """
        Return a DataFrame of the last ``window_minutes`` of real system metrics.
        """
        max_points = max(10, (window_minutes * 60) // self.SCRAPE_INTERVAL_SECONDS)

        with self._lock:
            records = list(self._buffer)[-max_points:]

        if not records:
            # Fallback: take a live snapshot if buffer is empty
            records = [self._snapshot()]

        df = pd.DataFrame(records)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df.set_index("timestamp")
        return df

    def get_metric_metadata(self) -> list[dict]:
        """Return human-readable metadata for each metric."""
        return [
            {
                "name": "cpu_usage",
                "label": "CPU Usage",
                "unit": "%",
                "description": "Percentage of CPU capacity consumed across all cores",
                "normal_range": {"min": 5, "max": 70},
                "critical_threshold": 90,
            },
            {
                "name": "memory_usage",
                "label": "Memory Usage",
                "unit": "%",
                "description": "Percentage of available RAM in use",
                "normal_range": {"min": 20, "max": 80},
                "critical_threshold": 92,
            },
            {
                "name": "latency_ms",
                "label": "Disk I/O Latency",
                "unit": "ms",
                "description": "Disk read/write time delta used as a system latency proxy (ms)",
                "normal_range": {"min": 0, "max": 300},
                "critical_threshold": 1000,
            },
            {
                "name": "error_rate",
                "label": "CPU iowait",
                "unit": "fraction",
                "description": "Fraction of time CPU is waiting on I/O — proxy for system stress",
                "normal_range": {"min": 0, "max": 0.1},
                "critical_threshold": 0.4,
            },
        ]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _snapshot(self) -> dict:
        """Take a single real-time reading from psutil."""
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory().percent

        # Disk I/O delta as latency proxy
        try:
            io1 = psutil.disk_io_counters()
            time.sleep(0.1)
            io2 = psutil.disk_io_counters()
            read_ms = (io2.read_time - io1.read_time)
            write_ms = (io2.write_time - io1.write_time)
            latency = float(np.clip(read_ms + write_ms, 0, 5000))
        except Exception:
            latency = 0.0

        # CPU times iowait as error-rate proxy (macOS may return 0 — use steal/irq fallback)
        try:
            cpu_times = psutil.cpu_times_percent(interval=0.0)
            iowait = getattr(cpu_times, "iowait", 0.0) or getattr(cpu_times, "steal", 0.0)
            error_rate = float(np.clip(iowait / 100.0, 0, 1))
        except Exception:
            error_rate = 0.0

        return {
            "timestamp": datetime.now(tz=timezone.utc),
            "cpu_usage": round(cpu, 2),
            "memory_usage": round(mem, 2),
            "latency_ms": round(latency, 2),
            "error_rate": round(error_rate, 6),
        }

    def _seed_buffer(self) -> None:
        """Take 10 quick snapshots to give the ML model something to fit on at startup."""
        for _ in range(10):
            snap = self._snapshot()
            self._buffer.append(snap)

    def _collector_loop(self) -> None:
        """Background thread: collect a snapshot every SCRAPE_INTERVAL_SECONDS."""
        while True:
            snap = self._snapshot()
            with self._lock:
                self._buffer.append(snap)
            time.sleep(self.SCRAPE_INTERVAL_SECONDS)

    def _start_collector(self) -> None:
        t = threading.Thread(target=self._collector_loop, daemon=True)
        t.start()
