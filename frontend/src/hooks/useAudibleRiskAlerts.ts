"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { IntelligenceContext } from "@/lib/intelligence-context";

const AUDIBLE_ALERTS_STORAGE_KEY = "aegis.intelligence.audible-risk-alerts.v1";
const GLOBAL_SPEECH_COOLDOWN_MS = 45_000;
const CRITICAL_REPEAT_COOLDOWN_MS = 60_000;

export type AudibleRiskLevel = "MEDIUM" | "HIGH" | "CRITICAL";
export type AudibleRiskVisualState = "watching" | "attention" | "high_risk" | "unavailable";
export type AudibleRiskControlState = "muted" | "arming" | "watching" | "attention" | "high_risk" | "unavailable";
export type GeminiAlertPlaybackResult = "spoken" | "unavailable" | "busy";

export type AudibleRiskAlert = {
  /** Opaque record id. The backend revalidates it before generating audio. */
  id: string;
  level: Extract<AudibleRiskLevel, "HIGH" | "CRITICAL">;
  cameraId: string | null;
  evidenceLabel: string;
  /** Used only by the browser-TTS fallback after Gemini is unavailable. */
  spokenText: string;
  panelText: string;
};

export type AudibleRiskAssessment = {
  visualState: AudibleRiskVisualState;
  speechCandidate: AudibleRiskAlert | null;
};

type AlertMemory = { level: AudibleRiskAlert["level"]; spokenAt: number };

function riskLevel(value: string | null | undefined): AudibleRiskLevel | null {
  const normalized = value?.trim().toUpperCase();
  if (normalized === "MEDIUM" || normalized === "HIGH" || normalized === "CRITICAL") return normalized;
  return null;
}

function riskRank(level: AudibleRiskLevel) {
  if (level === "CRITICAL") return 3;
  if (level === "HIGH") return 2;
  return 1;
}

function isFreshVerifiedRecord(record: { freshness: { status: string }; evidence: Array<{ serverValidated?: boolean }> }) {
  return record.freshness.status === "live" && record.evidence.some((reference) => reference.serverValidated === true);
}

function wording(level: Extract<AudibleRiskLevel, "HIGH" | "CRITICAL">, cameraId: string | null) {
  const nearCamera = cameraId ? ` near ${cameraId}` : "";
  if (level === "CRITICAL") {
    return {
      spokenText: `Critical risk event detected${nearCamera}. Evidence has been saved. Immediate operator review is required.`,
      panelText: `${cameraId ? `${cameraId} - ` : ""}Operator review needed immediately.`,
    };
  }
  return {
    spokenText: `High-risk event detected${nearCamera}. Evidence has been saved. Operator review is required.`,
    panelText: `${cameraId ? `${cameraId} - ` : ""}Operator review recommended.`,
  };
}

/**
 * Builds candidates only from fresh, server-validated context records. The
 * actual Gemini speech request repeats this validation on the backend, so a
 * client poll can select a candidate but can never authorize its wording.
 */
export function assessAudibleRisk(context: IntelligenceContext | null): AudibleRiskAssessment {
  if (!context) {
    return { visualState: "unavailable", speechCandidate: null };
  }

  const candidates = new Map<string, { id: string; level: AudibleRiskLevel; cameraId: string | null; evidenceLabel: string }>();
  const add = (
    id: string,
    level: AudibleRiskLevel | null,
    record: { freshness: { status: string }; evidence: Array<{ serverValidated?: boolean; cameraId?: string | null; label: string }> },
  ) => {
    if (!level || !isFreshVerifiedRecord(record)) return;
    const evidence = record.evidence.find((reference) => reference.serverValidated === true);
    if (!evidence) return;
    const previous = candidates.get(id);
    if (!previous || riskRank(level) > riskRank(previous.level)) {
      candidates.set(id, { id, level, cameraId: evidence.cameraId ?? null, evidenceLabel: evidence.label });
    }
  };

  for (const alert of context.alerts.items) {
    if (alert.acknowledged === true) continue;
    add(alert.alertId, riskLevel(alert.level), alert);
  }
  for (const event of context.events) add(event.eventId, riskLevel(event.riskLevel), event);

  const records = Array.from(candidates.values()).sort((left, right) => riskRank(right.level) - riskRank(left.level) || left.id.localeCompare(right.id));
  const mostSevere = records[0];
  if (!mostSevere) return { visualState: "watching", speechCandidate: null };
  if (mostSevere.level === "MEDIUM") return { visualState: "attention", speechCandidate: null };

  const copy = wording(mostSevere.level, mostSevere.cameraId);
  return {
    visualState: "high_risk",
    speechCandidate: {
      id: mostSevere.id,
      level: mostSevere.level,
      cameraId: mostSevere.cameraId,
      evidenceLabel: mostSevere.evidenceLabel,
      ...copy,
    },
  };
}

