"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  browserVoiceEnvelope,
  closeLiveSession,
  createLiveSession,
  liveWebSocketUrl,
  serverVoiceEnvelopeSchema,
  type LiveCitation,
  type LiveSession,
  type AegisVoiceSessionState,
  type SafeUICommand,
  type VoiceState,
  type WakeWordMode,
} from "@/lib/live-voice";

type CaptureMode = "native-audio" | "speech-recognition" | null;

export type VoiceSessionPhase = "idle" | "activating" | "standby" | "wake_detected" | "listening" | "end_of_speech" | "processing" | "response" | "follow_up" | "muted";
export type VoiceSessionOutcome = "cancelled" | "timeout" | null;
export type AudibleAlertPlaybackResult = "spoken" | "unavailable" | "busy";

function configuredMilliseconds(value: string | undefined, fallback: number, min: number, max: number) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.min(max, Math.max(min, Math.round(parsed))) : fallback;
}

/** One source of truth for all hands-free timing and VAD thresholds. */
export const AEGIS_VOICE_SESSION_CONFIG = {
  followUpWindowMs: configuredMilliseconds(process.env.NEXT_PUBLIC_AEGIS_VOICE_FOLLOW_UP_MS, 20_000, 15_000, 30_000),
  gatewayReadyTimeoutMs: configuredMilliseconds(process.env.NEXT_PUBLIC_AEGIS_VOICE_GATEWAY_READY_TIMEOUT_MS, 8_000, 4_000, 20_000),
  responseTimeoutMs: configuredMilliseconds(process.env.NEXT_PUBLIC_AEGIS_VOICE_RESPONSE_TIMEOUT_MS, 25_000, 8_000, 60_000),
  gatewayReconnectDelayMs: 300,
  maxGatewayReconnectAttempts: 1,
  vadSpeechStartLevel: 0.018,
  vadSpeechEndLevel: 0.011,
  vadStartFrames: 2,
  vadEndFrames: 12,
  recognitionRestartDelayMs: 200,
} as const;

/** Compatibility export for callers that previously named this an idle timeout. */
export const VOICE_CONVERSATION_IDLE_TIMEOUT_MS = AEGIS_VOICE_SESSION_CONFIG.followUpWindowMs;
export const VOICE_FOLLOW_UP_WINDOW_MS = AEGIS_VOICE_SESSION_CONFIG.followUpWindowMs;

/** Returns the command portion only when a standalone wake phrase was heard. */
export function wakePhraseCommand(text: string): string | null {
  const match = text.match(/^\s*(?:hey\s+)?aegis\b[\s,.:;!\-]*/i);
  return match ? text.slice(match[0].length).trim() : null;
}

type BrowserSpeechRecognitionResult = {
  isFinal: boolean;
  0: { transcript: string };
};

type BrowserSpeechRecognitionEvent = Event & {
  resultIndex: number;
  results: ArrayLike<BrowserSpeechRecognitionResult>;
};

type BrowserSpeechRecognitionErrorEvent = Event & { error: string };

type BrowserSpeechRecognition = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onstart: (() => void) | null;
  onend: (() => void) | null;
  onerror: ((event: BrowserSpeechRecognitionErrorEvent) => void) | null;
  onresult: ((event: BrowserSpeechRecognitionEvent) => void) | null;
  start: () => void;
  abort: () => void;
};

type BrowserSpeechRecognitionConstructor = new () => BrowserSpeechRecognition;

function browserSpeechRecognitionConstructor(): BrowserSpeechRecognitionConstructor | null {
  if (typeof window === "undefined") return null;
  const browserWindow = window as typeof window & {
    SpeechRecognition?: BrowserSpeechRecognitionConstructor;
    webkitSpeechRecognition?: BrowserSpeechRecognitionConstructor;
  };
  return browserWindow.SpeechRecognition ?? browserWindow.webkitSpeechRecognition ?? null;
}

/** A final result must contain more than whitespace before Aegis receives it. */
export function isMeaningfulVoiceTranscript(text: string) {
  return text.trim().length > 1;
}

/** Web Speech routinely emits onend after a pause; that is not a disconnect. */
export function shouldRestartSpeechRecognition({
  sessionActive,
  phase,
  transcriptSubmitted,
  now,
  deadline,
}: {
  sessionActive: boolean;
  phase: VoiceSessionPhase;
  transcriptSubmitted: boolean;
  now: number;
  deadline: number;
}) {
  return sessionActive && phase === "listening" && !transcriptSubmitted && now < deadline;
}

type VoiceCallbacks = {
  sceneContext?: string;
  onProjection?: (execution: import("@/lib/operator-api").OperatorExecution) => void;
  onTurnComplete?: () => void;
  onTranscript?: (entry: { speaker: "operator" | "aegis"; text: string; isFinal: boolean }) => void;
  onCitations?: (citations: LiveCitation[]) => void;
  onUiCommand?: (command: SafeUICommand) => void;
  onToolActivity?: (activity: { tool: string; status: "calling" | "completed" | "failed"; turnId?: string | null }) => void;
};

// Hands-free capture keeps sending PCM while the operator is silent so Gemini
// can detect a completed utterance. That silence must never cancel Aegis's
// own output. A few consecutive elevated capture blocks are required before
// we treat input as a real barge-in rather than microphone floor noise.
const BARGE_IN_LEVEL = 0.035;
const BARGE_IN_REQUIRED_FRAMES = 4;

export function nextBargeInActivityFrame(previousFrames: number, level: number) {
  return level >= BARGE_IN_LEVEL ? previousFrames + 1 : 0;
}

function pcmBufferToBase64(buffer: ArrayBuffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  const chunkSize = 0x8000;
  for (let index = 0; index < bytes.length; index += chunkSize) {
    binary += String.fromCharCode(...Array.from(bytes.subarray(index, index + chunkSize)));
  }
  return btoa(binary);
}

function pcmToFloat(buffer: ArrayBuffer) {
  const pcm = new Int16Array(buffer.slice(0));
  const floats = new Float32Array(pcm.length);
  for (let index = 0; index < pcm.length; index += 1) floats[index] = pcm[index] / (pcm[index] < 0 ? 0x8000 : 0x7fff);
  return floats;
}

type PcmPlayerCallbacks = {
  onLevel: (level: number) => void;
  onStarted: () => void;
  onIdle: () => void;
};

// Gemini PCM arrives as a sequence of small WebSocket frames. Keeping a short
// lead time lets the browser schedule those frames on one continuous audio
// timeline instead of exposing normal network jitter as missing syllables.
const PCM_INITIAL_BUFFER_SECONDS = 0.45;
const PCM_UNDERRUN_RECOVERY_SECONDS = 0.02;
const PCM_IDLE_GRACE_MS = 180;
const PCM_BATCH_WINDOW_MS = 24;
const PCM_BATCH_TARGET_SECONDS = 0.1;
const GEMINI_INPUT_SAMPLE_RATE = 16_000;
const MAX_QUEUED_INPUT_AUDIO_BYTES = GEMINI_INPUT_SAMPLE_RATE * Int16Array.BYTES_PER_ELEMENT * 2;

/** Convert one microphone channel to Gemini Live's signed-16-bit 16 kHz PCM. */
export function resampleMonoToPcm16(input: Float32Array, inputSampleRate: number, outputSampleRate = GEMINI_INPUT_SAMPLE_RATE) {
  if (input.length === 0 || inputSampleRate <= 0 || outputSampleRate <= 0) return new ArrayBuffer(0);
  const ratio = inputSampleRate / outputSampleRate;
  const output = new Int16Array(Math.max(1, Math.round(input.length / ratio)));
  for (let index = 0; index < output.length; index += 1) {
    const start = Math.floor(index * ratio);
    const end = Math.min(input.length, Math.max(start + 1, Math.floor((index + 1) * ratio)));
    let total = 0;
    for (let sample = start; sample < end; sample += 1) total += input[sample] ?? 0;
    const value = total / Math.max(1, end - start);
    output[index] = Math.max(-1, Math.min(1, value)) < 0
      ? Math.round(Math.max(-1, value) * 0x8000)
      : Math.round(Math.min(1, value) * 0x7fff);
  }
  return output.buffer;
}

/** Coalesces tiny adjacent PCM frames before they reach Web Audio. */
export class PcmFrameBatcher {
  constructor(private onBatch: (buffer: ArrayBuffer, sampleRate: number) => void = () => undefined) {}

