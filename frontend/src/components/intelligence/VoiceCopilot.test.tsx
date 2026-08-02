import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const testState = vi.hoisted(() => ({
  fetchCapabilities: vi.fn(),
  callbacks: null as any,
  voice: {
    state: "off",
    error: null as string | null,
    waveformLevel: 0,
    captureMode: null as "speech-recognition" | null,
    isCapturing: false,
    sessionActive: false,
    sessionPhase: "idle" as "idle" | "listening" | "processing" | "response",
    sessionOutcome: null as "cancelled" | "timeout" | null,
    sessionSecondsRemaining: 0,
    startListening: vi.fn(),
    enableHandsFree: vi.fn(),
    beginPushToTalk: vi.fn(),
    endPushToTalk: vi.fn(),
    sendTypedFallback: vi.fn(() => false),
    stop: vi.fn(),
  },
}));

vi.mock("@/hooks/useGeminiLiveVoice", () => ({
  useGeminiLiveVoice: (callbacks: unknown) => {
    testState.callbacks = callbacks;
    return testState.voice;
  },
  voiceStateLabel: (state: string) => ({
    off: "Ready", connecting: "Connecting", ready: "Ready", listening: "Listening", thinking: "Thinking", speaking: "Aegis speaking", error: "Connection error",
  }[state] ?? state),
}));

vi.mock("@/lib/live-voice", () => ({
  fetchLiveCapabilities: (...args: unknown[]) => testState.fetchCapabilities(...args),
}));

import VoiceCopilot from "./VoiceCopilot";

const liveCapability = {
  availability: "live" as const,
  model: "gemini-live-test",
  voice: "Kore",
  nativeAudio: true,
  inputTranscription: true,
  outputTranscription: true,
  pushToTalk: "live" as const,
  websocketProtocol: "aegis-live-v1" as const,
};

beforeEach(() => {
  testState.fetchCapabilities.mockResolvedValue(liveCapability);
  Object.assign(testState.voice, {
    state: "off", error: null, waveformLevel: 0, captureMode: null, isCapturing: false,
    sessionActive: false, sessionPhase: "idle", sessionOutcome: null, sessionSecondsRemaining: 0,
  });
  Object.values(testState.voice).forEach((value) => {
    if (typeof value === "function" && "mockClear" in value) (value as ReturnType<typeof vi.fn>).mockClear();
  });
  testState.callbacks = null;
});

afterEach(cleanup);

describe("VoiceCopilot", () => {
  it("renders a truthful unavailable state rather than inventing a voice capability", async () => {
    testState.fetchCapabilities.mockResolvedValue({ ...liveCapability, availability: "unavailable", reason: "GEMINI_API_KEY is not configured." });
    render(<VoiceCopilot contextAvailability="unavailable" contextReason="Live voice is unavailable." />);

    await waitFor(() => expect(screen.getByText(/Voice unavailable:/i)).toHaveTextContent(/GEMINI_API_KEY/i));
    expect(screen.getByRole("button", { name: /Ask Aegis/i })).toBeDisabled();
  });

  it("shows the required voice state indicator and starts only after an explicit operator action", async () => {
    render(<VoiceCopilot contextAvailability="live" />);

    await waitFor(() => expect(screen.getByText("Ready")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Ask Aegis/i }));
    expect(testState.voice.startListening).toHaveBeenCalledTimes(1);
  });

  it("renders operator and Aegis transcripts with evidence citations", async () => {
    render(<VoiceCopilot contextAvailability="live" />);
    await waitFor(() => expect(testState.callbacks).toBeTruthy());

    await act(async () => {
      testState.callbacks.onTranscript({ speaker: "operator", text: "How many cameras are online?", isFinal: true });
      testState.callbacks.onTranscript({ speaker: "aegis", text: "I have verified the camera runtime state.", isFinal: true });
      testState.callbacks.onCitations([{ evidenceId: "camera:gate-2", kind: "camera", label: "Gate 2", availability: "live", observedAt: "2026-07-30T12:00:00.000Z" }]);
    });

    expect(screen.getByText("How many cameras are online?")).toBeInTheDocument();
    expect(screen.getByText(/verified the camera runtime/i)).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Gate 2" }).length).toBeGreaterThan(0);
  });

  it("stops audio/capture through the visible click-to-listen controls", async () => {
    testState.voice.state = "speaking";
    testState.voice.sessionActive = true;
    render(<VoiceCopilot contextAvailability="live" />);
    await waitFor(() => expect(screen.getByText("Aegis speaking")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Stop" }));
    expect(testState.voice.stop).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: /Stop listening/i }));
    expect(testState.voice.startListening).toHaveBeenCalledTimes(1);
  });

  it("uses an explicit degraded message when the Live gateway reports an error", async () => {
    testState.voice.state = "error";
    testState.voice.error = "Gemini Live could not validate the configured model.";
    render(<VoiceCopilot contextAvailability="live" />);

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/Microphone capture and audio playback have stopped/i));
    expect(screen.getByText(/could not validate/i)).toBeInTheDocument();
  });
});
