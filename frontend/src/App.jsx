import React, { useState, useEffect, useCallback, useRef } from 'react';
import Dashboard from './components/Dashboard';
import AlertPanel from './components/AlertPanel';
import VoiceAlert from './components/VoiceAlert';
import './styles/App.css';

const TABS = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'alerts', label: 'Alerts' },
];

function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [highContrast, setHighContrast] = useState(
    () => localStorage.getItem('accessops-high-contrast') === 'true'
  );
  const [announceMessage, setAnnounceMessage] = useState('');
  const [alerts, setAlerts] = useState([]);
  const [voiceEnabled, setVoiceEnabled] = useState(false);
  const tabRefs = useRef([]);

  // Persist high contrast preference
  useEffect(() => {
    localStorage.setItem('accessops-high-contrast', String(highContrast));
    if (highContrast) {
      document.documentElement.classList.add('high-contrast');
    } else {
      document.documentElement.classList.remove('high-contrast');
    }
  }, [highContrast]);

  const announce = useCallback((message) => {
    setAnnounceMessage('');
    // Reset then set so screen readers re-announce even if the same message fires twice
    requestAnimationFrame(() => setAnnounceMessage(message));
  }, []);

  const handleTabChange = useCallback(
    (tabId) => {
      setActiveTab(tabId);
      const tab = TABS.find((t) => t.id === tabId);
      if (tab) announce(`Navigated to ${tab.label}`);
    },
    [announce]
  );

  // Keyboard navigation for tabs (arrow keys + Home/End)
  const handleTabKeyDown = useCallback(
    (e, currentIndex) => {
      let targetIndex = currentIndex;
      if (e.key === 'ArrowRight') {
        targetIndex = (currentIndex + 1) % TABS.length;
      } else if (e.key === 'ArrowLeft') {
        targetIndex = (currentIndex - 1 + TABS.length) % TABS.length;
      } else if (e.key === 'Home') {
        targetIndex = 0;
      } else if (e.key === 'End') {
        targetIndex = TABS.length - 1;
      } else {
        return; // not a navigation key
      }
      e.preventDefault();
      handleTabChange(TABS[targetIndex].id);
      tabRefs.current[targetIndex]?.focus();
    },
    [handleTabChange]
  );

  const handleAlertsUpdate = useCallback(
    (newAlerts) => {
      setAlerts(newAlerts);
      if (newAlerts.length > 0) {
        const critical = newAlerts.filter((a) => a.severity === 'critical').length;
        const high = newAlerts.filter((a) => a.severity === 'high').length;
        let msg = `${newAlerts.length} alert${newAlerts.length !== 1 ? 's' : ''} detected.`;
        if (critical > 0) msg += ` ${critical} critical.`;
        if (high > 0) msg += ` ${high} high severity.`;
        announce(msg);
      }
    },
    [announce]
  );

  return (
    <div className={`app-root${highContrast ? ' high-contrast' : ''}`}>
      {/* Skip navigation link — visually hidden until focused */}
      <a href="#main-content" className="skip-link">
        Skip to main content
      </a>

      {/* ------------------------------------------------------------------ */}
      {/* Header                                                               */}
      {/* ------------------------------------------------------------------ */}
      <header role="banner" className="app-header">
        <div className="header-inner">
          <div className="header-brand">
            {/* SVG icon with accessible hidden label */}
            <svg
              aria-hidden="true"
              focusable="false"
              width="32"
              height="32"
              viewBox="0 0 32 32"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
              className="brand-icon"
            >
              <circle cx="16" cy="16" r="15" stroke="currentColor" strokeWidth="2" />
              <path
                d="M10 22 L16 10 L22 22"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <circle cx="16" cy="10" r="2" fill="currentColor" />
            </svg>
            <span className="brand-name">AccessOps</span>
            <span className="brand-tagline" aria-label="Accessible AI-Powered Incident Intelligence">
              Incident Intelligence
            </span>
          </div>

          <div className="header-controls">
            {/* Voice alerts toggle */}
            <VoiceAlert
              alerts={alerts}
              enabled={voiceEnabled}
              onToggle={setVoiceEnabled}
            />

            {/* High contrast toggle */}
            <button
              type="button"
              className="btn-icon"
              onClick={() => {
                setHighContrast((v) => !v);
                announce(
                  `High contrast mode ${!highContrast ? 'enabled' : 'disabled'}`
                );
              }}
              aria-pressed={highContrast}
              aria-label={
                highContrast
                  ? 'Disable high contrast mode'
                  : 'Enable high contrast mode'
              }
              title="Toggle high contrast mode"
            >
              <svg
                aria-hidden="true"
                focusable="false"
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <circle cx="12" cy="12" r="10" />
                <path d="M12 2v20M2 12h20" />
                <path d="M12 2a10 10 0 0 1 0 20V2z" fill="currentColor" />
              </svg>
            </button>
          </div>
        </div>
      </header>

      {/* ------------------------------------------------------------------ */}
      {/* Navigation                                                           */}
      {/* ------------------------------------------------------------------ */}
      <nav role="navigation" aria-label="Main navigation" className="app-nav">
        <div
          role="tablist"
          aria-label="Application sections"
          className="tab-list"
        >
          {TABS.map((tab, index) => (
            <button
              key={tab.id}
              ref={(el) => (tabRefs.current[index] = el)}
              role="tab"
              id={`tab-${tab.id}`}
              aria-controls={`panel-${tab.id}`}
              aria-selected={activeTab === tab.id}
              tabIndex={activeTab === tab.id ? 0 : -1}
              className={`tab-btn${activeTab === tab.id ? ' tab-btn--active' : ''}`}
              onClick={() => handleTabChange(tab.id)}
              onKeyDown={(e) => handleTabKeyDown(e, index)}
            >
              {tab.label}
              {tab.id === 'alerts' && alerts.length > 0 && (
                <span
                  className="alert-badge"
                  aria-label={`${alerts.length} active alert${alerts.length !== 1 ? 's' : ''}`}
                >
                  {alerts.length}
                </span>
              )}
            </button>
          ))}
        </div>
      </nav>

      {/* ------------------------------------------------------------------ */}
      {/* Live region for screen reader announcements                         */}
      {/* ------------------------------------------------------------------ */}
      <div
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className="sr-only live-region"
      >
        {announceMessage}
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Main content                                                         */}
      {/* ------------------------------------------------------------------ */}
      <main id="main-content" role="main" className="app-main" tabIndex={-1}>
        <div
          role="tabpanel"
          id="panel-dashboard"
          aria-labelledby="tab-dashboard"
          hidden={activeTab !== 'dashboard'}
        >
          {activeTab === 'dashboard' && (
            <Dashboard onAlertsUpdate={handleAlertsUpdate} announce={announce} />
          )}
        </div>

        <div
          role="tabpanel"
          id="panel-alerts"
          aria-labelledby="tab-alerts"
          hidden={activeTab !== 'alerts'}
        >
          {activeTab === 'alerts' && (
            <AlertPanel
              alerts={alerts}
              onAlertsChange={setAlerts}
              announce={announce}
            />
          )}
        </div>
      </main>

      {/* ------------------------------------------------------------------ */}
      {/* Footer                                                               */}
      {/* ------------------------------------------------------------------ */}
      <footer role="contentinfo" className="app-footer">
        <p>
          AccessOps v1.0 &mdash; WCAG 2.1 AA Compliant &mdash; Powered by
          IsolationForest &amp; ARIMA
        </p>
      </footer>
    </div>
  );
}

export default App;
