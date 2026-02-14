"""
RemediationEngine: Rule-based engine that maps detected anomalies to
actionable remediation steps, ranked by severity.
"""

from __future__ import annotations

from typing import Any


class RemediationEngine:
    """
    Given a metric name, anomaly score, and optional context, returns a
    structured remediation recommendation.

    The engine encodes operational knowledge for four core metrics and falls
    back gracefully for unknown metrics.
    """

    SEVERITY_THRESHOLDS = {
        "critical": 0.85,
        "high": 0.65,
        "medium": 0.40,
        "low": 0.0,
    }

    # Playbooks: metric_name -> list of (score_threshold, recommendation_dict)
    # Higher threshold entries are checked first.
    _PLAYBOOKS: dict[str, list[tuple[float, dict[str, Any]]]] = {
        "cpu_usage": [
            (
                0.85,
                {
                    "action": "IMMEDIATE_SCALE_OUT",
                    "description": (
                        "CPU usage is critically elevated. The system is at risk of being "
                        "unable to serve requests. Immediately scale out the affected service "
                        "and investigate runaway processes."
                    ),
                    "steps": [
                        "Trigger horizontal autoscaler to add at least 2 additional replicas",
                        "Run `top -b -n1` or equivalent to identify the highest-CPU process",
                        "Check for infinite loops or tight retry storms in recent deployments",
                        "Review APM traces for unexpectedly slow code paths",
                        "Enable CPU throttling on non-critical background jobs",
                        "Set a PagerDuty P1 incident and notify the on-call engineer",
                    ],
                },
            ),
            (
                0.65,
                {
                    "action": "INVESTIGATE_AND_THROTTLE",
                    "description": (
                        "CPU usage is significantly above the normal baseline. "
                        "Investigate workload composition and consider throttling non-critical tasks."
                    ),
                    "steps": [
                        "Identify the top-3 CPU-consuming processes with `ps aux --sort=-%cpu | head -5`",
                        "Check if a scheduled batch job coincides with the spike",
                        "Review recent deployments for CPU-intensive regressions",
                        "Enable request rate-limiting at the load balancer if applicable",
                        "Notify the on-call engineer if the trend continues for 5 minutes",
                    ],
                },
            ),
            (
                0.40,
                {
                    "action": "MONITOR_CLOSELY",
                    "description": (
                        "CPU usage is moderately elevated. No immediate action required, "
                        "but the situation warrants close monitoring."
                    ),
                    "steps": [
                        "Increase scrape frequency to 15-second intervals for the next 10 minutes",
                        "Check if this correlates with scheduled tasks (cron, ETL jobs)",
                        "Verify auto-scaling policies are active and correctly configured",
                    ],
                },
            ),
            (
                0.0,
                {
                    "action": "LOG_AND_CONTINUE",
                    "description": "Minor CPU fluctuation — within tolerable bounds. No action required.",
                    "steps": [
                        "Log the event for trend analysis",
                        "No immediate remediation needed",
                    ],
                },
            ),
        ],
        "memory_usage": [
            (
                0.85,
                {
                    "action": "EMERGENCY_RESTART_OR_EVICT",
                    "description": (
                        "Memory usage is critically high. OOM (Out-Of-Memory) kills are imminent. "
                        "Immediate action is required to prevent service degradation."
                    ),
                    "steps": [
                        "Identify the process consuming the most memory: `ps aux --sort=-%mem | head -5`",
                        "Check for memory leak indicators in application heap dumps",
                        "Restart the highest-memory process if it is safe to do so",
                        "Evict unused data from in-process caches (Redis FLUSH, Guava Cache invalidate)",
                        "Trigger a rolling restart of the affected deployment",
                        "Raise a P1 incident and engage the application team",
                    ],
                },
            ),
            (
                0.65,
                {
                    "action": "FREE_CACHE_AND_ALERT",
                    "description": (
                        "Memory consumption is significantly above baseline. "
                        "A memory leak may be in progress. Free caches and prepare for restart."
                    ),
                    "steps": [
                        "Trigger cache eviction policies to reclaim memory",
                        "Check heap profiler output for objects with unexpectedly high retention",
                        "Review recent code changes for missing `close()` or `dispose()` calls",
                        "Set an alert threshold at 90% memory to trigger auto-restart",
                        "Notify on-call: memory leak signature detected",
                    ],
                },
            ),
            (
                0.40,
                {
                    "action": "REVIEW_MEMORY_PROFILE",
                    "description": "Memory usage is moderately elevated. Schedule a memory profile review.",
                    "steps": [
                        "Capture a heap snapshot and compare with the previous baseline",
                        "Verify that GC is running and not paused",
                        "Monitor for upward trend over the next 15 minutes",
                    ],
                },
            ),
            (
                0.0,
                {
                    "action": "LOG_AND_CONTINUE",
                    "description": "Memory usage is within normal bounds. No immediate action required.",
                    "steps": ["Log the event for trend analysis"],
                },
            ),
        ],
        "latency_ms": [
            (
                0.85,
                {
                    "action": "CIRCUIT_BREAKER_OPEN",
                    "description": (
                        "Request latency is critically high. The service is likely degraded. "
                        "Open circuit breakers to prevent cascading failures."
                    ),
                    "steps": [
                        "Activate circuit breaker on the affected service endpoint",
                        "Return cached or degraded responses to clients during recovery",
                        "Check database query performance: `EXPLAIN ANALYZE` slow queries",
                        "Inspect downstream service health (third-party APIs, message queues)",
                        "Review network latency between service tiers with traceroute",
                        "Enable request hedging or retries with exponential backoff",
                        "Raise a P1 incident",
                    ],
                },
            ),
            (
                0.65,
                {
                    "action": "SCALE_AND_OPTIMISE",
                    "description": (
                        "Latency is significantly elevated. Users are experiencing slow responses. "
                        "Scale the service and investigate hot paths."
                    ),
                    "steps": [
                        "Add replicas to distribute request load",
                        "Profile the slowest endpoints using APM distributed traces",
                        "Identify N+1 query patterns in ORM-generated SQL",
                        "Check cache hit rates — a drop may indicate cache invalidation storms",
                        "Review connection pool exhaustion metrics",
                    ],
                },
            ),
            (
                0.40,
                {
                    "action": "INVESTIGATE_HOTSPOT",
                    "description": "Latency is moderately above normal. Investigate specific slow endpoints.",
                    "steps": [
                        "Pull P95/P99 latency breakdowns from your APM tool",
                        "Identify endpoints with the highest tail latency",
                        "Check if a recent deployment changed query patterns",
                    ],
                },
            ),
            (
                0.0,
                {
                    "action": "LOG_AND_CONTINUE",
                    "description": "Latency is within acceptable bounds.",
                    "steps": ["Log the event for baseline tracking"],
                },
            ),
        ],
        "error_rate": [
            (
                0.85,
                {
                    "action": "ROLLBACK_DEPLOYMENT",
                    "description": (
                        "Error rate is critically high. The service is failing for a large fraction of users. "
                        "Consider an immediate rollback of the most recent deployment."
                    ),
                    "steps": [
                        "Check deployment history: `kubectl rollout history deployment/<name>`",
                        "Initiate rollback if the error spike correlates with a recent deploy",
                        "Review error logs for the dominant exception types",
                        "Validate that dependent services (DB, auth, downstream APIs) are healthy",
                        "Activate the incident response runbook and notify the on-call team",
                        "Communicate status via status page to affected users",
                    ],
                },
            ),
            (
                0.65,
                {
                    "action": "INVESTIGATE_ROOT_CAUSE",
                    "description": (
                        "Error rate is significantly elevated. A portion of users are impacted. "
                        "Investigate and prepare for rollback if the trend continues."
                    ),
                    "steps": [
                        "Aggregate error logs and identify the most frequent error codes",
                        "Cross-reference with recent configuration or schema changes",
                        "Run smoke tests against the affected endpoints",
                        "Verify external dependency health (SLAs, status pages)",
                        "Notify the on-call engineer",
                    ],
                },
            ),
            (
                0.40,
                {
                    "action": "REVIEW_ERROR_LOGS",
                    "description": "Error rate is moderately above baseline. Review logs for new error patterns.",
                    "steps": [
                        "Search structured logs for new exception class names",
                        "Verify that error budget burn rate is still within SLO",
                        "Set a temporary alert at 2× the current rate",
                    ],
                },
            ),
            (
                0.0,
                {
                    "action": "LOG_AND_CONTINUE",
                    "description": "Error rate is within normal SLO bounds.",
                    "steps": ["Log for SLO burn rate tracking"],
                },
            ),
        ],
    }

    _GENERIC_PLAYBOOK: list[tuple[float, dict[str, Any]]] = [
        (
            0.85,
            {
                "action": "IMMEDIATE_INVESTIGATION",
                "description": "Critical anomaly detected. Engage on-call team immediately.",
                "steps": [
                    "Identify the anomalous metric and affected service",
                    "Check infrastructure health dashboard",
                    "Review recent changes (deploys, config updates, scaling events)",
                    "Raise a P1 incident",
                ],
            },
        ),
        (
            0.65,
            {
                "action": "ESCALATE_INVESTIGATION",
                "description": "High-severity anomaly detected. Investigate within 15 minutes.",
                "steps": [
                    "Correlate the anomaly with other metrics for root cause clues",
                    "Check for upstream or downstream service issues",
                    "Notify on-call engineer",
                ],
            },
        ),
        (
            0.40,
            {
                "action": "MONITOR_AND_LOG",
                "description": "Medium-severity anomaly. Monitor for escalation.",
                "steps": [
                    "Increase metric collection frequency temporarily",
                    "Log details for post-incident review",
                ],
            },
        ),
        (
            0.0,
            {
                "action": "LOG_AND_CONTINUE",
                "description": "Low-severity anomaly within tolerable bounds.",
                "steps": ["Log for trend analysis"],
            },
        ),
    ]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def suggest(
        self,
        metric_name: str,
        anomaly_score: float,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Return a remediation recommendation.

        Parameters
        ----------
        metric_name   : str   — e.g. "cpu_usage", "latency_ms"
        anomaly_score : float — normalised [0, 1], higher = more anomalous
        context       : dict  — optional extra info (e.g. current_value, host)

        Returns
        -------
        dict with keys:
          - action      : str   — machine-readable action identifier
          - severity    : str   — "critical" | "high" | "medium" | "low"
          - description : str   — human-readable summary
          - steps       : list[str] — ordered remediation checklist
          - metric_name : str
          - anomaly_score : float
          - context     : dict
        """
        context = context or {}
        severity = self._score_to_severity(anomaly_score)
        playbook = self._PLAYBOOKS.get(metric_name, self._GENERIC_PLAYBOOK)
        recommendation = self._select_recommendation(playbook, anomaly_score)

        # Enrich steps with context if current value is provided
        enriched_steps = list(recommendation["steps"])
        current_value = context.get("current_value")
        if current_value is not None:
            meta = self._get_metric_metadata(metric_name)
            if meta and current_value > meta.get("critical_threshold", float("inf")):
                enriched_steps.insert(
                    0,
                    f"Current value ({current_value:.2f} {meta.get('unit', '')}) "
                    f"exceeds critical threshold ({meta['critical_threshold']} {meta.get('unit', '')})",
                )

        return {
            "action": recommendation["action"],
            "severity": severity,
            "description": recommendation["description"],
            "steps": enriched_steps,
            "metric_name": metric_name,
            "anomaly_score": round(anomaly_score, 4),
            "context": context,
        }

    def bulk_suggest(
        self,
        anomalies: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Process a list of anomaly dicts and return ranked remediation suggestions.

        Each anomaly dict must have: metric_name, anomaly_score, and optionally context.
        Results are sorted by anomaly_score descending (most critical first).
        """
        suggestions = []
        for anomaly in anomalies:
            suggestion = self.suggest(
                metric_name=anomaly.get("metric_name", "unknown"),
                anomaly_score=float(anomaly.get("anomaly_score", 0.0)),
                context=anomaly.get("context", {}),
            )
            suggestions.append(suggestion)

        return sorted(suggestions, key=lambda s: s["anomaly_score"], reverse=True)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _select_recommendation(
        playbook: list[tuple[float, dict[str, Any]]],
        score: float,
    ) -> dict[str, Any]:
        for threshold, recommendation in playbook:
            if score >= threshold:
                return recommendation
        return playbook[-1][1]

    @classmethod
    def _score_to_severity(cls, score: float) -> str:
        for label, threshold in cls.SEVERITY_THRESHOLDS.items():
            if score >= threshold:
                return label
        return "low"

    @staticmethod
    def _get_metric_metadata(metric_name: str) -> dict[str, Any] | None:
        metadata_map = {
            "cpu_usage": {"unit": "%", "critical_threshold": 90},
            "memory_usage": {"unit": "%", "critical_threshold": 92},
            "latency_ms": {"unit": "ms", "critical_threshold": 1000},
            "error_rate": {"unit": "", "critical_threshold": 0.15},
        }
        return metadata_map.get(metric_name)
