import { afterEach, describe, expect, it, vi } from "vitest";

import {
  NativePcmPlayer,
  nextBargeInActivityFrame,
  isMeaningfulVoiceTranscript,
  shouldRestartSpeechRecognition,
  VOICE_CONVERSATION_IDLE_TIMEOUT_MS,
} from "./useGeminiLiveVoice";

class MockSource {
  buffer: { duration: number } | null = null;
  onended: (() => void) | null = null;
  connect = vi.fn();
  start = vi.fn();
  stop = vi.fn();
}

class MockAudioContext {
  static close = vi.fn(async () => undefined);
  state = "running";
  currentTime = 0;
  destination = {} as AudioDestinationNode;
  resume = vi.fn(async () => undefined);
  close = MockAudioContext.close;
  createAnalyser = vi.fn(() => ({ fftSize: 0, connect: vi.fn(), getByteTimeDomainData: (samples: Uint8Array) => samples.fill(128) }));
  createBuffer = vi.fn((_channels: number, length: number, sampleRate: number) => ({ duration: length / sampleRate, copyToChannel: vi.fn() }));
  createBufferSource = vi.fn(() => new MockSource());
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("NativePcmPlayer", () => {
  it("does not treat silent hands-free capture frames as a barge-in", () => {
    let activityFrames = 0;
    for (const level of [0.001, 0.012, 0.02, 0.001]) activityFrames = nextBargeInActivityFrame(activityFrames, level);
    expect(activityFrames).toBe(0);

    for (const level of [0.08, 0.07, 0.06, 0.09]) activityFrames = nextBargeInActivityFrame(activityFrames, level);
    expect(activityFrames).toBe(4);
  });

  it("queues native PCM and reports speaking only when playback is scheduled", async () => {
    vi.stubGlobal("AudioContext", MockAudioContext);
    vi.stubGlobal("requestAnimationFrame", () => 1);
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
    const started = vi.fn();
    const player = new NativePcmPlayer({ onLevel: vi.fn(), onStarted: started, onIdle: vi.fn() });

    await player.playPcm(new Int16Array([0, 1024, -1024]).buffer, 24_000);

    expect(started).toHaveBeenCalledOnce();
    expect(player.isPlaying).toBe(true);
    expect(player.stop()).toBe(true);
    expect(player.isPlaying).toBe(false);
  });

  it("releases queued native audio resources on close", async () => {
    vi.stubGlobal("AudioContext", MockAudioContext);
    vi.stubGlobal("requestAnimationFrame", () => 1);
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
    const player = new NativePcmPlayer({ onLevel: vi.fn(), onStarted: vi.fn(), onIdle: vi.fn() });

    await player.prepare();
    await player.close();

    expect(MockAudioContext.close).toHaveBeenCalledTimes(1);
  });
});

describe("click-to-listen session guards", () => {
  it("keeps a conversation open until its 60 second inactivity timeout", () => {
    expect(VOICE_CONVERSATION_IDLE_TIMEOUT_MS).toBe(60_000);
  });

  it("does not submit empty or one-character recognition results", () => {
    expect(isMeaningfulVoiceTranscript("   ")).toBe(false);
    expect(isMeaningfulVoiceTranscript("a")).toBe(false);
    expect(isMeaningfulVoiceTranscript("camera status")).toBe(true);
  });

  it("restarts Web Speech after onend only while the listening timer is active", () => {
    expect(shouldRestartSpeechRecognition({
      sessionActive: true,
      phase: "listening",
      transcriptSubmitted: false,
      now: 1_000,
      deadline: 61_000,
    })).toBe(true);
    expect(shouldRestartSpeechRecognition({
      sessionActive: true,
      phase: "processing",
      transcriptSubmitted: false,
      now: 1_000,
      deadline: 61_000,
    })).toBe(false);
    expect(shouldRestartSpeechRecognition({
      sessionActive: true,
      phase: "listening",
      transcriptSubmitted: false,
      now: 61_000,
      deadline: 61_000,
    })).toBe(false);
  });
});
