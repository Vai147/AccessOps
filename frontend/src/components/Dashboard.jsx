import React, { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
} from 'recharts';

const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';
const REFRESH_INTERVAL_MS = 30_000;

const METRIC_CONFIG = {
  cpu_usage: {
    label: 'CPU Usage',
    unit: '%',
    color: '#4f8ef7',
    anomalyColor: '#ef4444',
    description: 'Percentage of CPU capacity consumed',
    warningThreshold: 70,
    criticalThreshold: 90,
  },
  memory_usage: {
    label: 'Memory Usage',
    unit: '%',
    color: '#10b981',
    anomalyColor: '#f59e0b',
    description: 'Percentage of available RAM in use',
    warningThreshold: 75,
    criticalThreshold: 92,
  },
  latency_ms: {
    label: 'Request Latency',
    unit: 'ms',
    color: '#8b5cf6',
    anomalyColor: '#ef4444',
    description: 'P50 request round-trip latency',
    warningThreshold: 300,
    criticalThreshold: 1000,
  },
  error_rate: {
    label: 'Error Rate',
    unit: '',
    color: '#f59e0b',
    anomalyColor: '#dc2626',
    description: 'Fraction of requests returning errors',
    warningThreshold: 0.05,
    criticalThreshold: 0.15,
  },
};

// -------------------------------------------------------------------------
// Accessible custom tooltip
// -------------------------------------------------------------------------
function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div
      className="chart-tooltip"
      role="tooltip"
      aria-label={`Data point at ${label}`}
    >
      <p className="chart-tooltip__time">{label}</p>
      {payload.map((entry) => (
        <p key={entry.dataKey} className="chart-tooltip__value">
          <span
            className="chart-tooltip__dot"
            style={{ backgroundColor: entry.color }}
            aria-hidden="true"
          />
          {entry.name}:{' '}
          <strong>
            {typeof entry.value === 'number' ? entry.value.toFixed(3) : entry.value}
          </strong>
        </p>
      ))}
    </div>
  );
}