  private chunks: ArrayBuffer[] = [];
  private totalBytes = 0;
  private sampleRate = 0;
  private flushTimer: ReturnType<typeof setTimeout> | null = null;

  setOnBatch(onBatch: (buffer: ArrayBuffer, sampleRate: number) => void) {
    this.onBatch = onBatch;
  }

  enqueue(chunk: ArrayBuffer, sampleRate: number) {
    if (chunk.byteLength === 0) return;
    if (this.sampleRate && this.sampleRate !== sampleRate) this.flush();
    this.sampleRate = sampleRate;
    this.chunks.push(chunk);
    this.totalBytes += chunk.byteLength;
    const queuedSeconds = this.totalBytes / (sampleRate * Int16Array.BYTES_PER_ELEMENT);
    if (queuedSeconds >= PCM_BATCH_TARGET_SECONDS) {
      this.flush();
      return;
    }
    if (this.flushTimer === null) this.flushTimer = setTimeout(() => this.flush(), PCM_BATCH_WINDOW_MS);
  }

  flush() {
    if (this.flushTimer !== null) clearTimeout(this.flushTimer);
    this.flushTimer = null;
    if (this.chunks.length === 0 || !this.sampleRate) return false;
    const combined = new Uint8Array(this.totalBytes);
    let offset = 0;
    for (const chunk of this.chunks) {
      combined.set(new Uint8Array(chunk), offset);
      offset += chunk.byteLength;
    }
    const sampleRate = this.sampleRate;
    this.chunks = [];
    this.totalBytes = 0;
    this.sampleRate = 0;
    this.onBatch(combined.buffer, sampleRate);
    return true;
  }

  clear() {
    if (this.flushTimer !== null) clearTimeout(this.flushTimer);
    this.flushTimer = null;
    this.chunks = [];
    this.totalBytes = 0;
    this.sampleRate = 0;
  }
}

/** Queues signed 16-bit mono native Gemini PCM without browser TTS. */
export class NativePcmPlayer {
  constructor(private readonly callbacks: PcmPlayerCallbacks) {}

  private context?: AudioContext;
  private analyser?: AnalyserNode;
  private levelFrame = 0;
  private nextStartAt = 0;
  private sources = new Set<AudioBufferSourceNode>();
  private pendingSchedules = 0;
  private playbackGeneration = 0;
  private scheduleTail: Promise<void> = Promise.resolve();
  private idleTimer: ReturnType<typeof setTimeout> | null = null;
  private hasScheduledAudio = false;
  private streamBoundaryManaged = false;
  private streamComplete = false;

  get isPlaying() {
    return this.sources.size > 0 || this.pendingSchedules > 0;
  }

  async prepare() {
    if (!this.context) this.context = new AudioContext();
    if (this.context.state === "suspended") await this.context.resume();
    if (!this.analyser) {
      this.analyser = this.context.createAnalyser();
      this.analyser.fftSize = 256;
      this.analyser.connect(this.context.destination);
    }
  }

  private startLevelMonitor() {
    if (this.levelFrame || !this.analyser) return;
    const samples = new Uint8Array(this.analyser.fftSize);
    const measure = () => {
      if (!this.analyser) return;
      this.analyser.getByteTimeDomainData(samples);
      let energy = 0;
      for (let index = 0; index < samples.length; index += 1) {
        const sample = samples[index];
        const normalized = (sample - 128) / 128;
        energy += normalized * normalized;
      }
      this.callbacks.onLevel(Math.min(1, Math.sqrt(energy / samples.length) * 3));
      this.levelFrame = requestAnimationFrame(measure);
    };
    measure();
  }

  private stopLevelMonitor() {
    if (this.levelFrame) cancelAnimationFrame(this.levelFrame);
    this.levelFrame = 0;
    this.callbacks.onLevel(0);
  }

  private cancelIdleNotification() {
    if (this.idleTimer !== null) clearTimeout(this.idleTimer);
    this.idleTimer = null;
  }

  /** Begin one provider response so a transient underrun cannot look idle. */
  beginStream() {
    this.cancelIdleNotification();
    this.streamBoundaryManaged = true;
    this.streamComplete = false;
    if (!this.isPlaying) {
      this.nextStartAt = 0;
      this.hasScheduledAudio = false;
    }
  }

  /** Mark that all PCM frames for the current provider response arrived. */
  endStream() {
    this.streamComplete = true;
    this.notifyIdleWhenDrained();
  }

  private notifyIdleWhenDrained() {
    if (this.sources.size > 0 || this.pendingSchedules > 0 || this.idleTimer !== null) return;
    if (this.streamBoundaryManaged && !this.streamComplete) return;
    this.idleTimer = setTimeout(() => {
      this.idleTimer = null;
      if (this.sources.size > 0 || this.pendingSchedules > 0) return;
      if (this.streamBoundaryManaged && !this.streamComplete) return;
      this.nextStartAt = 0;
      this.hasScheduledAudio = false;
      this.streamBoundaryManaged = false;
      this.streamComplete = false;
      this.stopLevelMonitor();
      this.callbacks.onIdle();
    }, PCM_IDLE_GRACE_MS);
  }

  playPcm(pcmBuffer: ArrayBuffer, sampleRate: number) {
    if (pcmBuffer.byteLength % Int16Array.BYTES_PER_ELEMENT !== 0) {
      return Promise.reject(new Error("Native PCM audio frame is not 16-bit aligned."));
    }
    const generation = this.playbackGeneration;
    this.pendingSchedules += 1;
    this.cancelIdleNotification();

    let resolvePlayback!: (played: boolean) => void;
    let rejectPlayback!: (reason?: unknown) => void;
    const result = new Promise<boolean>((resolve, reject) => {
      resolvePlayback = resolve;
      rejectPlayback = reject;
    });

    const schedule = async () => {
      try {
        await this.prepare();
        if (generation !== this.playbackGeneration) {
          resolvePlayback(false);
          return;
        }
        const context = this.context;
        if (!context || !this.analyser) throw new Error("Native audio output is not ready.");
        const samples = pcmToFloat(pcmBuffer);
        if (samples.length === 0) {
          resolvePlayback(false);
          return;
        }
        const buffer = context.createBuffer(1, samples.length, sampleRate);
        buffer.copyToChannel(samples, 0);
        const source = context.createBufferSource();
        source.buffer = buffer;
        source.connect(this.analyser);
        source.onended = () => {
          this.sources.delete(source);
          this.notifyIdleWhenDrained();
        };

        // Once playback has a future timeline, every chunk starts exactly at
        // the preceding chunk's end. A genuine underrun gets only a small
        // scheduling lead; applying the full initial buffer again makes a
        // tiny network gap sound like a conspicuous cut.
        const startAt = this.nextStartAt > context.currentTime
          ? this.nextStartAt
          : context.currentTime + (this.hasScheduledAudio ? PCM_UNDERRUN_RECOVERY_SECONDS : PCM_INITIAL_BUFFER_SECONDS);
        source.start(startAt);
        this.nextStartAt = startAt + buffer.duration;
        this.hasScheduledAudio = true;
        const wasIdle = this.sources.size === 0;
        this.sources.add(source);
        this.startLevelMonitor();
        if (wasIdle) this.callbacks.onStarted();
        resolvePlayback(true);
      } catch (error) {
        rejectPlayback(error);
      } finally {
        if (generation === this.playbackGeneration) {
          this.pendingSchedules = Math.max(0, this.pendingSchedules - 1);
          this.notifyIdleWhenDrained();
        }
      }
    };

    // Serializing schedule work preserves WebSocket frame order even when
    // AudioContext.resume() or Blob conversion resolves asynchronously.
    this.scheduleTail = this.scheduleTail.then(schedule, schedule);
    return result;
  }

  stop() {
    const wasPlaying = this.isPlaying;
    this.playbackGeneration += 1;
    this.pendingSchedules = 0;
    this.cancelIdleNotification();
    this.sources.forEach((source) => {
      try {
        source.onended = null;
        source.stop();
      } catch {
        // A source that already ended has no work left to do.
      }
    });
    this.sources.clear();
    this.nextStartAt = 0;
    this.hasScheduledAudio = false;
    this.streamBoundaryManaged = false;
    this.streamComplete = false;
    this.stopLevelMonitor();
    if (wasPlaying) this.callbacks.onIdle();
    return wasPlaying;
  }

  async close() {
    this.stop();
    if (this.context) {
      await this.context.close().catch(() => undefined);
      this.context = undefined;
      this.analyser = undefined;
    }
  }
}

