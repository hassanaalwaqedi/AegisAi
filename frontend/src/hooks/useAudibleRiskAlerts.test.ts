import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  assessAudibleRisk,
  canSpeakRiskAlert,
  useAudibleRiskAlerts,
  type AudibleRiskAlert,
} from "./useAudibleRiskAlerts";
import type { IntelligenceContext } from "@/lib/intelligence-context";

const now = "2026-08-02T12:00:00.000Z";

function highRiskContext(): IntelligenceContext {
  return {
    schemaVersion: "1.0",
    contextId: "audible-alert-test",
    generatedAt: now,
    refreshAfterSeconds: 15,
    overall: { status: "live", degradedReasons: [], checks: [] },
    cameras: { total: 1, totalConfigured: 1, online: 1, offline: 0, stale: 0, unavailable: 0, items: [], freshness: { observedAt: now, status: "live" } },
    alerts: {
      activeCount: 1,
      freshness: { observedAt: now, status: "live" },
      items: [{
        alertId: "alert-high-1",
        level: "HIGH",
        acknowledged: false,
        freshness: { observedAt: now, status: "live" },
        evidence: [{ kind: "alert", id: "alert-high-1", label: "Validated alert", cameraId: "north-gate", serverValidated: true, validatedAt: now }],
      }],
    },
    incidents: { capability: "unavailable", reason: "No incident domain." },
    events: [],
    tracks: [],
    detections: { recentCount: 0, freshness: { observedAt: now, status: "live" } },
    semantic: { capability: "unavailable", evidence: [], freshness: { observedAt: now, status: "unavailable", reason: "Unavailable." } },
    pipeline: { running: true, stages: [], freshness: { observedAt: now, status: "live" } },
    ai: { chat: "live", providerConfigured: true, evidenceGrounding: "live", voice: { pushToTalk: "live", handsFree: "live" } },
    suggestions: [],
  };
}

function installBrowserSpeechFallback() {
  const speak = vi.fn();
  vi.stubGlobal("speechSynthesis", { cancel: vi.fn(), speak });
  vi.stubGlobal("SpeechSynthesisUtterance", class { rate = 1; pitch = 1; volume = 1; constructor(public readonly text: string) {} });
  return speak;
}

function installLocalStorage(values: Record<string, string> = {}) {
  const store = new Map(Object.entries(values));
  vi.stubGlobal("localStorage", {
    getItem: vi.fn((key: string) => store.get(key) ?? null),
    setItem: vi.fn((key: string, value: string) => store.set(key, value)),
    clear: vi.fn(() => store.clear()),
  });
  return store;
}

afterEach(() => {
  window.localStorage?.clear();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("audible Intelligence risk alerts", () => {
  it("accepts only a fresh, server-validated HIGH/CRITICAL candidate", () => {
    const assessment = assessAudibleRisk(highRiskContext());
    expect(assessment.visualState).toBe("high_risk");
    expect(assessment.speechCandidate).toMatchObject({ id: "alert-high-1", level: "HIGH" });

    const stale = highRiskContext();
    stale.alerts.items[0].freshness.status = "stale";
    expect(assessAudibleRisk(stale).speechCandidate).toBeNull();

    const degradedElsewhere = highRiskContext();
    degradedElsewhere.overall.status = "degraded";
    expect(assessAudibleRisk(degradedElsewhere).speechCandidate).toMatchObject({ id: "alert-high-1" });
  });

  it("deduplicates event IDs and observes the global cooldown", () => {
    const alert: AudibleRiskAlert = {
      id: "alert-high-1", level: "HIGH", cameraId: null, evidenceLabel: "Validated", spokenText: "High", panelText: "High",
    };
    expect(canSpeakRiskAlert({ alert, spoken: undefined, lastSpokenAt: null, now: 1_000 })).toBe(true);
    expect(canSpeakRiskAlert({ alert, spoken: { level: "HIGH", spokenAt: 1_000 }, lastSpokenAt: 1_000, now: 2_000 })).toBe(false);
    expect(canSpeakRiskAlert({ alert: { ...alert, level: "CRITICAL" }, spoken: { level: "HIGH", spokenAt: 1_000 }, lastSpokenAt: 1_000, now: 2_000 })).toBe(true);
  });

  it("uses native Gemini audio before browser synthesis", async () => {
    const browserSpeak = installBrowserSpeechFallback();
    const prepareGeminiAudio = vi.fn(async () => true);
    const speakWithGemini = vi.fn(async () => "spoken" as const);
    const { result } = renderHook(() => useAudibleRiskAlerts({
      context: highRiskContext(),
      geminiAvailable: true,
      prepareGeminiAudio,
      speakWithGemini,
      stopGeminiAudio: vi.fn(),
    }));

    await act(async () => { await result.current.setEnabled(true); });
    await waitFor(() => expect(speakWithGemini).toHaveBeenCalledWith("alert-high-1"));
    expect(prepareGeminiAudio).toHaveBeenCalledOnce();
    expect(browserSpeak).not.toHaveBeenCalled();
  });

  it("uses browser speech only after Gemini reports its output path unavailable", async () => {
    const browserSpeak = installBrowserSpeechFallback();
    const speakWithGemini = vi.fn(async () => "unavailable" as const);
    const { result } = renderHook(() => useAudibleRiskAlerts({
      context: highRiskContext(),
      geminiAvailable: true,
      prepareGeminiAudio: vi.fn(async () => true),
      speakWithGemini,
      stopGeminiAudio: vi.fn(),
    }));

    await act(async () => { await result.current.setEnabled(true); });
    await waitFor(() => expect(browserSpeak).toHaveBeenCalledOnce());
    expect(speakWithGemini).toHaveBeenCalledOnce();
    expect(browserSpeak).toHaveBeenCalledWith(expect.objectContaining({
      text: "High-risk event detected near north-gate. Evidence has been saved. Operator review is required.",
      rate: 0.92,
      pitch: 0.84,
      volume: 0.8,
    }));
  });

  it("keeps an opted-in alert preference and arms Gemini after the first post-reload interaction", async () => {
    const storedValues = installLocalStorage({
      "aegis.intelligence.audible-risk-alerts.v1": JSON.stringify({ version: 1, enabled: true }),
    });
    const prepareGeminiAudio = vi.fn(async () => true);
    const speakWithGemini = vi.fn(async () => "spoken" as const);
    const { result } = renderHook(() => useAudibleRiskAlerts({
      context: highRiskContext(),
      geminiAvailable: true,
      prepareGeminiAudio,
      speakWithGemini,
      stopGeminiAudio: vi.fn(),
    }));

    await waitFor(() => expect(result.current.enabled).toBe(true));
    expect(result.current.state).toBe("arming");
    expect(prepareGeminiAudio).not.toHaveBeenCalled();

    await act(async () => {
      window.dispatchEvent(new Event("pointerdown"));
    });
    await waitFor(() => expect(prepareGeminiAudio).toHaveBeenCalledOnce());
    await waitFor(() => expect(speakWithGemini).toHaveBeenCalledWith("alert-high-1"));
    expect(storedValues.get("aegis.intelligence.audible-risk-alerts.v1")).toContain("\"enabled\":true");
  });
});
