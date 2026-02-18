import React, { useState, useEffect, useRef, useCallback } from 'react';

/**
 * VoiceAlert: Uses the Web Speech API (SpeechSynthesis) to narrate new alerts
 * aloud. Respects prefers-reduced-motion and provides an accessible toggle button.
 *
 * Props:
 *   alerts   — array of alert objects from the backend
 *   enabled  — boolean controlled by parent
 *   onToggle — callback(newValue: boolean)
 */
function VoiceAlert({ alerts, enabled, onToggle }) {
  const [speechSupported, setSpeechSupported] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const prevAlertIdsRef = useRef(new Set());
  const queueRef = useRef([]);
  const isSpeakingRef = useRef(false);

  // Detect speech synthesis support once on mount
  useEffect(() => {
    setSpeechSupported('speechSynthesis' in window);
  }, []);

  // Check the user's motion preference
  const prefersReducedMotion = useCallback(
    () =>
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    []
  );

  // Speak a single utterance, then drain the queue
  const speakNext = useCallback(() => {
    if (isSpeakingRef.current || queueRef.current.length === 0) return;

    const text = queueRef.current.shift();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 0.95;
    utterance.pitch = 1.0;
    utterance.volume = 1.0;

    // Prefer a natural-sounding English voice if available
    const voices = window.speechSynthesis.getVoices();
    const preferred = voices.find(
      (v) => v.lang.startsWith('en') && v.localService
    );
    if (preferred) utterance.voice = preferred;

    utterance.onstart = () => {
      isSpeakingRef.current = true;
      setSpeaking(true);
    };

    utterance.onend = () => {
      isSpeakingRef.current = false;
      setSpeaking(false);
      // Drain queue
      if (queueRef.current.length > 0) speakNext();
    };

    utterance.onerror = () => {
      isSpeakingRef.current = false;
      setSpeaking(false);
    };

    window.speechSynthesis.speak(utterance);
  }, []);

  const enqueueSpeech = useCallback(
    (text) => {
      if (!speechSupported || !enabled || prefersReducedMotion()) return;
      queueRef.current.push(text);
      speakNext();
    },
    [speechSupported, enabled, prefersReducedMotion, speakNext]
  );

  // Watch for genuinely new alerts and narrate them
  useEffect(() => {
    if (!enabled || !speechSupported || !alerts?.length) return;

    const currentIds = new Set(alerts.map((a) => a.id));
    const newAlerts = alerts.filter((a) => !prevAlertIdsRef.current.has(a.id));

    if (newAlerts.length === 0) {
      prevAlertIdsRef.current = currentIds;
      return;
    }

    // Summarise if many new alerts arrive at once
    if (newAlerts.length > 3) {
      const critical = newAlerts.filter((a) => a.severity === 'critical').length;
      const high = newAlerts.filter((a) => a.severity === 'high').length;
      let summary = `${newAlerts.length} new alerts detected.`;
      if (critical) summary += ` ${critical} critical.`;
      if (high) summary += ` ${high} high severity.`;
      enqueueSpeech(summary);
    } else {
      // Narrate each alert individually
      newAlerts.forEach((alert) => {
        const metricLabels = {
          cpu_usage:    'CPU usage',
          memory_usage: 'memory usage',
          latency_ms:   'request latency',
          error_rate:   'error rate',
        };
        const metricLabel = metricLabels[alert.metric_name] || alert.metric_name;
        const severity = alert.severity.charAt(0).toUpperCase() + alert.severity.slice(1);
        const score = Math.round(alert.anomaly_score * 100);
        enqueueSpeech(
          `${severity} alert. ${metricLabel} anomaly detected. Confidence: ${score} percent.`
        );
      });
    }

    prevAlertIdsRef.current = currentIds;
  }, [alerts, enabled, speechSupported, enqueueSpeech]);

  // Stop speaking when voice alerts are disabled
  useEffect(() => {
    if (!enabled && speechSupported) {
      window.speechSynthesis.cancel();
      queueRef.current = [];
      isSpeakingRef.current = false;
      setSpeaking(false);
    }
  }, [enabled, speechSupported]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (speechSupported) {
        window.speechSynthesis.cancel();
      }
    };
  }, [speechSupported]);

  const handleToggle = useCallback(() => {
    const next = !enabled;
    onToggle(next);

    // Give the user audible confirmation when enabling
    if (next && speechSupported && !prefersReducedMotion()) {
      const confirmUtterance = new SpeechSynthesisUtterance(
        'Voice alerts enabled. I will narrate new incidents.'
      );
      confirmUtterance.rate = 0.95;
      window.speechSynthesis.speak(confirmUtterance);
    }
  }, [enabled, onToggle, speechSupported, prefersReducedMotion]);

  if (!speechSupported) {
    return (
      <div
        className="voice-alert voice-alert--unsupported"
        title="Web Speech API is not supported in this browser"
        aria-label="Voice alerts unavailable in this browser"
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
          <line x1="1" y1="1" x2="23" y2="23" />
          <path d="M9 9v3a3 3 0 0 0 5.12 2.12M15 9.34V4a3 3 0 0 0-5.94-.6" />
          <path d="M17 16.95A7 7 0 0 1 5 12v-2m14 0v2a7 7 0 0 1-.11 1.23" />
          <line x1="12" y1="19" x2="12" y2="23" />
          <line x1="8" y1="23" x2="16" y2="23" />
        </svg>
        <span className="sr-only">Voice alerts not supported</span>
      </div>
    );
  }

  return (
    <div className="voice-alert">
      <button
        type="button"
        className={`btn-icon voice-alert__btn${enabled ? ' voice-alert__btn--active' : ''}`}
        onClick={handleToggle}
        aria-pressed={enabled}
        aria-label={enabled ? 'Disable voice alerts' : 'Enable voice alerts'}
        title={enabled ? 'Voice alerts on — click to disable' : 'Enable voice alerts'}
      >
        {speaking ? (
          // Animated "speaking" icon
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
            className="speaking-icon"
          >
            <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
            <path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
            <path d="M19.07 4.93a10 10 0 0 1 0 14.14" />
          </svg>
        ) : enabled ? (
          // Voice on icon
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
            <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
            <path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
          </svg>
        ) : (
          // Voice off (muted) icon
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
            <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
            <line x1="23" y1="9" x2="17" y2="15" />
            <line x1="17" y1="9" x2="23" y2="15" />
          </svg>
        )}
      </button>

      {/* Visible status label for sighted users */}
      <span
        className={`voice-alert__label${enabled ? ' voice-alert__label--active' : ''}`}
        aria-hidden="true"
      >
        {speaking ? 'Speaking…' : enabled ? 'Voice on' : 'Voice off'}
      </span>
    </div>
  );
}

export default VoiceAlert;
