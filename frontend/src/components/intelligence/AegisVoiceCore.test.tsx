import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const testState = vi.hoisted(() => ({
  fetchCapabilities: vi.fn(),
  fetchPersistedEvidence: vi.fn(),
  fetchActiveIncidents: vi.fn(),
  sendChatMessage: vi.fn(),
  callbacks: null as any,
  voice: {
    state: "off" as "off" | "connecting" | "ready" | "listening" | "thinking" | "speaking" | "error",
    error: null as string | null,
    waveformLevel: 0,
    playbackLevel: 0,
    captureMode: null as "speech-recognition" | null,
    isCapturing: false,
    sessionPhase: "idle" as "idle" | "listening" | "processing" | "response",
    sessionOutcome: null as "cancelled" | "timeout" | null,
    sessionSecondsRemaining: 0,
    sessionActive: false,
    startListening: vi.fn(),
    enableHandsFree: vi.fn(),
    beginPushToTalk: vi.fn(),
    endPushToTalk: vi.fn(),
    sendTypedFallback: vi.fn(() => true),
    prepareAudibleAlertAudio: vi.fn(async () => true),
    speakAudibleRiskAlert: vi.fn(async () => "spoken"),
    stopAudibleRiskAlert: vi.fn(),
    stop: vi.fn(),
  },
}));

vi.mock("@/hooks/useGeminiLiveVoice", () => ({
  useGeminiLiveVoice: (callbacks: unknown) => {
    testState.callbacks = callbacks;
    return testState.voice;
  },
}));

vi.mock("@/lib/live-voice", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/live-voice")>();
  return { ...actual, fetchLiveCapabilities: (...args: unknown[]) => testState.fetchCapabilities(...args) };
});

vi.mock("@/lib/ai-api", () => ({
  sendChatMessage: (...args: unknown[]) => testState.sendChatMessage(...args),
}));

vi.mock("@/lib/evidence-api", () => ({
  fetchRecentPersistedEvidence: (...args: unknown[]) => testState.fetchPersistedEvidence(...args),
  fetchActiveIncidents: (...args: unknown[]) => testState.fetchActiveIncidents(...args),
  persistedEvidenceSnapshotUrl: () => null,
}));

vi.mock("@/components/intelligence/AIOrb", () => ({
  default: ({ voiceState, activeCapability, onActivate, onListenToggle, voiceSessionActive }: { voiceState: string; activeCapability?: string; onActivate: () => void; onListenToggle: () => void; voiceSessionActive: boolean }) => (
    <div>
      <button type="button" onClick={onActivate} data-testid="aegis-voice-orb" data-voice-state={voiceState} data-active-capability={activeCapability ?? ""}>Aegis Voice Core</button>
      <button type="button" onClick={onListenToggle}>{voiceSessionActive ? "Stop listening" : "Ask Aegis"}</button>
    </div>
  ),
}));

vi.mock("@/components/intelligence/NodeOrbit", () => ({
  default: ({ activeNodeId }: { activeNodeId?: string }) => <div data-testid="voice-capability-map" data-active-node={activeNodeId ?? ""} />,
}));

import AegisVoiceCore from "./AegisVoiceCore";

const capability = {
  availability: "live" as const,
  nativeAudio: true,
  inputTranscription: true,
  outputTranscription: true,
  pushToTalk: "live" as const,
  websocketProtocol: "aegis-live-v1" as const,
};

const nodes = [{ id: "cameras", label: "Cameras", sublabel: "Runtime", icon: "Camera", x: 25, y: 59, color: "#38d6ff", availability: "live" as const, href: "/cameras" }];

function renderCore() {
  const onCapabilityHighlight = vi.fn();
  const view = render(<AegisVoiceCore contextAvailability="live" nodes={nodes} activeCapability={null} onCapabilityHighlight={onCapabilityHighlight} />);
  return { ...view, onCapabilityHighlight };
}

beforeEach(() => {
  testState.fetchCapabilities.mockResolvedValue(capability);
  testState.fetchPersistedEvidence.mockResolvedValue([]);
  testState.fetchActiveIncidents.mockResolvedValue([]);
  Object.assign(testState.voice, {
    state: "off", error: null, waveformLevel: 0, playbackLevel: 0, captureMode: null, isCapturing: false,
    sessionPhase: "idle", sessionOutcome: null, sessionSecondsRemaining: 0, sessionActive: false,
  });
  Object.values(testState.voice).forEach((value) => {
    if (typeof value === "function" && "mockClear" in value) (value as ReturnType<typeof vi.fn>).mockClear();
  });
  testState.callbacks = null;
});