export function voiceStateLabel(state: VoiceState) {
  return {
    off: "Ready",
    connecting: "Connecting",
    ready: "Ready",
    listening: "Listening",
    thinking: "Thinking",
    speaking: "Aegis speaking",
    error: "Connection error"
  }[state];
}

/**
 * An activated operator voice session. Native 16 kHz microphone PCM is sent
 * through the authenticated Gemini Live gateway only while local VAD detects
 * speech. Browser recognition may gate wake detection before a Live session;
 * the browser's own provider policy applies to that recognizer. First-use
 * activation is a user gesture, and mute/deactivation release microphone use.
 */
export function useGeminiLiveVoice(callbacks: VoiceCallbacks = {}) {
  const [state, setState] = useState<VoiceState>("off");
  const [error, setError] = useState<string | null>(null);
  const [waveformLevel, setWaveformLevel] = useState(0);
  const [playbackLevel, setPlaybackLevel] = useState(0);
  const [captureMode, setCaptureMode] = useState<CaptureMode>(null);
  const [isCapturing, setIsCapturing] = useState(false);
  const [sessionPhase, setSessionPhase] = useState<VoiceSessionPhase>("idle");
  const [voiceSessionState, setVoiceSessionState] = useState<AegisVoiceSessionState>("DISABLED");
  const [isActivated, setIsActivated] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [isUserSpeaking, setIsUserSpeaking] = useState(false);
  const [wakeWordMode, setWakeWordMode] = useState<WakeWordMode>("unavailable");
  const [sessionOutcome, setSessionOutcome] = useState<VoiceSessionOutcome>(null);
  const [sessionSecondsRemaining, setSessionSecondsRemaining] = useState(0);
  const [sessionActive, setSessionActive] = useState(false);
  const socketRef = useRef<WebSocket | null>(null);
  const sessionRef = useRef<LiveSession | null>(null);
  // Audible alerts use the same authenticated Gemini Live gateway and native
  // PCM player as conversational responses, but never open the microphone.
  // Keeping the lifecycles separate avoids an alert competing with an active
  // operator conversation or creating duplicate browser audio contexts.
  const audibleAlertSocketRef = useRef<WebSocket | null>(null);
  const audibleAlertSessionRef = useRef<LiveSession | null>(null);
  const audibleAlertOpeningRef = useRef(false);
  const audibleAlertPreparedRef = useRef(false);
  const audibleAlertOutputSampleRateRef = useRef(24_000);
  const audibleAlertDrainTimerRef = useRef<number | null>(null);
  const recognitionRef = useRef<BrowserSpeechRecognition | null>(null);
  const wakeRecognitionRef = useRef<BrowserSpeechRecognition | null>(null);
  const wakeRecognitionStartingRef = useRef(false);
  const wakeRecognitionRestartTimerRef = useRef<number | null>(null);
  const inputAudioContextRef = useRef<AudioContext | null>(null);
  const inputMediaStreamRef = useRef<MediaStream | null>(null);
  const inputSourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const inputProcessorRef = useRef<ScriptProcessorNode | null>(null);
  const inputSinkRef = useRef<GainNode | null>(null);
  const nativeInputActiveRef = useRef(false);
  const nativeTransmissionActiveRef = useRef(false);
  const nativeSpeechFramesRef = useRef(0);
  const nativeSilenceFramesRef = useRef(0);
  const waveformLevelRef = useRef(0);
  const pendingInputAudioRef = useRef<ArrayBuffer[]>([]);
  const pendingInputAudioBytesRef = useRef(0);
  const pendingAudioEndRef = useRef(false);
  const beginSpeechRecognitionRef = useRef<(epoch: number) => void>(() => undefined);
  const recognitionRestartTimerRef = useRef<number | null>(null);
  const recognitionStartingRef = useRef(false);
  const intentionalRecognitionStopRef = useRef(false);
  const sessionActiveRef = useRef(false);
  const sessionEpochRef = useRef(0);
  const sessionDeadlineRef = useRef(0);
  const sessionPhaseRef = useRef<VoiceSessionPhase>("idle");
  const sessionTimerRef = useRef<number | null>(null);
  const gatewayReadyTimerRef = useRef<number | null>(null);
  const responseTimerRef = useRef<number | null>(null);
  const connectionOpeningRef = useRef(false);
  const gatewayReadyRef = useRef(false);
  const pendingTranscriptRef = useRef<string | null>(null);
  const submittedTranscriptRef = useRef(false);
  const lastSubmittedTranscriptRef = useRef<string | null>(null);
  const responseCompleteRef = useRef(false);
  const nativeAudioQueuedRef = useRef(false);
  const nativeAudioPlaybackStartedRef = useRef(false);
  const outputSampleRateRef = useRef(24_000);
  const manuallyStoppedRef = useRef(false);
  const activatedRef = useRef(false);
  const mutedRef = useRef(false);
  const beginWakeDetectionRef = useRef<() => void>(() => undefined);
  const beginConversationRef = useRef<(initialTranscript?: string) => Promise<void>>(() => Promise.resolve());
  const openLiveConnectionRef = useRef<(epoch: number, attempt?: number) => void>(() => undefined);
  // Audio analysers sample at the display refresh rate. Keep the raw value in
  // a ref and publish only meaningful changes so a playback meter cannot
  // trigger a React render loop while native audio is playing.
  const playbackLevelRef = useRef(0);
  const finishSessionRef = useRef<(outcome?: VoiceSessionOutcome, message?: string | null) => void>(() => undefined);
  const resumeListeningRef = useRef<() => void>(() => undefined);
  const onPlayerLevel = useCallback((level: number) => {
    const next = Math.round(Math.min(1, Math.max(0, level)) * 20) / 20;
    if (Math.abs(playbackLevelRef.current - next) < 0.05) return;
    playbackLevelRef.current = next;
    setPlaybackLevel(next);
  }, []);
  const setPhase = useCallback((phase: VoiceSessionPhase) => {
    sessionPhaseRef.current = phase;
    setSessionPhase(phase);
  }, []);
  const onPlayerStarted = useCallback(() => {
    if (!sessionActiveRef.current) return;
    nativeAudioPlaybackStartedRef.current = true;
    setPhase("response");
    setVoiceSessionState("SPEAKING");
    setState("speaking");
  }, [setPhase]);
  const onPlayerIdle = useCallback(() => {
    if (sessionActiveRef.current && responseCompleteRef.current) resumeListeningRef.current();
  }, []);
  // The player is intentionally created once. Its callbacks run only from
  // browser audio events, after render, and use refs to read the latest turn.
  // eslint-disable-next-line react-hooks/refs
  const [player] = useState(() => new NativePcmPlayer({
      onLevel: onPlayerLevel,
      onStarted: onPlayerStarted,
      onIdle: onPlayerIdle,
    }));
  // Risk-alert audio has an independent lifecycle. Sharing this player with
  // conversational output allowed alert cleanup to stop an Aegis response.
  const [audibleAlertPlayer] = useState(() => new NativePcmPlayer({
    onLevel: () => undefined,
    onStarted: () => undefined,
    onIdle: () => undefined,
  }));
  const [conversationAudioBatcher] = useState(() => new PcmFrameBatcher());
  const callbacksRef = useRef(callbacks);
  useEffect(() => {
    if (callbacks.sceneContext && gatewayReadyRef.current && socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify({ version: "1.0", type: "scene_context", data: callbacks.sceneContext }));
    }
  }, [callbacks.sceneContext]);

  useEffect(() => {
    conversationAudioBatcher.setOnBatch((chunk, sampleRate) => {
      if (!sessionActiveRef.current) return;
      void player.playPcm(chunk, sampleRate).catch(() => {
        finishSessionRef.current(null, "Aegis native audio playback is unavailable in this browser.");
      });
    });
    return () => conversationAudioBatcher.clear();
  }, [conversationAudioBatcher, player]);

  useEffect(() => {
    callbacksRef.current = callbacks;
  }, [callbacks]);

  const closeAudibleAlert = useCallback((stopPlayback = false) => {
    if (audibleAlertDrainTimerRef.current !== null) {
      window.clearTimeout(audibleAlertDrainTimerRef.current);
      audibleAlertDrainTimerRef.current = null;
    }
    const socket = audibleAlertSocketRef.current;
    const session = audibleAlertSessionRef.current;
    audibleAlertSocketRef.current = null;
    audibleAlertSessionRef.current = null;
    audibleAlertOpeningRef.current = false;
    if (stopPlayback) audibleAlertPlayer.stop();
    if (socket?.readyState === WebSocket.OPEN) socket.send(browserVoiceEnvelope("stop"));
    if (socket) {
      socket.onclose = null;
      socket.onerror = null;
      socket.close(1000, "audible alert ended");
    }
    if (session) void closeLiveSession(session.sessionId);
  }, [audibleAlertPlayer]);

  // This callback is passed into useAudibleRiskAlerts, whose effect cleanup
  // depends on referential stability. A fresh wrapper on every render caused
  // cleanup to run during playback and repeatedly stop the audio player.
  const stopAudibleRiskAlert = useCallback(() => {
    closeAudibleAlert(true);
  }, [closeAudibleAlert]);

  const send = useCallback((type: "audio" | "text" | "audio_end" | "interrupt" | "stop" | "ping", data?: string, mimeType?: string) => {
    const socket = socketRef.current;
    if (socket?.readyState === WebSocket.OPEN) socket.send(browserVoiceEnvelope(type, data, mimeType));
  }, []);

  const queueOrSendAudioEnd = useCallback(() => {
    if (!sessionActiveRef.current) return;
    const socket = socketRef.current;
    if (gatewayReadyRef.current && socket?.readyState === WebSocket.OPEN) {
      socket.send(browserVoiceEnvelope("audio_end"));
      return;
    }
    // A user can finish speaking during the short gateway handshake. Preserve
    // that turn boundary beside queued PCM so Gemini does not wait forever.
    pendingAudioEndRef.current = true;
  }, []);

  const queueOrSendInputAudio = useCallback((pcm: ArrayBuffer) => {
    if (!sessionActiveRef.current || pcm.byteLength === 0) return;
    const socket = socketRef.current;
    if (gatewayReadyRef.current && socket?.readyState === WebSocket.OPEN) {
      socket.send(browserVoiceEnvelope("audio", pcmBufferToBase64(pcm), `audio/pcm;rate=${GEMINI_INPUT_SAMPLE_RATE}`));
      return;
    }

    pendingInputAudioRef.current.push(pcm);
    pendingInputAudioBytesRef.current += pcm.byteLength;
    while (pendingInputAudioBytesRef.current > MAX_QUEUED_INPUT_AUDIO_BYTES) {
      const discarded = pendingInputAudioRef.current.shift();
      pendingInputAudioBytesRef.current -= discarded?.byteLength ?? 0;
    }
  }, []);

  const flushPendingInputAudio = useCallback(() => {
    const socket = socketRef.current;
    if (!gatewayReadyRef.current || socket?.readyState !== WebSocket.OPEN || !sessionActiveRef.current) return;
    for (const pcm of pendingInputAudioRef.current) {
      socket.send(browserVoiceEnvelope("audio", pcmBufferToBase64(pcm), `audio/pcm;rate=${GEMINI_INPUT_SAMPLE_RATE}`));
    }
    pendingInputAudioRef.current = [];
    pendingInputAudioBytesRef.current = 0;
    if (pendingAudioEndRef.current) {
      pendingAudioEndRef.current = false;
      socket.send(browserVoiceEnvelope("audio_end"));
    }
  }, []);

  const pauseConversationInactivityTimer = useCallback(() => {
    if (sessionTimerRef.current !== null) window.clearInterval(sessionTimerRef.current);
    sessionTimerRef.current = null;
    setSessionSecondsRemaining(0);
  }, []);

  const clearGatewayReadyTimer = useCallback(() => {
    if (gatewayReadyTimerRef.current !== null) window.clearTimeout(gatewayReadyTimerRef.current);
    gatewayReadyTimerRef.current = null;
  }, []);

  const clearResponseTimer = useCallback(() => {
    if (responseTimerRef.current !== null) window.clearTimeout(responseTimerRef.current);
    responseTimerRef.current = null;
  }, []);

  const armResponseTimeout = useCallback(() => {
    clearResponseTimer();
    responseTimerRef.current = window.setTimeout(() => {
      if (!sessionActiveRef.current || responseCompleteRef.current) return;
      finishSessionRef.current(null, "Aegis did not receive a voice response in time. Tap Talk to Aegis to reconnect.");
    }, AEGIS_VOICE_SESSION_CONFIG.responseTimeoutMs);
  }, [clearResponseTimer]);

  const clearSessionTimers = useCallback(() => {
    pauseConversationInactivityTimer();
    clearGatewayReadyTimer();
    clearResponseTimer();
    if (recognitionRestartTimerRef.current !== null) window.clearTimeout(recognitionRestartTimerRef.current);
    recognitionRestartTimerRef.current = null;
  }, [clearGatewayReadyTimer, clearResponseTimer, pauseConversationInactivityTimer]);

  const stopNativeAudioCapture = useCallback(() => {
    nativeInputActiveRef.current = false;
    nativeTransmissionActiveRef.current = false;
    nativeSpeechFramesRef.current = 0;
    nativeSilenceFramesRef.current = 0;
    waveformLevelRef.current = 0;
    setIsUserSpeaking(false);
    setWaveformLevel(0);
    pendingInputAudioRef.current = [];
    pendingInputAudioBytesRef.current = 0;
    const processor = inputProcessorRef.current;
    inputProcessorRef.current = null;
    if (processor) {
      processor.onaudioprocess = null;
      processor.disconnect();
    }
    inputSourceRef.current?.disconnect();
    inputSourceRef.current = null;
    inputSinkRef.current?.disconnect();
    inputSinkRef.current = null;
    inputMediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    inputMediaStreamRef.current = null;
    const context = inputAudioContextRef.current;
    inputAudioContextRef.current = null;
    if (context && context.state !== "closed") void context.close();
  }, []);

  const stopRecognition = useCallback(() => {
    const recognition = recognitionRef.current;
    recognitionRef.current = null;
    recognitionStartingRef.current = false;
    intentionalRecognitionStopRef.current = true;
    if (recognition) {
      recognition.onend = null;
      recognition.onerror = null;
      recognition.onresult = null;
      try {
        recognition.abort();
      } catch {
        // A completed recognition instance has already released its microphone.
      }
    }
    setIsCapturing(false);
    setCaptureMode(null);
    setWaveformLevel(0);
  }, []);

  /** Stops only the browser-side wake recognizer; it never owns a Live socket. */
  const stopWakeRecognition = useCallback(() => {
    if (wakeRecognitionRestartTimerRef.current !== null) window.clearTimeout(wakeRecognitionRestartTimerRef.current);
    wakeRecognitionRestartTimerRef.current = null;
    const recognition = wakeRecognitionRef.current;
    wakeRecognitionRef.current = null;
    wakeRecognitionStartingRef.current = false;
    if (recognition) {
      recognition.onend = null;
      recognition.onerror = null;
      recognition.onresult = null;
      try {
        recognition.abort();
      } catch {
        // The browser may already have closed this recognition turn.
      }
    }
  }, []);

  const startNativeAudioCapture = useCallback(async (epoch: number) => {
    if (!sessionActiveRef.current || epoch !== sessionEpochRef.current) return false;
    if (nativeInputActiveRef.current) return true;
    if (!navigator.mediaDevices?.getUserMedia || typeof AudioContext === "undefined") return false;

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
    } catch {
      return false;
    }
    if (!sessionActiveRef.current || epoch !== sessionEpochRef.current) {
      stream.getTracks().forEach((track) => track.stop());
      return false;
    }

    const context = new AudioContext();
    const source = context.createMediaStreamSource(stream);
    // ScriptProcessor is used for broad browser support. It remains local
    // until the VAD observes speech; ambient standby/follow-up PCM is never
    // forwarded to Gemini merely to keep a session warm.
    const processor = context.createScriptProcessor(2_048, 1, 1);
    const silentSink = context.createGain();
    silentSink.gain.value = 0;
    processor.onaudioprocess = (event) => {
      if (!sessionActiveRef.current || epoch !== sessionEpochRef.current || !nativeInputActiveRef.current) return;
      const samples = event.inputBuffer.getChannelData(0);
      let energy = 0;
      for (let index = 0; index < samples.length; index += 1) energy += samples[index] * samples[index];
      const level = Math.min(1, Math.sqrt(energy / Math.max(1, samples.length)) * 3);
      const published = Math.round(level * 20) / 20;
      if (Math.abs(waveformLevelRef.current - published) >= 0.05) {
        waveformLevelRef.current = published;
        setWaveformLevel(published);
      }

      if (level >= AEGIS_VOICE_SESSION_CONFIG.vadSpeechStartLevel) {
        nativeSpeechFramesRef.current += 1;
        nativeSilenceFramesRef.current = 0;
      } else if (level <= AEGIS_VOICE_SESSION_CONFIG.vadSpeechEndLevel) {
        nativeSpeechFramesRef.current = 0;
        if (nativeTransmissionActiveRef.current) nativeSilenceFramesRef.current += 1;
      }

      if (!nativeTransmissionActiveRef.current && nativeSpeechFramesRef.current >= AEGIS_VOICE_SESSION_CONFIG.vadStartFrames) {
        nativeTransmissionActiveRef.current = true;
        setIsUserSpeaking(true);
        setPhase("listening");
        setVoiceSessionState("LISTENING");
        setState("listening");
        if (player.isPlaying) {
          player.stop();
          send("interrupt");
        }
      }

      if (!nativeTransmissionActiveRef.current) return;
      queueOrSendInputAudio(resampleMonoToPcm16(samples, context.sampleRate));
      if (nativeSilenceFramesRef.current >= AEGIS_VOICE_SESSION_CONFIG.vadEndFrames) {
        nativeTransmissionActiveRef.current = false;
        nativeSilenceFramesRef.current = 0;
        setIsUserSpeaking(false);
        setPhase("end_of_speech");
        setVoiceSessionState("END_OF_SPEECH");
        setState("thinking");
        queueOrSendAudioEnd();
        armResponseTimeout();
      }
    };
    source.connect(processor);
    processor.connect(silentSink);
    silentSink.connect(context.destination);
    inputAudioContextRef.current = context;
    inputMediaStreamRef.current = stream;
    inputSourceRef.current = source;
    inputProcessorRef.current = processor;
    inputSinkRef.current = silentSink;
    nativeInputActiveRef.current = true;
    if (context.state === "suspended") await context.resume();
    setCaptureMode("native-audio");
    setIsCapturing(true);
    setState("listening");
    return true;
  }, [armResponseTimeout, player, queueOrSendAudioEnd, queueOrSendInputAudio, send, setPhase]);

  const finishSession = useCallback((outcome: VoiceSessionOutcome = null, message: string | null = null) => {
    const session = sessionRef.current;
    const socket = socketRef.current;
    manuallyStoppedRef.current = true;
    sessionActiveRef.current = false;
    setSessionActive(false);
    sessionEpochRef.current += 1;
    connectionOpeningRef.current = false;
    gatewayReadyRef.current = false;
    pendingTranscriptRef.current = null;
    submittedTranscriptRef.current = false;
    lastSubmittedTranscriptRef.current = null;
    responseCompleteRef.current = false;
    nativeAudioQueuedRef.current = false;
    nativeAudioPlaybackStartedRef.current = false;
    pendingAudioEndRef.current = false;
    conversationAudioBatcher.clear();
    closeAudibleAlert(true);
    clearSessionTimers();
    stopNativeAudioCapture();
    stopRecognition();
    // Keep the user-authorized output context alive while Aegis is in standby.
    // A wake event is not itself a fresh click, so recreating it then may make
    // the next native response ineligible for browser playback.
    player.stop();
    player.endStream();
    if (!activatedRef.current || mutedRef.current) void player.close();
    socketRef.current = null;
    sessionRef.current = null;
    if (socket?.readyState === WebSocket.OPEN) socket.send(browserVoiceEnvelope("stop"));
    if (socket) {
      socket.onclose = null;
      socket.onerror = null;
      socket.close(1000, "voice session ended");
    }
    if (session) void closeLiveSession(session.sessionId);
    setPhase("idle");
    setSessionSecondsRemaining(0);
    setSessionOutcome(outcome);
    setError(message);
    setVoiceSessionState(message && outcome === null ? "ERROR" : mutedRef.current ? "MUTED" : "DISABLED");
    setState(message && outcome === null ? "error" : "off");
  }, [clearSessionTimers, closeAudibleAlert, conversationAudioBatcher, player, setPhase, stopNativeAudioCapture, stopRecognition]);

  useEffect(() => {
    finishSessionRef.current = finishSession;
  }, [finishSession]);

  const flushPendingTranscript = useCallback(() => {
    const text = pendingTranscriptRef.current;
    const socket = socketRef.current;
    if (!text || !gatewayReadyRef.current || socket?.readyState !== WebSocket.OPEN || !sessionActiveRef.current) return;
    pendingTranscriptRef.current = null;
    responseCompleteRef.current = false;
    nativeAudioQueuedRef.current = false;
    nativeAudioPlaybackStartedRef.current = false;
    player.beginStream();
    socket.send(browserVoiceEnvelope("text", text));
    armResponseTimeout();
    setPhase("processing");
    setVoiceSessionState("THINKING");
    setState("thinking");
  }, [armResponseTimeout, player, setPhase]);

  const resetConversationInactivityTimer = useCallback((epoch: number) => {
    pauseConversationInactivityTimer();
    const deadline = Date.now() + VOICE_FOLLOW_UP_WINDOW_MS;
    sessionDeadlineRef.current = deadline;
    setSessionSecondsRemaining(Math.ceil(VOICE_FOLLOW_UP_WINDOW_MS / 1_000));
    sessionTimerRef.current = window.setInterval(() => {
      if (!sessionActiveRef.current || epoch !== sessionEpochRef.current) return;
      const remaining = Math.max(0, deadline - Date.now());
      setSessionSecondsRemaining(Math.ceil(remaining / 1_000));
      if (remaining === 0) {
        finishSessionRef.current("timeout", null);
        if (activatedRef.current && !mutedRef.current) window.setTimeout(() => beginWakeDetectionRef.current(), 0);
      }
    }, 250);
  }, [pauseConversationInactivityTimer]);

  const submitTranscript = useCallback((text: string) => {
    const trimmed = text.trim();
    if (!sessionActiveRef.current || submittedTranscriptRef.current || !isMeaningfulVoiceTranscript(trimmed)) return;
    submittedTranscriptRef.current = true;
    lastSubmittedTranscriptRef.current = trimmed;
    pendingTranscriptRef.current = trimmed;
    // Inactivity means waiting for the operator, not time spent generating or
    // speaking an answer. Pausing here prevents long answers being cut off by
    // the listening timeout; resumeListening starts a fresh 60-second window.
    pauseConversationInactivityTimer();
    stopRecognition();
    setPhase("processing");
    setVoiceSessionState("THINKING");
    setState("thinking");
    callbacksRef.current.onTranscript?.({ speaker: "operator", text: trimmed, isFinal: true });
    flushPendingTranscript();
  }, [flushPendingTranscript, pauseConversationInactivityTimer, setPhase, stopRecognition]);

  const beginSpeechRecognition = useCallback((epoch: number) => {
    if (!sessionActiveRef.current || epoch !== sessionEpochRef.current || recognitionRef.current || recognitionStartingRef.current) return;
    const Recognition = browserSpeechRecognitionConstructor();
    if (!Recognition) {
      finishSessionRef.current(null, "Web Speech API is not supported in this browser. Use the typed fallback.");
      return;
    }
    intentionalRecognitionStopRef.current = false;
    recognitionStartingRef.current = true;
    const recognition = new Recognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = navigator.language || "en-US";
    recognition.onstart = () => {
      if (!sessionActiveRef.current || epoch !== sessionEpochRef.current) return;
      recognitionStartingRef.current = false;
      setCaptureMode("speech-recognition");
      setIsCapturing(true);
      setVoiceSessionState("LISTENING");
      setState("listening");
    };
    recognition.onresult = (event) => {
      if (!sessionActiveRef.current || epoch !== sessionEpochRef.current || submittedTranscriptRef.current) return;
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const result = event.results[index];
        const text = result?.[0]?.transcript?.trim() ?? "";
        if (!text) continue;
        if (result.isFinal) submitTranscript(text);
        else callbacksRef.current.onTranscript?.({ speaker: "operator", text, isFinal: false });
      }
    };
    recognition.onerror = (event) => {
      recognitionStartingRef.current = false;
      if (!sessionActiveRef.current || epoch !== sessionEpochRef.current || intentionalRecognitionStopRef.current) return;
      if (event.error === "no-speech" || event.error === "aborted") return;
      const message = event.error === "not-allowed" || event.error === "service-not-allowed"
        ? "Microphone permission was denied. Allow microphone access to ask Aegis."
        : `Browser speech recognition failed (${event.error}). Use the typed fallback or try again.`;
      finishSessionRef.current(null, message);
    };
    recognition.onend = () => {
      recognitionStartingRef.current = false;
      if (recognitionRef.current === recognition) recognitionRef.current = null;
      setIsCapturing(false);
      setCaptureMode(null);
      if (intentionalRecognitionStopRef.current) return;
      if (!shouldRestartSpeechRecognition({
        sessionActive: sessionActiveRef.current && epoch === sessionEpochRef.current,
        phase: sessionPhaseRef.current,
        transcriptSubmitted: submittedTranscriptRef.current,
        now: Date.now(),
        deadline: sessionDeadlineRef.current,
      })) return;
      if (recognitionRestartTimerRef.current !== null) return;
      recognitionRestartTimerRef.current = window.setTimeout(() => {
        recognitionRestartTimerRef.current = null;
        beginSpeechRecognitionRef.current(epoch);
      }, 200);
    };
    recognitionRef.current = recognition;
    try {
      recognition.start();
    } catch (nextError) {
      recognitionRef.current = null;
      recognitionStartingRef.current = false;
      const message = nextError instanceof Error ? nextError.message : "Browser speech recognition could not start.";
      finishSessionRef.current(null, `Microphone listening could not start: ${message}`);
    }
  }, [submitTranscript]);

  useEffect(() => {
    beginSpeechRecognitionRef.current = beginSpeechRecognition;
  }, [beginSpeechRecognition]);

  const openLiveConnection = useCallback(async (epoch: number, attempt = 0) => {
    if (connectionOpeningRef.current || socketRef.current || !sessionActiveRef.current || epoch !== sessionEpochRef.current) return;
    connectionOpeningRef.current = true;
    let session: LiveSession | null = null;
    let socket: WebSocket | null = null;

    const retryOrFinish = (message: string) => {
      if (!sessionActiveRef.current || epoch !== sessionEpochRef.current) return;
      clearGatewayReadyTimer();
      connectionOpeningRef.current = false;
      gatewayReadyRef.current = false;
      if (socketRef.current === socket) socketRef.current = null;
      if (sessionRef.current === session) sessionRef.current = null;
      if (socket) {
        socket.onclose = null;
        socket.onerror = null;
        try {
          socket.close(1000, "retrying voice connection");
        } catch {
          // A failed WebSocket may already be closed by the browser.
        }
      }
      if (session) void closeLiveSession(session.sessionId);

      if (attempt < AEGIS_VOICE_SESSION_CONFIG.maxGatewayReconnectAttempts) {
        setState("connecting");
        setVoiceSessionState("LISTENING");
        window.setTimeout(() => {
          void openLiveConnectionRef.current(epoch, attempt + 1);
        }, AEGIS_VOICE_SESSION_CONFIG.gatewayReconnectDelayMs);
        return;
      }
      finishSessionRef.current(null, message);
    };

    try {
      session = await createLiveSession();
    } catch (nextError) {
      retryOrFinish(nextError instanceof Error ? nextError.message : "The voice session could not be created.");
      return;
    }
    if (!sessionActiveRef.current || epoch !== sessionEpochRef.current) {
      connectionOpeningRef.current = false;
      void closeLiveSession(session.sessionId);
      return;
    }
    sessionRef.current = session;
    outputSampleRateRef.current = session.capabilities.outputSampleRate ?? 24_000;
    try {
      socket = new WebSocket(liveWebSocketUrl(session.sessionId), [session.capabilities.websocketProtocol, session.connectionToken]);
    } catch (nextError) {
      void closeLiveSession(session.sessionId);
      sessionRef.current = null;
      session = null;
      retryOrFinish(nextError instanceof Error ? nextError.message : "The voice WebSocket could not be created.");
      return;
    }
    socketRef.current = socket;
    connectionOpeningRef.current = false;
    setState("connecting");
    socket.binaryType = "arraybuffer";
    gatewayReadyTimerRef.current = window.setTimeout(() => {
      if (socketRef.current === socket && !gatewayReadyRef.current) {
        retryOrFinish("Aegis could not establish the secure voice connection. Check the service and try again.");
      }
    }, AEGIS_VOICE_SESSION_CONFIG.gatewayReadyTimeoutMs);
    socket.onmessage = (message) => {
      const queueNativeAudio = (chunk: ArrayBuffer) => {
        if (!sessionActiveRef.current || socketRef.current !== socket) return;
        clearResponseTimer();
        nativeAudioQueuedRef.current = true;
        conversationAudioBatcher.enqueue(chunk, outputSampleRateRef.current);
      };
      if (message.data instanceof ArrayBuffer) {
        queueNativeAudio(message.data);
        return;
      }
      if (message.data instanceof Blob) {
        void message.data.arrayBuffer().then(queueNativeAudio).catch(() => {
          finishSessionRef.current(null, "The voice gateway sent an unreadable native audio frame.");
        });
        return;
      }
      let payload: unknown;
      try {
        payload = JSON.parse(String(message.data));
      } catch {
        finishSessionRef.current(null, "The voice gateway sent invalid JSON.");
        return;
      }
      const parsed = serverVoiceEnvelopeSchema.safeParse(payload);
      if (!parsed.success) {
        finishSessionRef.current(null, "The voice gateway sent an invalid event.");
        return;
      }
      const event = parsed.data;
      if (!sessionActiveRef.current || socketRef.current !== socket) return;
      if (event.type === "session_ready") {
        outputSampleRateRef.current = event.outputSampleRate ?? outputSampleRateRef.current;
        clearGatewayReadyTimer();
      }
      if (event.type === "state" && event.state) {
        if (event.state === "ready") {
          clearGatewayReadyTimer();
          gatewayReadyRef.current = true;
          if (callbacksRef.current.sceneContext) socket.send(JSON.stringify({ version: "1.0", type: "scene_context", data: callbacksRef.current.sceneContext }));
          flushPendingInputAudio();
          flushPendingTranscript();
        } else if (event.state === "thinking") {
          setPhase("processing");
          setVoiceSessionState("THINKING");
          setState("thinking");
        }
      }
      if (event.type === "transcript" && event.speaker && event.text) {
        if (event.speaker === "aegis") clearResponseTimer();
        if (event.speaker === "operator" && event.isFinal && event.text.trim() === lastSubmittedTranscriptRef.current) return;
        callbacksRef.current.onTranscript?.({ speaker: event.speaker, text: event.text, isFinal: event.isFinal ?? true });
      }
      if (event.type === "citations" && event.citations) callbacksRef.current.onCitations?.(event.citations);
      if (event.type === "ui_command" && event.uiCommand) callbacksRef.current.onUiCommand?.(event.uiCommand);
      if (event.type === "projection" && event.projection) callbacksRef.current.onProjection?.(event.projection);
      if (event.type === "tool_activity" && event.tool && event.toolStatus) {
        if (event.toolStatus === "calling") setVoiceSessionState("EXECUTING");
        callbacksRef.current.onToolActivity?.({ tool: event.tool, status: event.toolStatus, turnId: event.turnId });
      }
      if (event.type === "interrupted") {
        clearResponseTimer();
        conversationAudioBatcher.clear();
        player.stop();
        responseCompleteRef.current = true;
        resumeListeningRef.current();
      }
      if (event.type === "turn_complete") {
        clearResponseTimer();
        callbacksRef.current.onTurnComplete?.();
        responseCompleteRef.current = true;
        conversationAudioBatcher.flush();
        player.endStream();
        if (!nativeAudioQueuedRef.current || nativeAudioPlaybackStartedRef.current) {
          if (!player.isPlaying) resumeListeningRef.current();
        }
      }
      if (event.type === "error") {
        retryOrFinish(event.message ?? "The Gemini Live gateway reported an error.");
      }
    };
    socket.onerror = () => {
      if (socketRef.current === socket && !manuallyStoppedRef.current) retryOrFinish("The secure Gemini Live connection failed.");
    };
    socket.onclose = () => {
      if (socketRef.current === socket && !manuallyStoppedRef.current) retryOrFinish("The Gemini Live connection closed.");
    };
  }, [clearGatewayReadyTimer, clearResponseTimer, conversationAudioBatcher, flushPendingInputAudio, flushPendingTranscript, player, setPhase]);

  useEffect(() => {
    openLiveConnectionRef.current = openLiveConnection;
  }, [openLiveConnection]);

  /**
   * Prime native Gemini audio from a deliberate opt-in click. This never asks
   * for microphone access; it only resumes the browser output context so a
   * later verified alert can play without switching to browser TTS.
   */
  const prepareAudibleAlertAudio = useCallback(async () => {
    if (sessionActiveRef.current) return false;
    try {
      await audibleAlertPlayer.prepare();
      audibleAlertPreparedRef.current = true;
      return true;
    } catch {
      audibleAlertPreparedRef.current = false;
      return false;
    }
  }, [audibleAlertPlayer]);

  /**
   * Play a HIGH/CRITICAL alert through a separate, output-only Gemini session.
   * The opaque id is revalidated by the backend before Gemini receives any
   * wording. A live operator conversation wins; callers must not fall back to
   * browser speech while that Gemini connection is simply busy.
   */
  const speakAudibleRiskAlert = useCallback(async (alertId: string): Promise<AudibleAlertPlaybackResult> => {
    if (sessionActiveRef.current || audibleAlertSocketRef.current || audibleAlertOpeningRef.current) return "busy";
    if (!audibleAlertPreparedRef.current) return "unavailable";

    audibleAlertOpeningRef.current = true;
    let session: LiveSession;
    try {
      session = await createLiveSession({ audibleAlertId: alertId });
    } catch {
      audibleAlertOpeningRef.current = false;
      return "unavailable";
    }
    if (sessionActiveRef.current || audibleAlertSocketRef.current) {
      audibleAlertOpeningRef.current = false;
      void closeLiveSession(session.sessionId);
      return "busy";
    }

    return new Promise<AudibleAlertPlaybackResult>((resolve) => {
      let resultResolved = false;
      let connectionClosed = false;
      let receivedAudio = false;
      let turnComplete = false;
      let socket: WebSocket;

      const closeConnection = (stopPlayback = false) => {
        if (connectionClosed) return;
        connectionClosed = true;
        if (audibleAlertDrainTimerRef.current !== null) {
          window.clearTimeout(audibleAlertDrainTimerRef.current);
          audibleAlertDrainTimerRef.current = null;
        }
        const isCurrent = audibleAlertSocketRef.current === socket;
        if (isCurrent) closeAudibleAlert(stopPlayback);
        else if (session) void closeLiveSession(session.sessionId);
      };

      const settle = (result: AudibleAlertPlaybackResult, stopPlayback = false) => {
        closeConnection(stopPlayback);
        if (resultResolved) return;
        resultResolved = true;
        resolve(result);
      };

      const closeWhenDrained = () => {
        if (!turnComplete || !receivedAudio) return;
        if (!audibleAlertPlayer.isPlaying) {
          settle("spoken");
          return;
        }
        audibleAlertDrainTimerRef.current = window.setTimeout(closeWhenDrained, 100);
      };

      try {
        socket = new WebSocket(
          liveWebSocketUrl(session.sessionId),
          [session.capabilities.websocketProtocol, session.connectionToken],
        );
      } catch {
        audibleAlertOpeningRef.current = false;
        void closeLiveSession(session.sessionId);
        resolve("unavailable");
        return;
      }

      audibleAlertSocketRef.current = socket;
      audibleAlertSessionRef.current = session;
      audibleAlertOutputSampleRateRef.current = session.capabilities.outputSampleRate ?? 24_000;
      audibleAlertOpeningRef.current = false;
      socket.binaryType = "arraybuffer";
      audibleAlertPlayer.beginStream();

      const queueNativeAudio = (chunk: ArrayBuffer) => {
        if (audibleAlertSocketRef.current !== socket) return;
        void audibleAlertPlayer.playPcm(chunk, audibleAlertOutputSampleRateRef.current)
          .then((played) => {
            if (!played) return;
            if (audibleAlertDrainTimerRef.current !== null) {
              window.clearTimeout(audibleAlertDrainTimerRef.current);
              audibleAlertDrainTimerRef.current = null;
            }
            receivedAudio = true;
            // Speaking has started. Keep the socket alive until the Gemini
            // turn and queued PCM have drained, but let the caller record the
            // evidence entry exactly once now.
            if (!resultResolved) {
              resultResolved = true;
              resolve("spoken");
            }
            if (turnComplete) closeWhenDrained();
          })
          .catch(() => settle("unavailable", true));
      };

      socket.onmessage = (message) => {
        if (message.data instanceof ArrayBuffer) {
          queueNativeAudio(message.data);
          return;
        }
        if (message.data instanceof Blob) {
          void message.data.arrayBuffer().then(queueNativeAudio).catch(() => settle("unavailable", true));
          return;
        }
        let payload: unknown;
        try {
          payload = JSON.parse(String(message.data));
        } catch {
          settle("unavailable", true);
          return;
        }
        const parsed = serverVoiceEnvelopeSchema.safeParse(payload);
        if (!parsed.success) {
          settle("unavailable", true);
          return;
        }
        const event = parsed.data;
        if (event.type === "session_ready") {
          audibleAlertOutputSampleRateRef.current = event.outputSampleRate ?? audibleAlertOutputSampleRateRef.current;
        }
        if (event.type === "turn_complete") {
          turnComplete = true;
          audibleAlertPlayer.endStream();
          if (!receivedAudio) settle("unavailable");
          else closeWhenDrained();
        }
        if (event.type === "error") settle("unavailable", true);
      };
      socket.onerror = () => settle("unavailable", true);
      socket.onclose = () => {
        if (!receivedAudio) {
          settle("unavailable", true);
          return;
        }
        // The provider may close immediately after its final PCM chunk.
        // Preserve queued native audio, then release the short-lived record.
        turnComplete = true;
        audibleAlertPlayer.endStream();
        closeWhenDrained();
      };
      // No alert should leave a socket or a promise open if a provider never
      // emits a first audio frame.
      audibleAlertDrainTimerRef.current = window.setTimeout(() => {
        if (!receivedAudio) settle("unavailable", true);
      }, 12_000);
    });
  }, [audibleAlertPlayer, closeAudibleAlert]);

  const resumeListening = useCallback(() => {
    if (!sessionActiveRef.current || !responseCompleteRef.current) return;
    const epoch = sessionEpochRef.current;
    responseCompleteRef.current = false;
    nativeAudioQueuedRef.current = false;
    nativeAudioPlaybackStartedRef.current = false;
    conversationAudioBatcher.clear();
    submittedTranscriptRef.current = false;
    lastSubmittedTranscriptRef.current = null;
    setPhase("follow_up");
    setVoiceSessionState("FOLLOW_UP_WINDOW");
    setState("ready");
    resetConversationInactivityTimer(epoch);
    if (!nativeInputActiveRef.current) beginSpeechRecognitionRef.current(epoch);
  }, [conversationAudioBatcher, resetConversationInactivityTimer, setPhase]);

  useEffect(() => {
    resumeListeningRef.current = resumeListening;
  }, [resumeListening]);

  const beginWakeDetection = useCallback(() => {
    if (!activatedRef.current || mutedRef.current || sessionActiveRef.current || wakeRecognitionRef.current || wakeRecognitionStartingRef.current) return;
    const Recognition = browserSpeechRecognitionConstructor();
    if (!Recognition) {
      // No local wake engine is available. This is deliberately explicit: the
      // user remains in a VAD-gated active session, not a falsely-labelled
      // private wake-word mode.
      setWakeWordMode("session-listening");
      setPhase("listening");
      setVoiceSessionState("LISTENING");
      void beginConversationRef.current();
      return;
    }

    setWakeWordMode("browser-recognition");
    setPhase("standby");
    setVoiceSessionState("STANDBY");
    setState("ready");
    wakeRecognitionStartingRef.current = true;
    const recognition = new Recognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = navigator.language || "en-US";
    recognition.onstart = () => {
      if (!activatedRef.current || mutedRef.current || sessionActiveRef.current) return;
      wakeRecognitionStartingRef.current = false;
      setCaptureMode("speech-recognition");
      setIsCapturing(true);
    };
    recognition.onresult = (event) => {
      if (!activatedRef.current || mutedRef.current || sessionActiveRef.current) return;
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const result = event.results[index];
        const text = result?.[0]?.transcript?.trim() ?? "";
        const command = wakePhraseCommand(text);
        if (command === null) continue;
        // Interim detection creates the immediate visual attention response;
        // only a final browser transcript may activate a remote session.
        setPhase("wake_detected");
        setVoiceSessionState("WAKE_DETECTED");
        if (!result.isFinal) continue;
        stopWakeRecognition();
        setIsCapturing(false);
        setCaptureMode(null);
        void beginConversationRef.current(command || undefined);
        return;
      }
    };
    recognition.onerror = (event) => {
      wakeRecognitionStartingRef.current = false;
      if (!activatedRef.current || mutedRef.current || event.error === "aborted" || event.error === "no-speech") return;
      if (event.error === "not-allowed" || event.error === "service-not-allowed") {
        activatedRef.current = false;
        setIsActivated(false);
        setVoiceSessionState("ERROR");
        setState("error");
        setError("Microphone permission was denied. Allow microphone access to activate Aegis.");
      }
    };
    recognition.onend = () => {
      wakeRecognitionStartingRef.current = false;
      if (wakeRecognitionRef.current === recognition) wakeRecognitionRef.current = null;
      if (!activatedRef.current || mutedRef.current || sessionActiveRef.current) return;
      if (wakeRecognitionRestartTimerRef.current !== null) return;
      wakeRecognitionRestartTimerRef.current = window.setTimeout(() => {
        wakeRecognitionRestartTimerRef.current = null;
        beginWakeDetectionRef.current();
      }, AEGIS_VOICE_SESSION_CONFIG.recognitionRestartDelayMs);
    };
    wakeRecognitionRef.current = recognition;
    try {
      recognition.start();
    } catch (error) {
      wakeRecognitionRef.current = null;
      wakeRecognitionStartingRef.current = false;
      setVoiceSessionState("ERROR");
      setState("error");
      setError(error instanceof Error ? `Wake detection could not start: ${error.message}` : "Wake detection could not start.");
    }
  }, [stopWakeRecognition]);

  useEffect(() => {
    beginWakeDetectionRef.current = beginWakeDetection;
  }, [beginWakeDetection]);

  const startListening = useCallback(async (initialTranscript?: string) => {
    if (sessionActiveRef.current) return;
    if (!navigator.mediaDevices?.getUserMedia && !browserSpeechRecognitionConstructor()) {
      setError("Microphone capture is not supported in this browser. Use the typed fallback.");
      setState("error");
      return;
    }
    // An explicit operator conversation always wins over a background risk
    // alert. Stop its socket and isolated player before opening the microphone.
    closeAudibleAlert(true);
    stopWakeRecognition();
    setIsCapturing(false);
    setCaptureMode(null);
    const epoch = sessionEpochRef.current + 1;
    sessionEpochRef.current = epoch;
    sessionActiveRef.current = true;
    setSessionActive(true);
    manuallyStoppedRef.current = false;
    gatewayReadyRef.current = false;
    pendingTranscriptRef.current = initialTranscript?.trim() || null;
    pendingAudioEndRef.current = false;
    submittedTranscriptRef.current = false;
    lastSubmittedTranscriptRef.current = null;
    responseCompleteRef.current = false;
    nativeAudioQueuedRef.current = false;
    nativeAudioPlaybackStartedRef.current = false;
    conversationAudioBatcher.clear();
    setError(null);
    setSessionOutcome(null);
    setVoiceSessionState("LISTENING");
    setPhase("listening");
    setState("listening");
    resetConversationInactivityTimer(epoch);
    // Preparing playback inside this click keeps native Gemini response audio
    // eligible for browser playback without opening the microphone early.
    void player.prepare().catch(() => finishSessionRef.current(null, "The browser could not authorize Aegis audio playback."));
    void startNativeAudioCapture(epoch).then((started) => {
      if (!started) beginSpeechRecognition(epoch);
    });
    void openLiveConnection(epoch);
  }, [beginSpeechRecognition, closeAudibleAlert, conversationAudioBatcher, openLiveConnection, player, resetConversationInactivityTimer, setPhase, startNativeAudioCapture, stopWakeRecognition]);

  useEffect(() => {
    beginConversationRef.current = startListening;
  }, [startListening]);

  /** Explicit first-use activation required by browser microphone policy. */
  const activate = useCallback(async () => {
    if (activatedRef.current && !mutedRef.current) return;
    if (!navigator.mediaDevices?.getUserMedia && !browserSpeechRecognitionConstructor()) {
      setVoiceSessionState("ERROR");
      setState("error");
      setError("Microphone capture is not supported in this browser.");
      return;
    }
    activatedRef.current = true;
    mutedRef.current = false;
    setIsActivated(true);
    setIsMuted(false);
    setError(null);
    setSessionOutcome(null);
    setPhase("activating");
    setVoiceSessionState("ACTIVATING");
    // This happens inside the user gesture so Aegis can play a later response.
    await player.prepare().catch(() => undefined);
    beginWakeDetectionRef.current();
  }, [player]);

  const mute = useCallback(() => {
    // Set this before finishing an active turn so finishSession releases the
    // retained output context along with the microphone resources.
    mutedRef.current = true;
    activatedRef.current = true;
    stopWakeRecognition();
    setIsCapturing(false);
    setCaptureMode(null);
    if (sessionActiveRef.current || socketRef.current || sessionRef.current) finishSession("cancelled", null);
    else {
      conversationAudioBatcher.clear();
      stopNativeAudioCapture();
      stopRecognition();
      void player.close();
    }
    setIsMuted(true);
    setIsActivated(true);
    setPhase("muted");
    setVoiceSessionState("MUTED");
    setState("off");
  }, [conversationAudioBatcher, finishSession, player, stopNativeAudioCapture, stopRecognition, stopWakeRecognition]);

  const unmute = useCallback(() => {
    if (!activatedRef.current) {
      void activate();
      return;
    }
    mutedRef.current = false;
    setIsMuted(false);
    setError(null);
    beginWakeDetectionRef.current();
  }, [activate]);

  const interrupt = useCallback(() => {
    if (!sessionActiveRef.current || !player.isPlaying) return false;
    player.stop();
    send("interrupt");
    nativeTransmissionActiveRef.current = false;
    nativeSpeechFramesRef.current = 0;
    nativeSilenceFramesRef.current = 0;
    setIsUserSpeaking(false);
    setPhase("listening");
    setVoiceSessionState("LISTENING");
    setState("listening");
    return true;
  }, [player, send, setPhase]);

  const deactivate = useCallback(() => {
    activatedRef.current = false;
    mutedRef.current = false;
    stopWakeRecognition();
    setIsActivated(false);
    setIsMuted(false);
    setIsCapturing(false);
    setCaptureMode(null);
    if (sessionActiveRef.current || socketRef.current || sessionRef.current) finishSession("cancelled", null);
    else {
      conversationAudioBatcher.clear();
      closeAudibleAlert(true);
      stopNativeAudioCapture();
      stopRecognition();
      void player.close();
      setPhase("idle");
      setState("off");
    }
    setVoiceSessionState("DISABLED");
  }, [closeAudibleAlert, conversationAudioBatcher, finishSession, player, setPhase, stopNativeAudioCapture, stopRecognition, stopWakeRecognition]);

  const stop = deactivate;

  // Kept as a compatibility alias for the existing voice core callers.
  const enableHandsFree = startListening;
  const beginPushToTalk = startListening;
  const endPushToTalk = useCallback(() => undefined, []);

  const sendTypedFallback = useCallback((text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return false;
    if (socketRef.current?.readyState !== WebSocket.OPEN || !gatewayReadyRef.current || !sessionActiveRef.current) return false;
    conversationAudioBatcher.clear();
    player.stop();
    player.beginStream();
    pauseConversationInactivityTimer();
    send("text", trimmed);
    setPhase("processing");
    setState("thinking");
    return true;
  }, [conversationAudioBatcher, pauseConversationInactivityTimer, player, send, setPhase]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") stop();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      stop();
      void audibleAlertPlayer.close();
    };
  }, [audibleAlertPlayer, stop]);

  return {
    state,
    error,
    waveformLevel,
    playbackLevel,
    captureMode,
    isCapturing,
    sessionPhase,
    voiceSessionState,
    sessionOutcome,
    sessionSecondsRemaining,
    sessionActive,
    isActivated,
    isMuted,
    isUserSpeaking,
    wakeWordMode,
    activate,
    deactivate,
    mute,
    unmute,
    interrupt,
    startListening,
    enableHandsFree,
    beginPushToTalk,
    endPushToTalk,
    sendTypedFallback,
    prepareAudibleAlertAudio,
    speakAudibleRiskAlert,
    stopAudibleRiskAlert,
    stop
  };
}
