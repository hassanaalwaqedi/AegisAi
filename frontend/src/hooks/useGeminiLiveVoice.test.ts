import { afterEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";

import {
  NativePcmPlayer,
  PcmFrameBatcher,
  nextBargeInActivityFrame,
  isMeaningfulVoiceTranscript,
  resampleMonoToPcm16,
  shouldRestartSpeechRecognition,
  useGeminiLiveVoice,
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
  static instances: MockAudioContext[] = [];
  static close = vi.fn(async () => undefined);
  state = "running";
  currentTime = 0;
  destination = {} as AudioDestinationNode;
  resume = vi.fn(async () => undefined);
  close = MockAudioContext.close;
  createAnalyser = vi.fn(() => ({ fftSize: 0, connect: vi.fn(), getByteTimeDomainData: (samples: Uint8Array) => samples.fill(128) }));
  createBuffer = vi.fn((_channels: number, length: number, sampleRate: number) => ({ duration: length / sampleRate, copyToChannel: vi.fn() }));
  createBufferSource = vi.fn(() => new MockSource());

  constructor() {
    MockAudioContext.instances.push(this);
  }
}

afterEach(() => {
  MockAudioContext.instances = [];
  MockAudioContext.close.mockClear();
  vi.useRealTimers();
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

  it("keeps streamed PCM chunks contiguous on one buffered timeline", async () => {
    vi.stubGlobal("AudioContext", MockAudioContext);
    vi.stubGlobal("requestAnimationFrame", () => 1);
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
    const player = new NativePcmPlayer({ onLevel: vi.fn(), onStarted: vi.fn(), onIdle: vi.fn() });

    await Promise.all([
      player.playPcm(new Int16Array(2_400).buffer, 24_000),
      player.playPcm(new Int16Array(2_400).buffer, 24_000),
    ]);

    const context = MockAudioContext.instances[0];
    const first = context.createBufferSource.mock.results[0]?.value as MockSource;
    const second = context.createBufferSource.mock.results[1]?.value as MockSource;
    expect(first.start).toHaveBeenCalledWith(0.45);
    expect(second.start.mock.calls[0]?.[0]).toBeCloseTo(0.55);
    expect(player.isPlaying).toBe(true);
  });

  it("recovers a brief underrun without inserting the full initial buffer again", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("AudioContext", MockAudioContext);
    vi.stubGlobal("requestAnimationFrame", () => 1);
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
    const player = new NativePcmPlayer({ onLevel: vi.fn(), onStarted: vi.fn(), onIdle: vi.fn() });

    await player.playPcm(new Int16Array(2_400).buffer, 24_000);
    const context = MockAudioContext.instances[0];
    const first = context.createBufferSource.mock.results[0]?.value as MockSource;
    context.currentTime = 0.56;
    first.onended?.();

    await player.playPcm(new Int16Array(2_400).buffer, 24_000);
    const second = context.createBufferSource.mock.results[1]?.value as MockSource;
    expect(second.start.mock.calls[0]?.[0]).toBeCloseTo(0.58);
  });

  it("does not declare a managed stream idle during a temporary chunk gap", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("AudioContext", MockAudioContext);
    vi.stubGlobal("requestAnimationFrame", () => 1);
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
    const idle = vi.fn();
    const player = new NativePcmPlayer({ onLevel: vi.fn(), onStarted: vi.fn(), onIdle: idle });
    player.beginStream();

    await player.playPcm(new Int16Array(2_400).buffer, 24_000);
    const context = MockAudioContext.instances[0];
    const first = context.createBufferSource.mock.results[0]?.value as MockSource;
    first.onended?.();
    vi.advanceTimersByTime(500);
    expect(idle).not.toHaveBeenCalled();

    player.endStream();
    vi.advanceTimersByTime(180);
    expect(idle).toHaveBeenCalledOnce();
  });

  it("does not report idle while another PCM frame is pending or queued", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("AudioContext", MockAudioContext);
    vi.stubGlobal("requestAnimationFrame", () => 1);
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
    const idle = vi.fn();
    const player = new NativePcmPlayer({ onLevel: vi.fn(), onStarted: vi.fn(), onIdle: idle });

    await Promise.all([
      player.playPcm(new Int16Array(2_400).buffer, 24_000),
      player.playPcm(new Int16Array(2_400).buffer, 24_000),
    ]);
    const context = MockAudioContext.instances[0];
    const first = context.createBufferSource.mock.results[0]?.value as MockSource;
    const second = context.createBufferSource.mock.results[1]?.value as MockSource;

    first.onended?.();
    vi.advanceTimersByTime(200);
    expect(idle).not.toHaveBeenCalled();

    second.onended?.();
    vi.advanceTimersByTime(179);
    expect(idle).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(idle).toHaveBeenCalledOnce();
    vi.useRealTimers();
  });

  it("invalidates queued PCM immediately when playback is cancelled", async () => {
    let releaseResume!: () => void;
    const resumePending = new Promise<undefined>((resolve) => {
      releaseResume = () => resolve(undefined);
    });
    class SuspendedAudioContext extends MockAudioContext {
      state = "suspended";
      resume = vi.fn(() => resumePending);
    }
    vi.stubGlobal("AudioContext", SuspendedAudioContext);
    vi.stubGlobal("requestAnimationFrame", () => 1);
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
    const idle = vi.fn();
    const player = new NativePcmPlayer({ onLevel: vi.fn(), onStarted: vi.fn(), onIdle: idle });

    const pendingPlayback = player.playPcm(new Int16Array(2_400).buffer, 24_000);
    expect(player.isPlaying).toBe(true);
    expect(player.stop()).toBe(true);
    expect(player.isPlaying).toBe(false);
    releaseResume();

    await expect(pendingPlayback).resolves.toBe(false);
    expect(player.isPlaying).toBe(false);
  });
});