export function canSpeakRiskAlert({
  alert,
  spoken,
  lastSpokenAt,
  now,
}: {
  alert: AudibleRiskAlert;
  spoken: AlertMemory | undefined;
  lastSpokenAt: number | null;
  now: number;
}) {
  const severityIncreased = spoken && riskRank(alert.level) > riskRank(spoken.level);
  if (spoken && !severityIncreased) {
    const mayRepeatCritical = alert.level === "CRITICAL" && now - spoken.spokenAt >= CRITICAL_REPEAT_COOLDOWN_MS;
    if (!mayRepeatCritical) return false;
  }
  return severityIncreased || lastSpokenAt === null || now - lastSpokenAt >= GLOBAL_SPEECH_COOLDOWN_MS;
}

function browserSpeechFallbackAvailable() {
  return typeof window !== "undefined" && "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;
}

function readStoredEnabled() {
  try {
    const value = window.localStorage.getItem(AUDIBLE_ALERTS_STORAGE_KEY);
    if (!value) return false;
    const parsed = JSON.parse(value) as { version?: number; enabled?: unknown };
    return parsed.version === 1 && parsed.enabled === true;
  } catch {
    return false;
  }
}

function persistEnabled(enabled: boolean) {
  try {
    window.localStorage.setItem(AUDIBLE_ALERTS_STORAGE_KEY, JSON.stringify({ version: 1, enabled }));
  } catch {
    // Storage can be unavailable in private or restricted browser contexts.
  }
}

function speakWithBrowserFallback(alert: AudibleRiskAlert) {
  if (!browserSpeechFallbackAvailable()) return false;
  try {
    const utterance = new SpeechSynthesisUtterance(alert.spokenText);
    // Browser speech is only a fallback. A 0.84 Web Speech pitch is roughly
    // three semitones below neutral, and 0.92 keeps alerts deliberate but clear.
    utterance.rate = 0.92;
    utterance.pitch = 0.84;
    utterance.volume = 0.8;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utterance);
    return true;
  } catch {
    return false;
  }
}

/**
 * Opt-in audible alert controller for the Intelligence surface. Gemini native
 * audio is always the primary path. Browser `speechSynthesis` is considered
 * only after that path reports unavailable, never merely because it is idle.
 */