// -------------------------------------------------------------------------
// Visually hidden data table (for screen readers)
// -------------------------------------------------------------------------
function MetricTable({ metricKey, data }) {
  const cfg = METRIC_CONFIG[metricKey];
  return (
    <div className="sr-only">
      <table aria-label={`${cfg.label} data table`}>
        <caption>{cfg.label} time series data</caption>
        <thead>
          <tr>
            <th scope="col">Time</th>
            <th scope="col">
              {cfg.label} ({cfg.unit || 'value'})
            </th>
            <th scope="col">Anomaly</th>
          </tr>
        </thead>
        <tbody>
          {data.map((row) => (
            <tr key={row.timestamp}>
              <td>{row.time}</td>
              <td>
                {typeof row[metricKey] === 'number'
                  ? row[metricKey].toFixed(3)
                  : row[metricKey]}
              </td>
              <td>{row.is_anomaly ? 'Yes' : 'No'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// -------------------------------------------------------------------------
// Single metric card with chart
// -------------------------------------------------------------------------
function MetricCard({ metricKey, data, latestValue, isAnomaly, headingId }) {
  const cfg = METRIC_CONFIG[metricKey];
  const [showTable, setShowTable] = useState(false);
  const tableBtnRef = useRef(null);

  const formattedValue =
    typeof latestValue === 'number'
      ? metricKey === 'error_rate'
        ? `${(latestValue * 100).toFixed(2)}%`
        : `${latestValue.toFixed(1)}${cfg.unit}`
      : '—';

  const statusLabel = isAnomaly
    ? 'anomaly detected'
    : latestValue >= cfg.criticalThreshold
    ? 'critical'
    : latestValue >= cfg.warningThreshold
    ? 'warning'
    : 'normal';

  return (
    <article
      role="region"
      aria-labelledby={headingId}
      className={`metric-card${isAnomaly ? ' metric-card--anomaly' : ''}`}
    >
      <div className="metric-card__header">
        <h2 id={headingId} className="metric-card__title">
          {cfg.label}
        </h2>
        <div
          className={`metric-card__status metric-card__status--${statusLabel.replace(' ', '-')}`}
          aria-label={`Status: ${statusLabel}`}
          role="img"
        >
          {statusLabel}
        </div>
      </div>

      <p className="metric-card__description">{cfg.description}</p>

      <div className="metric-card__value" aria-label={`Current value: ${formattedValue}`}>
        {formattedValue}
      </div>

      {/* Recharts line chart with aria-label on the SVG wrapper */}
      <div
        className="metric-card__chart"
        aria-label={`${cfg.label} time series chart. ${data.length} data points. Current value: ${formattedValue}`}
        role="img"
      >
        <ResponsiveContainer width="100%" height={160}>
          <LineChart
            data={data}
            margin={{ top: 4, right: 8, left: -20, bottom: 0 }}
            aria-hidden="true"
          >
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-grid)" />
            <XAxis
              dataKey="time"
              tick={{ fontSize: 10, fill: 'var(--color-text-muted)' }}
              interval="preserveStartEnd"
              aria-hidden="true"
            />
            <YAxis
              tick={{ fontSize: 10, fill: 'var(--color-text-muted)' }}
              aria-hidden="true"
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <ReferenceLine
              y={cfg.criticalThreshold}
              stroke="#ef4444"
              strokeDasharray="4 2"
              label={{ value: 'Critical', fill: '#ef4444', fontSize: 10 }}
            />
            <Line
              type="monotone"
              dataKey={metricKey}
              name={cfg.label}
              stroke={isAnomaly ? cfg.anomalyColor : cfg.color}
              strokeWidth={2}
              dot={(props) => {
                const { cx, cy, payload } = props;
                if (!payload.is_anomaly) return null;
                return (
                  <circle
                    key={`dot-${payload.timestamp}`}
                    cx={cx}
                    cy={cy}
                    r={5}
                    fill="#ef4444"
                    stroke="#fff"
                    strokeWidth={1.5}
                    aria-hidden="true"
                  />
                );
              }}
              activeDot={{ r: 5 }}
              isAnimationActive={
                !window.matchMedia('(prefers-reduced-motion: reduce)').matches
              }
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Screen-reader table toggle */}
      <button
        ref={tableBtnRef}
        type="button"
        className="btn-text"
        onClick={() => setShowTable((v) => !v)}
        aria-expanded={showTable}
        aria-controls={`table-${metricKey}`}
      >
        {showTable ? 'Hide' : 'Show'} data table
      </button>

      <div id={`table-${metricKey}`} hidden={!showTable} className="metric-table-wrapper">
        <MetricTable metricKey={metricKey} data={data} />
      </div>

      {/* Always-present visually-hidden table for screen readers */}
      <MetricTable metricKey={metricKey} data={data} />
    </article>
  );
}

// -------------------------------------------------------------------------
// Summary statistics bar
// -------------------------------------------------------------------------
function SummaryBar({ detectResult }) {
  if (!detectResult) return null;
  const { total_points, anomaly_count, anomaly_rate, average_anomaly_score } = detectResult;

  return (
    <section
      aria-label="Detection summary statistics"
      className="summary-bar"
    >
      <dl className="summary-bar__stats">
        <div className="summary-bar__stat">
          <dt>Data Points</dt>
          <dd>{total_points}</dd>
        </div>
        <div className="summary-bar__stat">
          <dt>Anomalies Found</dt>
          <dd
            className={anomaly_count > 0 ? 'stat-value--alert' : 'stat-value--ok'}
            aria-label={`${anomaly_count} anomalies found`}
          >
            {anomaly_count}
          </dd>
        </div>
        <div className="summary-bar__stat">
          <dt>Anomaly Rate</dt>
          <dd>{(anomaly_rate * 100).toFixed(1)}%</dd>
        </div>
        <div className="summary-bar__stat">
          <dt>Avg. Score</dt>
          <dd>{average_anomaly_score?.toFixed(3)}</dd>
        </div>
      </dl>
    </section>
  );
}

// -------------------------------------------------------------------------
// Dashboard
// -------------------------------------------------------------------------
function Dashboard({ onAlertsUpdate, announce }) {
  const [metricsData, setMetricsData] = useState([]);
  const [detectResult, setDetectResult] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);
  const errorRef = useRef(null);

  const formatTime = (isoString) => {
    const d = new Date(isoString);
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  };

  const fetchData = useCallback(async () => {
    try {
      setError(null);

      const [metricsRes, detectRes, alertsRes] = await Promise.all([
        axios.get(`${API_BASE}/api/metrics?window_minutes=60`),
        axios.post(`${API_BASE}/api/detect`, { window_minutes: 60 }),
        axios.get(`${API_BASE}/api/alerts?window_minutes=60`),
      ]);

      // Merge anomaly flags into metric data
      const detectMetrics = detectRes.data.metrics || [];
      const enriched = detectMetrics.map((m) => ({
        ...m,
        time: formatTime(m.timestamp),
      }));

      setMetricsData(enriched);
      setDetectResult(detectRes.data);
      setLastUpdated(new Date());

      if (onAlertsUpdate) {
        onAlertsUpdate(alertsRes.data.alerts || []);
      }

      const count = detectRes.data.anomaly_count;
      announce(
        count > 0
          ? `Dashboard updated. ${count} anomal${count === 1 ? 'y' : 'ies'} detected.`
          : 'Dashboard updated. All metrics normal.'
      );
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || 'Unknown error';
      setError(msg);
      announce(`Dashboard error: ${msg}`);
      setTimeout(() => errorRef.current?.focus(), 100);
    } finally {
      setLoading(false);
    }
  }, [onAlertsUpdate, announce]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, REFRESH_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [fetchData]);

  const anomalyIndices = new Set(detectResult?.anomaly_indices ?? []);

  const getLatestValue = (key) => {
    if (!metricsData.length) return null;
    return metricsData[metricsData.length - 1]?.[key] ?? null;
  };

  const hasAnomalyForMetric = (key) => {
    return metricsData.some((row, i) => anomalyIndices.has(i) && row[key] != null);
  };

  if (loading) {
    return (
      <div className="loading-state" role="status" aria-live="polite">
        <div className="spinner" aria-hidden="true" />
        <p>Loading metric data and running anomaly detection&hellip;</p>
      </div>
    );
  }

  if (error) {
    return (
      <div
        className="error-state"
        role="alert"
        aria-live="assertive"
        tabIndex={-1}
        ref={errorRef}
      >
        <h2>Unable to load metrics</h2>
        <p>{error}</p>
        <button
          type="button"
          className="btn-primary"
          onClick={fetchData}
          aria-label="Retry loading dashboard data"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="dashboard">
      {/* Dashboard heading + controls */}
      <div className="dashboard__header">
        <h1 className="dashboard__title">Real-Time Metrics</h1>
        <div className="dashboard__controls">
          {lastUpdated && (
            <p className="dashboard__updated" aria-live="off">
              Last updated:{' '}
              <time dateTime={lastUpdated.toISOString()}>
                {lastUpdated.toLocaleTimeString()}
              </time>
            </p>
          )}
          <button
            type="button"
            className="btn-primary"
            onClick={fetchData}
            aria-label="Refresh dashboard data now"
          >
            Refresh
          </button>
        </div>
      </div>

      {/* Summary statistics */}
      <SummaryBar detectResult={detectResult} />

      {/* Metric cards grid */}
      <div
        className="metric-grid"
        role="list"
        aria-label="Metric charts"
      >
        {Object.keys(METRIC_CONFIG).map((key, i) => (
          <div role="listitem" key={key}>
            <MetricCard
              metricKey={key}
              data={metricsData}
              latestValue={getLatestValue(key)}
              isAnomaly={hasAnomalyForMetric(key)}
              headingId={`metric-heading-${key}`}
            />
          </div>
        ))}
      </div>
    </div>
  );
}

export default Dashboard;
