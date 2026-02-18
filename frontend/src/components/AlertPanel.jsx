import React, { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';

const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';
const REFRESH_INTERVAL_MS = 30_000;

const SEVERITY_CONFIG = {
  critical: { label: 'Critical', className: 'badge--critical', order: 0 },
  high:     { label: 'High',     className: 'badge--high',     order: 1 },
  medium:   { label: 'Medium',   className: 'badge--medium',   order: 2 },
  low:      { label: 'Low',      className: 'badge--low',      order: 3 },
};

// -------------------------------------------------------------------------
// Remediation steps accordion
// -------------------------------------------------------------------------
function RemediationSteps({ steps, alertId, expanded, onToggle }) {
  const panelId = `remediation-steps-${alertId}`;
  const btnId = `remediation-btn-${alertId}`;

  return (
    <div className="remediation">
      <button
        type="button"
        id={btnId}
        className="remediation__toggle"
        aria-expanded={expanded}
        aria-controls={panelId}
        onClick={onToggle}
      >
        <span>Remediation steps ({steps.length})</span>
        <span aria-hidden="true" className={`chevron${expanded ? ' chevron--open' : ''}`}>
          ▾
        </span>
      </button>

      <div
        id={panelId}
        role="region"
        aria-labelledby={btnId}
        hidden={!expanded}
        className="remediation__panel"
      >
        <ol className="remediation__list">
          {steps.map((step, i) => (
            <li key={i} className="remediation__step">
              {step}
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}

// -------------------------------------------------------------------------
// Single alert item
// -------------------------------------------------------------------------
function AlertItem({ alert, onDismiss, isNew }) {
  const [stepsExpanded, setStepsExpanded] = useState(false);
  const dismissBtnRef = useRef(null);
  const cfg = SEVERITY_CONFIG[alert.severity] ?? SEVERITY_CONFIG.low;
  const metricLabels = {
    cpu_usage:    'CPU Usage',
    memory_usage: 'Memory Usage',
    latency_ms:   'Request Latency',
    error_rate:   'Error Rate',
  };

  const formattedTime = new Date(alert.timestamp).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });

  const formattedValue =
    alert.metric_name === 'error_rate'
      ? `${(alert.value * 100).toFixed(2)}%`
      : alert.metric_name === 'latency_ms'
      ? `${alert.value.toFixed(0)} ms`
      : `${alert.value.toFixed(1)}%`;

  return (
    <li
      className={`alert-item alert-item--${alert.severity}${isNew ? ' alert-item--new' : ''}`}
      aria-label={`${cfg.label} alert: ${metricLabels[alert.metric_name] || alert.metric_name} anomaly at ${formattedTime}`}
    >
      <div className="alert-item__header">
        {/* Severity badge — uses aria-label not just color */}
        <span
          className={`severity-badge ${cfg.className}`}
          aria-label={`Severity: ${cfg.label}`}
          role="img"
        >
          {cfg.label}
        </span>

        <span className="alert-item__metric">
          {metricLabels[alert.metric_name] || alert.metric_name}
        </span>

        <time
          dateTime={alert.timestamp}
          className="alert-item__time"
          aria-label={`Detected at ${formattedTime}`}
        >
          {formattedTime}
        </time>

        <button
          ref={dismissBtnRef}
          type="button"
          className="btn-icon alert-item__dismiss"
          onClick={() => onDismiss(alert.id)}
          aria-label={`Dismiss ${cfg.label} alert for ${metricLabels[alert.metric_name] || alert.metric_name}`}
          title="Dismiss alert"
        >
          <svg
            aria-hidden="true"
            focusable="false"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
          >
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>

      <p className="alert-item__value">
        Value: <strong>{formattedValue}</strong>{' '}
        &mdash; Score:{' '}
        <strong aria-label={`Anomaly score ${(alert.anomaly_score * 100).toFixed(0)} percent`}>
          {(alert.anomaly_score * 100).toFixed(0)}%
        </strong>
      </p>

      <p className="alert-item__explanation">{alert.explanation}</p>

      {alert.remediation?.steps?.length > 0 && (
        <RemediationSteps
          steps={alert.remediation.steps}
          alertId={alert.id}
          expanded={stepsExpanded}
          onToggle={() => setStepsExpanded((v) => !v)}
        />
      )}
    </li>
  );
}

// -------------------------------------------------------------------------
// Alert Panel
// -------------------------------------------------------------------------
function AlertPanel({ alerts: externalAlerts, onAlertsChange, announce }) {
  const [alerts, setAlerts] = useState(externalAlerts || []);
  const [newAlertIds, setNewAlertIds] = useState(new Set());
  const [filter, setFilter] = useState('all');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const logRef = useRef(null);
  const prevIdsRef = useRef(new Set());

  // Sync external alerts in when they change (from Dashboard fetch)
  useEffect(() => {
    if (!externalAlerts) return;

    const incomingIds = new Set(externalAlerts.map((a) => a.id));
    const addedIds = [...incomingIds].filter((id) => !prevIdsRef.current.has(id));

    if (addedIds.length > 0) {
      setNewAlertIds(new Set(addedIds));
      setTimeout(() => setNewAlertIds(new Set()), 3000);
    }

    prevIdsRef.current = incomingIds;
    setAlerts(externalAlerts);
  }, [externalAlerts]);

  const fetchAlerts = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await axios.get(`${API_BASE}/api/alerts?window_minutes=60`);
      const incoming = res.data.alerts || [];

      const incomingIds = new Set(incoming.map((a) => a.id));
      const addedIds = [...incomingIds].filter((id) => !prevIdsRef.current.has(id));

      if (addedIds.length > 0) {
        setNewAlertIds(new Set(addedIds));
        setTimeout(() => setNewAlertIds(new Set()), 3000);
        announce(`${addedIds.length} new alert${addedIds.length > 1 ? 's' : ''} received`);
      }

      prevIdsRef.current = incomingIds;
      setAlerts(incoming);
      if (onAlertsChange) onAlertsChange(incoming);
    } catch (err) {
      const msg = err.response?.data?.detail || err.message;
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [announce, onAlertsChange]);

  // Periodic refresh
  useEffect(() => {
    const id = setInterval(fetchAlerts, REFRESH_INTERVAL_MS);
    return () => clearInterval(id);
  }, [fetchAlerts]);

  const handleDismiss = useCallback(
    (alertId) => {
      setAlerts((prev) => {
        const next = prev.filter((a) => a.id !== alertId);
        if (onAlertsChange) onAlertsChange(next);
        announce('Alert dismissed');
        // Move focus to the log container so keyboard users don't lose their place
        setTimeout(() => logRef.current?.focus(), 50);
        return next;
      });
    },
    [announce, onAlertsChange]
  );

  const handleDismissAll = useCallback(() => {
    setAlerts([]);
    if (onAlertsChange) onAlertsChange([]);
    announce('All alerts dismissed');
    logRef.current?.focus();
  }, [announce, onAlertsChange]);

  const filtered = filter === 'all'
    ? alerts
    : alerts.filter((a) => a.severity === filter);

  const severityCounts = alerts.reduce((acc, a) => {
    acc[a.severity] = (acc[a.severity] || 0) + 1;
    return acc;
  }, {});

  return (
    <div className="alert-panel">
      <div className="alert-panel__header">
        <h1 className="alert-panel__title">
          Active Alerts{' '}
          {alerts.length > 0 && (
            <span
              aria-label={`${alerts.length} total alerts`}
              className="alert-count-badge"
            >
              {alerts.length}
            </span>
          )}
        </h1>

        <div className="alert-panel__actions">
          <button
            type="button"
            className="btn-primary"
            onClick={fetchAlerts}
            disabled={loading}
            aria-label="Refresh alerts"
          >
            {loading ? 'Loading…' : 'Refresh'}
          </button>

          {alerts.length > 0 && (
            <button
              type="button"
              className="btn-secondary"
              onClick={handleDismissAll}
              aria-label={`Dismiss all ${alerts.length} alerts`}
            >
              Dismiss all
            </button>
          )}
        </div>
      </div>

      {/* Severity summary */}
      {alerts.length > 0 && (
        <section aria-label="Alert severity summary" className="severity-summary">
          {Object.entries(SEVERITY_CONFIG).map(([key, cfg]) => {
            const count = severityCounts[key] || 0;
            if (!count) return null;
            return (
              <div
                key={key}
                className={`severity-pill ${cfg.className}`}
                aria-label={`${count} ${cfg.label} severity alert${count !== 1 ? 's' : ''}`}
              >
                {cfg.label}: {count}
              </div>
            );
          })}
        </section>
      )}

      {/* Filter tabs */}
      <div
        role="group"
        aria-label="Filter alerts by severity"
        className="alert-filters"
      >
        {['all', 'critical', 'high', 'medium', 'low'].map((f) => (
          <button
            key={f}
            type="button"
            className={`filter-btn${filter === f ? ' filter-btn--active' : ''}`}
            onClick={() => {
              setFilter(f);
              announce(`Showing ${f === 'all' ? 'all' : f} alerts`);
            }}
            aria-pressed={filter === f}
            aria-label={`Show ${f} alerts${f !== 'all' ? ` (${severityCounts[f] || 0})` : ''}`}
          >
            {f.charAt(0).toUpperCase() + f.slice(1)}
            {f !== 'all' && severityCounts[f] > 0 && (
              <span aria-hidden="true"> ({severityCounts[f]})</span>
            )}
          </button>
        ))}
      </div>

      {error && (
        <div role="alert" className="error-banner">
          Failed to refresh alerts: {error}
        </div>
      )}

      {/* The alert log — role="log" + aria-live for screen readers */}
      <div
        ref={logRef}
        role="log"
        aria-live="polite"
        aria-label="Alert log"
        aria-relevant="additions removals"
        tabIndex={-1}
        className="alert-log"
      >
        {filtered.length === 0 ? (
          <div className="alert-empty" role="status">
            {filter === 'all'
              ? 'No active alerts. All systems normal.'
              : `No ${filter} severity alerts.`}
          </div>
        ) : (
          <ul className="alert-list" aria-label={`${filtered.length} alert${filtered.length !== 1 ? 's' : ''}`}>
            {filtered.map((alert) => (
              <AlertItem
                key={alert.id}
                alert={alert}
                onDismiss={handleDismiss}
                isNew={newAlertIds.has(alert.id)}
              />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

export default AlertPanel;
