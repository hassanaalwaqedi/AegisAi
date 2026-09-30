import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const testState = vi.hoisted(() => ({
  fetchCapabilities: vi.fn(),
  callbacks: null as any,
  voice: {
    state: "off",
    voiceSessionState: "DISABLED",
    error: null as string | null,
    waveformLevel: 0,
    playbackLevel: 0,
    isCapturing: false,
    sessionActive: false,
    isActivated: false,
    isMuted: false,
    isUserSpeaking: false,
    wakeWordMode: "browser-recognition",
    activate: vi.fn(),
    deactivate: vi.fn(),
    mute: vi.fn(),
    unmute: vi.fn(),
    interrupt: vi.fn(),
    startListening: vi.fn(),
    stop: vi.fn(),
  },
}));

vi.mock("@/hooks/useGeminiLiveVoice", () => ({
  useGeminiLiveVoice: (callbacks: unknown) => {
    testState.callbacks = callbacks;
    return testState.voice;
  },
}));

vi.mock("@/lib/live-voice", () => ({
  fetchLiveCapabilities: (...args: unknown[]) => testState.fetchCapabilities(...args),
}));

import VoiceCopilot, { uniqueCitations } from "./VoiceCopilot";

const liveCapability = {
  availability: "live" as const,
  nativeAudio: true,
  inputTranscription: true,
  outputTranscription: true,
  pushToTalk: "live" as const,
  websocketProtocol: "aegis-live-v1" as const,
};

beforeEach(() => {
  testState.fetchCapabilities.mockResolvedValue(liveCapability);
  Object.assign(testState.voice, {
    state: "off", voiceSessionState: "DISABLED", error: null, waveformLevel: 0, playbackLevel: 0,
    isCapturing: false, sessionActive: false, isActivated: false, isMuted: false, isUserSpeaking: false, wakeWordMode: "browser-recognition",
  });
  Object.values(testState.voice).forEach((value) => {
    if (typeof value === "function" && "mockClear" in value) (value as ReturnType<typeof vi.fn>).mockClear();
  });
  testState.callbacks = null;
});

afterEach(cleanup);

describe("VoiceCopilot hands-free presence", () => {
  it("deduplicates repeated event citations before rendering", () => {
    const citations = uniqueCitations([
      { evidenceId: "event-det-1", kind: "event", label: "Person detected", availability: "live", observedAt: "2026-09-26T10:00:00.000Z" },
      { evidenceId: "event-det-1", kind: "event", label: "Person detected", availability: "live", observedAt: "2026-09-26T10:00:00.000Z" },
    ]);

    expect(citations).toHaveLength(1);
    expect(citations[0].evidenceId).toBe("event-det-1");
  });

  it("keeps voice disabled truthfully when hands-free capability is unavailable", async () => {
    testState.fetchCapabilities.mockResolvedValue({ ...liveCapability, availability: "unavailable", reason: "GEMINI_API_KEY is not configured." });
    render(<VoiceCopilot contextAvailability="unavailable" contextReason="Live voice is unavailable." />);

    await waitFor(() => expect(screen.getByRole("button", { name: "Talk to Aegis" })).toBeDisabled());
    expect(screen.getByText(/Voice is unavailable for this Aegis session/i)).toBeInTheDocument();
  });

  it("starts listening from one direct operator click", async () => {
    render(<VoiceCopilot contextAvailability="live" />);

    await waitFor(() => expect(screen.getByRole("button", { name: "Talk to Aegis" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Talk to Aegis" }));
    expect(testState.voice.startListening).toHaveBeenCalledOnce();
    expect(testState.voice.activate).not.toHaveBeenCalled();
  });

  it("reports real hands-free session state and analyser levels to the operator", async () => {
    Object.assign(testState.voice, {
      state: "listening", voiceSessionState: "LISTENING", waveformLevel: 0.42,
      isCapturing: true, sessionActive: true, isActivated: true, isUserSpeaking: true,
    });
    const onActivity = vi.fn();
    render(<VoiceCopilot contextAvailability="live" onActivity={onActivity} />);

    await waitFor(() => expect(onActivity).toHaveBeenCalledWith({
      state: "listening", sessionState: "LISTENING", inputLevel: 0.42, outputLevel: 0, isCapturing: true, sessionActive: true,
    }));
    expect(screen.getByText("Listening")).toBeInTheDocument();
  });

  it("shows only a transient cinematic subtitle, including grounded citations", async () => {
    render(<VoiceCopilot contextAvailability="live" />);
    await waitFor(() => expect(testState.callbacks).toBeTruthy());
    await act(async () => {
      testState.callbacks.onCitations([{ evidenceId: "camera:gate-2", kind: "camera", label: "Gate 2", availability: "live", observedAt: "2026-07-30T12:00:00.000Z" }]);
      testState.callbacks.onTranscript({ speaker: "aegis", text: "Camera two is open.", isFinal: true });
    });
    expect(screen.getByText("Camera two is open.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Gate 2" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Voice transcript")).not.toBeInTheDocument();
  });

  it("keeps the single control unavailable while an active voice session owns the microphone", async () => {
    Object.assign(testState.voice, { sessionActive: true, voiceSessionState: "LISTENING" });
    render(<VoiceCopilot contextAvailability="live" />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Talk to Aegis" })).toBeDisabled());
    expect(screen.getByText("Aegis is listening")).toBeInTheDocument();
  });
});