describe("PcmFrameBatcher", () => {
  it("coalesces small consecutive PCM frames without changing sample order", () => {
    vi.useFakeTimers();
    const onBatch = vi.fn();
    const batcher = new PcmFrameBatcher(onBatch);
    batcher.enqueue(new Int16Array(1_200).fill(11).buffer, 24_000);
    expect(onBatch).not.toHaveBeenCalled();
    batcher.enqueue(new Int16Array(1_200).fill(22).buffer, 24_000);

    expect(onBatch).toHaveBeenCalledOnce();
    const [combined, rate] = onBatch.mock.calls[0] as [ArrayBuffer, number];
    const samples = new Int16Array(combined);
    expect(rate).toBe(24_000);
    expect(samples).toHaveLength(2_400);
    expect(samples[1_199]).toBe(11);
    expect(samples[1_200]).toBe(22);
  });

  it("flushes a short final frame instead of dropping the end of a sentence", () => {
    const onBatch = vi.fn();
    const batcher = new PcmFrameBatcher(onBatch);
    batcher.enqueue(new Int16Array(240).fill(7).buffer, 24_000);

    expect(batcher.flush()).toBe(true);
    expect(onBatch).toHaveBeenCalledOnce();
    expect(new Int16Array(onBatch.mock.calls[0]?.[0] as ArrayBuffer)).toHaveLength(240);
  });
});

describe("native microphone input", () => {
  it("resamples one mono microphone channel to signed 16-bit Gemini PCM", () => {
    const pcm = resampleMonoToPcm16(new Float32Array([-1, -0.5, 0, 0.5, 1]), 16_000);

    expect(Array.from(new Int16Array(pcm))).toEqual([-32768, -16384, 0, 16384, 32767]);
  });
});

describe("click-to-listen session guards", () => {
  it("keeps the audible-alert stop callback stable across playback renders", () => {
    const { result, rerender } = renderHook(() => useGeminiLiveVoice());
    const initialCallback = result.current.stopAudibleRiskAlert;

    rerender();

    expect(result.current.stopAudibleRiskAlert).toBe(initialCallback);
  });

  it("preserves the user-authorized alert AudioContext across a normal stop", async () => {
    vi.stubGlobal("AudioContext", MockAudioContext);
    vi.stubGlobal("requestAnimationFrame", () => 1);
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
    const { result, unmount } = renderHook(() => useGeminiLiveVoice());

    await act(async () => {
      expect(await result.current.prepareAudibleAlertAudio()).toBe(true);
    });
    expect(MockAudioContext.instances).toHaveLength(1);

    act(() => result.current.stopAudibleRiskAlert());
    expect(MockAudioContext.close).not.toHaveBeenCalled();

    await act(async () => {
      expect(await result.current.prepareAudibleAlertAudio()).toBe(true);
    });
    expect(MockAudioContext.instances).toHaveLength(1);
    unmount();
  });

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