afterEach(cleanup);

describe("AegisVoiceCore", () => {
  it("starts only from the explicit Ask Aegis click", async () => {
    renderCore();
    await waitFor(() => expect(screen.getByTestId("aegis-voice-orb")).toHaveAttribute("data-voice-state", "off"));
    fireEvent.click(screen.getByRole("button", { name: "Ask Aegis" }));
    expect(testState.voice.startListening).toHaveBeenCalledTimes(1);
  });

  it("renders ready, listening, thinking, speaking, degraded, and microphone-denied states truthfully", async () => {
    const { rerender } = renderCore();
    await waitFor(() => expect(testState.callbacks).toBeTruthy());

    for (const state of ["ready", "listening", "thinking", "speaking"] as const) {
      testState.voice.state = state;
      rerender(<AegisVoiceCore contextAvailability="live" nodes={nodes} activeCapability={null} onCapabilityHighlight={vi.fn()} />);
      expect(screen.getByTestId("aegis-voice-orb")).toHaveAttribute("data-voice-state", state);
    }

    rerender(<AegisVoiceCore contextAvailability="degraded" nodes={nodes} activeCapability={null} onCapabilityHighlight={vi.fn()} />);
    expect(screen.getByTestId("aegis-voice-orb")).toHaveAttribute("data-voice-state", "degraded");

    testState.voice.state = "error";
    testState.voice.error = "Microphone permission was denied.";
    rerender(<AegisVoiceCore contextAvailability="live" nodes={nodes} activeCapability={null} onCapabilityHighlight={vi.fn()} />);
    expect(screen.getByRole("alert")).toHaveTextContent(/Microphone permission was denied/i);
    fireEvent.click(screen.getByRole("button", { name: "Reconnect voice" }));
    expect(testState.voice.stop).toHaveBeenCalledTimes(1);
    expect(testState.voice.startListening).toHaveBeenCalledTimes(1);
  });

  it("stops through the explicit Stop control, Escape, and unmount cleanup", async () => {
    testState.voice.state = "listening";
    testState.voice.sessionActive = true;
    const { unmount } = renderCore();
    await waitFor(() => expect(screen.getByRole("button", { name: "Stop listening, microphone capture, and audio playback" })).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Stop listening, microphone capture, and audio playback" }));
    fireEvent.keyDown(window, { key: "Escape" });
    expect(testState.voice.stop).toHaveBeenCalledTimes(2);
    unmount();
    expect(testState.voice.stop).toHaveBeenCalledTimes(3);
  });

  it("shows timed listening feedback and a truthful timeout outcome", async () => {
    testState.voice.state = "listening";
    testState.voice.sessionActive = true;
    testState.voice.sessionPhase = "listening";
    testState.voice.sessionSecondsRemaining = 42;
    const { rerender } = renderCore();

    expect(screen.getByRole("progressbar", { name: /voice session time remaining/i })).toHaveAttribute("aria-valuenow", "42");
    expect(screen.getByText(/42s remaining/i)).toBeInTheDocument();

    testState.voice.state = "speaking";
    testState.voice.sessionPhase = "response";
    testState.voice.sessionSecondsRemaining = 0;
    rerender(<AegisVoiceCore contextAvailability="live" nodes={nodes} activeCapability={null} onCapabilityHighlight={vi.fn()} />);
    expect(screen.queryByRole("progressbar", { name: /voice session time remaining/i })).not.toBeInTheDocument();
    expect(screen.getByText("Playback active")).toBeInTheDocument();

    testState.voice.state = "off";
    testState.voice.sessionActive = false;
    testState.voice.sessionOutcome = "timeout";
    rerender(<AegisVoiceCore contextAvailability="live" nodes={nodes} activeCapability={null} onCapabilityHighlight={vi.fn()} />);
    expect(screen.getByText(/Voice session timed out/i)).toBeInTheDocument();
  });

  it("uses only typed citations and approved UI commands to highlight map nodes", async () => {
    const { onCapabilityHighlight } = renderCore();
    await waitFor(() => expect(testState.callbacks).toBeTruthy());

    await act(async () => {
      testState.callbacks.onTranscript({ speaker: "aegis", text: "Cameras are online.", isFinal: true });
    });
    expect(onCapabilityHighlight).not.toHaveBeenCalled();

    await act(async () => {
      testState.callbacks.onCitations([{ evidenceId: "camera:gate-2", kind: "camera", label: "Gate 2", availability: "live", observedAt: "2026-07-30T12:00:00.000Z" }]);
    });
    expect(onCapabilityHighlight).toHaveBeenLastCalledWith("cameras");

    await act(async () => {
      testState.callbacks.onUiCommand({ kind: "show_track_evidence" });
    });
    expect(onCapabilityHighlight).toHaveBeenLastCalledWith("tracking");
  });

  it("shows a short response and opens the compact slash text fallback", async () => {
    renderCore();
    await waitFor(() => expect(testState.callbacks).toBeTruthy());
    await act(async () => {
      testState.callbacks.onTranscript({ speaker: "aegis", text: "Two camera sources are online.", isFinal: true });
    });
    expect(screen.getByText(/Two camera sources are online/i)).toBeInTheDocument();

    fireEvent.keyDown(window, { key: "/" });
    const input = screen.getByPlaceholderText(/Type a request/i);
    fireEvent.change(input, { target: { value: "Show camera status" } });
    fireEvent.submit(input.closest("form")!);
    expect(testState.voice.sendTypedFallback).toHaveBeenCalledWith("Show camera status");
  });

  it("preserves the existing read-only text path when no Live session is active", async () => {
    testState.voice.sendTypedFallback.mockReturnValueOnce(false);
    testState.sendChatMessage.mockResolvedValueOnce({ answer: "Camera evidence is unavailable." });
    const onCapabilityHighlight = vi.fn();
    render(
      <AegisVoiceCore
        contextAvailability="live"
        textChatAvailability="live"
        nodes={nodes}
        activeCapability={null}
        onCapabilityHighlight={onCapabilityHighlight}
      />,
    );
    await waitFor(() => expect(testState.callbacks).toBeTruthy());

    fireEvent.keyDown(window, { key: "/" });
    const input = screen.getByPlaceholderText(/Type a request/i);
    fireEvent.change(input, { target: { value: "Show camera status" } });
    fireEvent.submit(input.closest("form")!);

    await waitFor(() => expect(testState.sendChatMessage).toHaveBeenCalledWith("Show camera status"));
    expect(screen.getByText(/Camera evidence is unavailable/i)).toBeInTheDocument();
    expect(onCapabilityHighlight).not.toHaveBeenCalled();
  });

  it("shows compact persisted alert evidence only after the existing drawer is opened", async () => {
    testState.fetchPersistedEvidence.mockResolvedValueOnce([{
      event_id: "evt-1",
      camera_name: "North Gate",
      risk_level: "HIGH",
      timestamp: "2026-08-02T12:00:00.000Z",
      reason: "Confirmed restricted-zone intrusion.",
      snapshot_available: false,
      snapshot_url: null,
    }]);
    renderCore();
    await waitFor(() => expect(testState.callbacks).toBeTruthy());

    await act(async () => {
      testState.callbacks.onTranscript({ speaker: "aegis", text: "A risk alert was recorded.", isFinal: true });
    });
    fireEvent.click(screen.getAllByRole("button", { name: "Open Conversation and Evidence" }).at(-1)!);

    expect(await screen.findByText(/Confirmed restricted-zone intrusion/i)).toBeInTheDocument();
    expect(screen.getByText("HIGH")).toBeInTheDocument();
    expect(screen.getByRole("article")).toHaveTextContent("North Gate");
  });

  it("shows compact active incident context in the existing Evidence drawer", async () => {
    testState.fetchActiveIncidents.mockResolvedValueOnce([{
      incident_id: "inc-north-gate-1",
      camera_id: "north-gate",
      current_risk_level: "HIGH",
      evidence_ids: ["evt-1", "evt-2"],
      summary_reason: "Track remained in the restricted zone.",
      last_seen_time: "2026-08-02T12:02:00.000Z",
      status: "active",
    }]);
    renderCore();
    await waitFor(() => expect(testState.callbacks).toBeTruthy());
    await act(async () => {
      testState.callbacks.onTranscript({ speaker: "aegis", text: "A risk alert was recorded.", isFinal: true });
    });
    fireEvent.click(screen.getAllByRole("button", { name: "Open Conversation and Evidence" }).at(-1)!);

    expect(await screen.findByText("Active incidents")).toBeInTheDocument();
    expect(screen.getByText(/Incident.*north-gate/i)).toBeInTheDocument();
    expect(screen.getByText(/2 linked evidence/i)).toBeInTheDocument();
    expect(screen.getByText(/Track remained in the restricted zone/i)).toBeInTheDocument();
  });
});