export function useAudibleRiskAlerts({
  context,
  geminiAvailable,
  prepareGeminiAudio,
  speakWithGemini,
  stopGeminiAudio,
  onSpokenAlert,
}: {
  context: IntelligenceContext | null;
  geminiAvailable: boolean;
  prepareGeminiAudio: () => Promise<boolean>;
  speakWithGemini: (alertId: string) => Promise<GeminiAlertPlaybackResult>;
  stopGeminiAudio: () => void;
  onSpokenAlert?: (alert: AudibleRiskAlert) => void;
}) {
  const [enabled, setEnabled] = useState(false);
  const [browserFallbackAvailable, setBrowserFallbackAvailable] = useState<boolean | null>(null);
  const [geminiPlaybackState, setGeminiPlaybackState] = useState<"unknown" | "ready" | "unavailable">("unknown");
  const spokenByIdRef = useRef(new Map<string, AlertMemory>());
  const lastSpokenAtRef = useRef<number | null>(null);
  const inFlightAlertRef = useRef<string | null>(null);
  const preparingOutputRef = useRef(false);
  const onSpokenAlertRef = useRef(onSpokenAlert);
  const assessment = useMemo(() => assessAudibleRisk(context), [context]);

  useEffect(() => {
    onSpokenAlertRef.current = onSpokenAlert;
  }, [onSpokenAlert]);

  useEffect(() => {
    // Defer hydration-only preference reads by one task. This preserves a
    // stable server render and avoids a synchronous effect-driven re-render.
    const task = window.setTimeout(() => {
      setBrowserFallbackAvailable(browserSpeechFallbackAvailable());
      setEnabled(readStoredEnabled());
    }, 0);
    return () => window.clearTimeout(task);
  }, []);

  useEffect(() => {
    // A configuration change must not make a stale readiness value look live.
    const task = window.setTimeout(() => {
      setGeminiPlaybackState(geminiAvailable ? "unknown" : "unavailable");
    }, 0);
    return () => window.clearTimeout(task);
  }, [geminiAvailable]);

  const stopSpeech = useCallback(() => {
    stopGeminiAudio();
    if (browserSpeechFallbackAvailable()) window.speechSynthesis.cancel();
  }, [stopGeminiAudio]);

  const armGeminiOutput = useCallback(async () => {
    if (!geminiAvailable || geminiPlaybackState === "ready" || preparingOutputRef.current) {
      return geminiPlaybackState === "ready";
    }

    // `prepare` must run in a browser user-activation callback. It resumes the
    // output-only AudioContext; it never requests microphone access.
    preparingOutputRef.current = true;
    try {
      const prepared = await prepareGeminiAudio();
      setGeminiPlaybackState(prepared ? "ready" : "unavailable");
      return prepared;
    } finally {
      preparingOutputRef.current = false;
    }
  }, [geminiAvailable, geminiPlaybackState, prepareGeminiAudio]);

  const setAudibleAlertsEnabled = useCallback(async (nextEnabled: boolean) => {
    if (!nextEnabled) {
      setEnabled(false);
      persistEnabled(false);
      stopSpeech();
      return;
    }

    // This runs from the visible opt-in control. It primes the native Gemini
    // player without opening the microphone or listening in the background.
    if (geminiAvailable) await armGeminiOutput();
    setEnabled(true);
    persistEnabled(true);
  }, [armGeminiOutput, geminiAvailable, stopSpeech]);

  useEffect(() => {
    if (!enabled || !geminiAvailable || geminiPlaybackState !== "unknown") return;

    // The operator has already opted in and their preference is persisted.
    // After a refresh, browsers require one user interaction before they allow
    // native audio to resume. Arm output on that first interaction instead of
    // making the operator find and toggle the alert control again.
    const armFromUserGesture = () => {
      void armGeminiOutput();
    };
    window.addEventListener("pointerdown", armFromUserGesture, { once: true, passive: true });
    window.addEventListener("keydown", armFromUserGesture, { once: true });
    return () => {
      window.removeEventListener("pointerdown", armFromUserGesture);
      window.removeEventListener("keydown", armFromUserGesture);
    };
  }, [armGeminiOutput, enabled, geminiAvailable, geminiPlaybackState]);

  useEffect(() => {
    if (!enabled || !assessment.speechCandidate || inFlightAlertRef.current) return;
    const alert = assessment.speechCandidate;
    const now = Date.now();
    if (!canSpeakRiskAlert({
      alert,
      spoken: spokenByIdRef.current.get(alert.id),
      lastSpokenAt: lastSpokenAtRef.current,
      now,
    })) return;

    // A persisted preference still needs one browser user activation after a
    // page load. The gesture listener above arms it automatically; until then
    // this guard prevents an untrusted autoplay attempt.
    if (geminiAvailable && geminiPlaybackState === "unknown") return;

    let cancelled = false;
    inFlightAlertRef.current = alert.id;
    const recordSpeech = () => {
      if (cancelled) return;
      const spokenAt = Date.now();
      spokenByIdRef.current.set(alert.id, { level: alert.level, spokenAt });
      lastSpokenAtRef.current = spokenAt;
      onSpokenAlertRef.current?.(alert);
    };

    void (async () => {
      try {
        let shouldTryBrowserFallback = !geminiAvailable || geminiPlaybackState === "unavailable";
        if (geminiAvailable && geminiPlaybackState === "ready") {
          const result = await speakWithGemini(alert.id);
          if (result === "spoken") {
            recordSpeech();
            return;
          }
          // An active operator conversation is not a Gemini outage. Let that
          // connection finish rather than interrupting it or switching engines.
          if (result === "busy") return;
          setGeminiPlaybackState("unavailable");
          shouldTryBrowserFallback = true;
        }

        // This is intentionally the last branch: only an unavailable Gemini
        // output path may use browser synthesis as a compatibility fallback.
        if (shouldTryBrowserFallback && speakWithBrowserFallback(alert)) {
          recordSpeech();
        }
      } finally {
        inFlightAlertRef.current = null;
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [assessment.speechCandidate, enabled, geminiAvailable, geminiPlaybackState, speakWithGemini]);

  useEffect(() => stopSpeech, [stopSpeech]);

  const outputUnavailable = geminiAvailable
    ? geminiPlaybackState === "unavailable" && browserFallbackAvailable === false
    : browserFallbackAvailable === false;
  const state: AudibleRiskControlState = !enabled
    ? "muted"
    : geminiAvailable && geminiPlaybackState === "unknown"
      ? "arming"
      : outputUnavailable || assessment.visualState === "unavailable"
      ? "unavailable"
      : assessment.visualState;

  return {
    enabled,
    setEnabled: setAudibleAlertsEnabled,
    stopSpeech,
    browserFallbackAvailable,
    geminiPlaybackState,
    visualState: assessment.visualState,
    state,
  };
}
