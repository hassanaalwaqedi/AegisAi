import { afterEach, describe, expect, it, vi } from "vitest";

import { aegisVoiceCoreStateSchema, liveCapabilitiesSchema, liveWebSocketUrl, safeUiCommandSchema, serverVoiceEnvelopeSchema, voiceStateSchema } from "./live-voice";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("Gemini Live browser contracts", () => {
  it("supports only the explicit VoiceState transitions", () => {
    expect(voiceStateSchema.options).toEqual(["off", "connecting", "ready", "listening", "thinking", "speaking", "error"]);
    expect(aegisVoiceCoreStateSchema.safeParse("degraded").success).toBe(true);
    expect(aegisVoiceCoreStateSchema.safeParse("invented-state").success).toBe(false);
  });

  it("rejects raw LLM navigation targets and only permits the typed UI command allowlist", () => {
    expect(safeUiCommandSchema.safeParse({ kind: "open_cameras" }).success).toBe(true);
    expect(safeUiCommandSchema.safeParse({ kind: "open_cameras", url: "javascript:alert(1)" }).success).toBe(false);
    expect(safeUiCommandSchema.safeParse({ kind: "navigate", target: "/admin" }).success).toBe(false);
  });

  it("accepts native-audio session rates without exposing provider model or voice", () => {
    const capability = liveCapabilitiesSchema.parse({
      availability: "live", nativeAudio: true, inputTranscription: true, outputTranscription: true,
      inputSampleRate: 16000, outputSampleRate: 24000, pushToTalk: "live", websocketProtocol: "aegis-live-v1",
    });
    expect(capability.inputSampleRate).toBe(16000);
    expect("model" in capability).toBe(false);
    expect("voice" in capability).toBe(false);
  });

  it("uses typed tool, turn, and interruption events alongside binary audio frames", () => {
    expect(serverVoiceEnvelopeSchema.safeParse({ version: "1.0", type: "tool_activity", tool: "get_live_camera_status", toolStatus: "calling", turnId: "turn-1" }).success).toBe(true);
    expect(serverVoiceEnvelopeSchema.safeParse({ version: "1.0", type: "interrupted", turnId: "turn-1" }).success).toBe(true);
    expect(serverVoiceEnvelopeSchema.safeParse({ version: "1.0", type: "audio", data: "base64" }).success).toBe(false);
  });

  it("connects local Next development ports to the FastAPI Live WebSocket", () => {
    vi.stubEnv("NEXT_PUBLIC_AEGIS_LIVE_WS_URL", "");
    vi.stubEnv("NEXT_PUBLIC_WS_URL", "");
    vi.stubGlobal("window", { location: { origin: "http://localhost:3001" } });

    expect(liveWebSocketUrl("voice-session")).toBe("ws://localhost:8080/ws/intelligence/live/voice-session");
  });
});
