# AccessOps: Accessible AI-Powered Incident Intelligence Platform

AccessOps is a cloud monitoring platform that combines real machine learning with a fully accessible UI to detect metric anomalies and surface actionable remediation steps.

## What It Does

- Ingests Prometheus-style time-series metrics (CPU, memory, latency, error rate)
- Runs **IsolationForest** (scikit-learn) for multivariate anomaly detection
- Uses **ARIMA** (statsmodels) for univariate time-series forecasting and anomaly bounds
- Surfaces detected anomalies through a **WCAG 2.1 AA compliant** React frontend
- Provides **voice alerts** via the Web Speech API for hands-free incident awareness
- Generates **remediation suggestions** ranked by severity

## Accessibility Features

- Skip-to-content link
- Full keyboard navigation with visible focus indicators
- `aria-live` regions for dynamic alert announcements
- Screen-reader-friendly chart data tables (visually hidden)
- High contrast mode toggle (persisted in localStorage)
- `prefers-reduced-motion` and `prefers-color-scheme` CSS media query support
- All interactive elements have descriptive `aria-label` attributes
- WCAG AA color contrast ratios throughout

## ML/AI Stack

| Component | Technology |
|---|---|
| Multivariate anomaly detection | scikit-learn `IsolationForest` |
| Time-series forecasting | statsmodels `ARIMA` |
| Feature engineering | Rolling stats, rate-of-change |
| Preprocessing | `StandardScaler`, forward-fill, interpolation |
| Remediation engine | Rule-based severity scoring |

## Quick Start

### With Docker Compose

```bash
docker-compose up --build
```

- Backend: http://localhost:8000
- Frontend: http://localhost:3000
- API docs: http://localhost:8000/docs

### Without Docker

**Backend:**
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
npm start
```

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Health check |
| GET | `/api/metrics` | Recent time-series metrics |
| POST | `/api/detect` | Run anomaly detection |
| GET | `/api/alerts` | Active alerts with remediation |

## Project Structure

```
AccessOps/
├── backend/
│   ├── ml/
│   │   ├── anomaly_detector.py   # IsolationForest + ARIMA
│   │   └── preprocessing.py      # Feature engineering
│   ├── services/
│   │   ├── metrics_service.py    # Synthetic Prometheus data
│   │   └── remediation_engine.py # Remediation suggestions
│   ├── main.py                   # FastAPI application
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── public/index.html
│   └── src/
│       ├── App.jsx
│       ├── index.jsx
│       ├── components/
│       │   ├── Dashboard.jsx
│       │   ├── AlertPanel.jsx
│       │   └── VoiceAlert.jsx
│       └── styles/App.css
└── docker-compose.yml
```
