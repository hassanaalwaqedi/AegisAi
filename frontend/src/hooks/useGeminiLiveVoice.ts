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
  type SafeUICommand,
  type VoiceState
} from "@/lib/live-voice";

type CaptureMode = "speech-recognition" | null;

export type VoiceSessionPhase = "idle" | "listening" | "processing" | "response";
export type VoiceSessionOutcome = "cancelled" | "timeout" | null;
export type AudibleAlertPlaybackResult = "spoken" | "unavailable" | "busy";

/** An open conversation ends only after 60 seconds without a new request. */
export const VOICE_CONVERSATION_IDLE_TIMEOUT_MS = 60_000;

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

/** Queues signed 16-bit mono native Gemini PCM without browser TTS. */
export class NativePcmPlayer {
  constructor(private readonly callbacks: PcmPlayerCallbacks) {}

  private context?: AudioContext;
  private analyser?: AnalyserNode;
  private levelFrame = 0;
  private nextStartAt = 0;
  private sources = new Set<AudioBufferSourceNode>();

  get isPlaying() {
    return this.sources.size > 0;
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

  async playPcm(pcmBuffer: ArrayBuffer, sampleRate: number) {
    await this.prepare();
    const context = this.context;
    if (!context || !this.analyser) throw new Error("Native audio output is not ready.");
    const samples = pcmToFloat(pcmBuffer);
    if (samples.length === 0) return false;
    const buffer = context.createBuffer(1, samples.length, sampleRate);
    buffer.copyToChannel(samples, 0);
    const source = context.createBufferSource();
    source.buffer = buffer;
    source.connect(this.analyser);
    source.onended = () => {
      this.sources.delete(source);
      if (this.sources.size === 0) {
        this.stopLevelMonitor();
        this.callbacks.onIdle();
      }
    };
    const startAt = Math.max(context.currentTime + 0.015, this.nextStartAt);
    source.start(startAt);
    this.nextStartAt = startAt + buffer.duration;
    const wasIdle = this.sources.size === 0;
    this.sources.add(source);
    this.startLevelMonitor();
    if (wasIdle) this.callbacks.onStarted();
    return true;
  }

  stop() {
    const wasPlaying = this.sources.size > 0;
    this.sources.forEach((source) => {
      try {
        source.stop();
      } catch {
        // A source that already ended has no work left to do.
      }
    });
    this.sources.clear();
    this.nextStartAt = 0;
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
 * A short, explicit operator voice turn. Browser speech recognition captures
 * a conversation through the existing authenticated Gemini Live gateway. No
 * microphone is opened until startListening is called from a user gesture,
 * and every exit path releases it.
 */
export function useGeminiLiveVoice(callbacks: VoiceCallbacks = {}) {
  const [state, setState] = useState<VoiceState>("off");
  const [error, setError] = useState<string | null>(null);
  const [waveformLevel, setWaveformLevel] = useState(0);
  const [playbackLevel, setPlaybackLevel] = useState(0);
  const [captureMode, setCaptureMode] = useState<CaptureMode>(null);
  const [isCapturing, setIsCapturing] = useState(false);
  const [sessionPhase, setSessionPhase] = useState<VoiceSessionPhase>("idle");
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
  const beginSpeechRecognitionRef = useRef<(epoch: number) => void>(() => undefined);
  const recognitionRestartTimerRef = useRef<number | null>(null);
  const recognitionStartingRef = useRef(false);
  const intentionalRecognitionStopRef = useRef(false);
  const sessionActiveRef = useRef(false);
  const sessionEpochRef = useRef(0);
  const sessionDeadlineRef = useRef(0);
  const sessionPhaseRef = useRef<VoiceSessionPhase>("idle");
  const sessionTimerRef = useRef<number | null>(null);
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
  const finishSessionRef = useRef<(outcome?: VoiceSessionOutcome, message?: string | null) => void>(() => undefined);
  const resumeListeningRef = useRef<() => void>(() => undefined);
  const onPlayerLevel = useCallback((level: number) => setPlaybackLevel(level), []);
  const setPhase = useCallback((phase: VoiceSessionPhase) => {
    sessionPhaseRef.current = phase;
    setSessionPhase(phase);
  }, []);
  const onPlayerStarted = useCallback(() => {
    if (!sessionActiveRef.current) return;
    nativeAudioPlaybackStartedRef.current = true;
    setPhase("response");
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
  const callbacksRef = useRef(callbacks);

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
    if (stopPlayback) player.stop();
    if (socket?.readyState === WebSocket.OPEN) socket.send(browserVoiceEnvelope("stop"));
    if (socket) {
      socket.onclose = null;
      socket.onerror = null;
      socket.close(1000, "audible alert ended");
    }
    if (session) void closeLiveSession(session.sessionId);
  }, [player]);

  const send = useCallback((type: "audio" | "text" | "audio_end" | "interrupt" | "stop" | "ping", data?: string, mimeType?: string) => {
    const socket = socketRef.current;
    if (socket?.readyState === WebSocket.OPEN) socket.send(browserVoiceEnvelope(type, data, mimeType));
  }, []);

  const clearSessionTimers = useCallback(() => {
    if (sessionTimerRef.current !== null) window.clearInterval(sessionTimerRef.current);
    if (recognitionRestartTimerRef.current !== null) window.clearTimeout(recognitionRestartTimerRef.current);
    sessionTimerRef.current = null;
    recognitionRestartTimerRef.current = null;
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
    audibleAlertPreparedRef.current = false;
    closeAudibleAlert(true);
    clearSessionTimers();
    stopRecognition();
    void player.close();
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
    setState(message && outcome === null ? "error" : "off");
  }, [clearSessionTimers, closeAudibleAlert, player, setPhase, stopRecognition]);

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
    socket.send(browserVoiceEnvelope("text", text));
  }, []);

  const resetConversationInactivityTimer = useCallback((epoch: number) => {
    if (sessionTimerRef.current !== null) window.clearInterval(sessionTimerRef.current);
    const deadline = Date.now() + VOICE_CONVERSATION_IDLE_TIMEOUT_MS;
    sessionDeadlineRef.current = deadline;
    setSessionSecondsRemaining(Math.ceil(VOICE_CONVERSATION_IDLE_TIMEOUT_MS / 1_000));
    sessionTimerRef.current = window.setInterval(() => {
      if (!sessionActiveRef.current || epoch !== sessionEpochRef.current) return;
      const remaining = Math.max(0, deadline - Date.now());
      setSessionSecondsRemaining(Math.ceil(remaining / 1_000));
      if (remaining === 0) finishSessionRef.current("timeout", "No request was received for 60 seconds. Listening stopped safely.");
    }, 250);
  }, []);

  const submitTranscript = useCallback((text: string) => {
    const trimmed = text.trim();
    if (!sessionActiveRef.current || submittedTranscriptRef.current || !isMeaningfulVoiceTranscript(trimmed)) return;
    submittedTranscriptRef.current = true;
    lastSubmittedTranscriptRef.current = trimmed;
    pendingTranscriptRef.current = trimmed;
    resetConversationInactivityTimer(sessionEpochRef.current);
    stopRecognition();
    setPhase("processing");
    setState("thinking");
    callbacksRef.current.onTranscript?.({ speaker: "operator", text: trimmed, isFinal: true });
    flushPendingTranscript();
  }, [flushPendingTranscript, resetConversationInactivityTimer, setPhase, stopRecognition]);

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

  const openLiveConnection = useCallback(async (epoch: number) => {
    if (connectionOpeningRef.current || socketRef.current || !sessionActiveRef.current || epoch !== sessionEpochRef.current) return;
    connectionOpeningRef.current = true;
    let session: LiveSession;
    try {
      session = await createLiveSession();
    } catch (nextError) {
      if (sessionActiveRef.current && epoch === sessionEpochRef.current) {
        finishSessionRef.current(null, nextError instanceof Error ? nextError.message : "The voice session could not be created.");
      }
      return;
    }
    if (!sessionActiveRef.current || epoch !== sessionEpochRef.current) {
      void closeLiveSession(session.sessionId);
      return;
    }
    sessionRef.current = session;
    outputSampleRateRef.current = session.capabilities.outputSampleRate ?? 24_000;
    let socket: WebSocket;
    try {
      socket = new WebSocket(liveWebSocketUrl(session.sessionId), [session.capabilities.websocketProtocol, session.connectionToken]);
    } catch (nextError) {
      void closeLiveSession(session.sessionId);
      sessionRef.current = null;
      if (sessionActiveRef.current && epoch === sessionEpochRef.current) {
        finishSessionRef.current(null, nextError instanceof Error ? nextError.message : "The voice WebSocket could not be created.");
      }
      return;
    }
    socketRef.current = socket;
    connectionOpeningRef.current = false;
    socket.binaryType = "arraybuffer";
    socket.onmessage = (message) => {
      const queueNativeAudio = (chunk: ArrayBuffer) => {
        if (!sessionActiveRef.current || socketRef.current !== socket) return;
        nativeAudioQueuedRef.current = true;
        void player.playPcm(chunk, outputSampleRateRef.current).catch(() => {
          finishSessionRef.current(null, "Aegis native audio playback is unavailable in this browser.");
        });
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
      if (event.type === "session_ready") outputSampleRateRef.current = event.outputSampleRate ?? outputSampleRateRef.current;
      if (event.type === "state" && event.state) {
        if (event.state === "ready") {
          gatewayReadyRef.current = true;
          flushPendingTranscript();
        } else if (event.state === "thinking") {
          setPhase("processing");
          setState("thinking");
        }
      }
      if (event.type === "transcript" && event.speaker && event.text) {
        if (event.speaker === "operator" && event.isFinal && event.text.trim() === lastSubmittedTranscriptRef.current) return;
        callbacksRef.current.onTranscript?.({ speaker: event.speaker, text: event.text, isFinal: event.isFinal ?? true });
      }
      if (event.type === "citations" && event.citations) callbacksRef.current.onCitations?.(event.citations);
      if (event.type === "ui_command" && event.uiCommand) callbacksRef.current.onUiCommand?.(event.uiCommand);
      if (event.type === "tool_activity" && event.tool && event.toolStatus) callbacksRef.current.onToolActivity?.({ tool: event.tool, status: event.toolStatus, turnId: event.turnId });
      if (event.type === "interrupted") {
        player.stop();
        responseCompleteRef.current = true;
        resumeListeningRef.current();
      }
      if (event.type === "turn_complete") {
        responseCompleteRef.current = true;
        if (!nativeAudioQueuedRef.current || nativeAudioPlaybackStartedRef.current) {
          if (!player.isPlaying) resumeListeningRef.current();
        }
      }
      if (event.type === "error") {
        finishSessionRef.current(null, event.message ?? "The Gemini Live gateway reported an error.");
      }
    };
    socket.onerror = () => {
      if (socketRef.current === socket && !manuallyStoppedRef.current) finishSessionRef.current(null, "The secure Gemini Live connection failed.");
    };
    socket.onclose = () => {
      if (socketRef.current === socket && !manuallyStoppedRef.current) finishSessionRef.current(null, "The Gemini Live connection closed.");
    };
  }, [flushPendingTranscript, player, setPhase]);

  /**
   * Prime native Gemini audio from a deliberate opt-in click. This never asks
   * for microphone access; it only resumes the browser output context so a
   * later verified alert can play without switching to browser TTS.
   */
  const prepareAudibleAlertAudio = useCallback(async () => {
    if (sessionActiveRef.current) return false;
    try {
      await player.prepare();
      audibleAlertPreparedRef.current = true;
      return true;
    } catch {
      audibleAlertPreparedRef.current = false;
      return false;
    }
  }, [player]);

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
        if (!player.isPlaying) {
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

      const queueNativeAudio = (chunk: ArrayBuffer) => {
        if (audibleAlertSocketRef.current !== socket) return;
        void player.playPcm(chunk, audibleAlertOutputSampleRateRef.current)
          .then((played) => {
            if (!played) return;
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
        closeWhenDrained();
      };
      // No alert should leave a socket or a promise open if a provider never
      // emits a first audio frame.
      audibleAlertDrainTimerRef.current = window.setTimeout(() => {
        if (!receivedAudio) settle("unavailable", true);
      }, 12_000);
    });
  }, [closeAudibleAlert, player]);

  const resumeListening = useCallback(() => {
    if (!sessionActiveRef.current || !responseCompleteRef.current) return;
    const epoch = sessionEpochRef.current;
    responseCompleteRef.current = false;
    nativeAudioQueuedRef.current = false;
    nativeAudioPlaybackStartedRef.current = false;
    submittedTranscriptRef.current = false;
    lastSubmittedTranscriptRef.current = null;
    setPhase("listening");
    setState("listening");
    resetConversationInactivityTimer(epoch);
    beginSpeechRecognitionRef.current(epoch);
  }, [resetConversationInactivityTimer, setPhase]);

  useEffect(() => {
    resumeListeningRef.current = resumeListening;
  }, [resumeListening]);

  const startListening = useCallback(async () => {
    if (sessionActiveRef.current) {
      finishSession("cancelled", "Listening cancelled.");
      return;
    }
    if (!browserSpeechRecognitionConstructor()) {
      setError("Web Speech API is not supported in this browser. Use the typed fallback.");
      setState("error");
      return;
    }
    const epoch = sessionEpochRef.current + 1;
    sessionEpochRef.current = epoch;
    sessionActiveRef.current = true;
    setSessionActive(true);
    manuallyStoppedRef.current = false;
    gatewayReadyRef.current = false;
    pendingTranscriptRef.current = null;
    submittedTranscriptRef.current = false;
    lastSubmittedTranscriptRef.current = null;
    responseCompleteRef.current = false;
    nativeAudioQueuedRef.current = false;
    nativeAudioPlaybackStartedRef.current = false;
    setError(null);
    setSessionOutcome(null);
    setPhase("listening");
    setState("listening");
    resetConversationInactivityTimer(epoch);
    // Preparing playback inside this click keeps native Gemini response audio
    // eligible for browser playback without opening the microphone early.
    void player.prepare().catch(() => finishSessionRef.current(null, "The browser could not authorize Aegis audio playback."));
    beginSpeechRecognition(epoch);
    void openLiveConnection(epoch);
  }, [beginSpeechRecognition, finishSession, openLiveConnection, player, resetConversationInactivityTimer, setPhase]);

  const stop = useCallback(() => {
    if (sessionActiveRef.current || socketRef.current || sessionRef.current) finishSession("cancelled", "Listening cancelled.");
    else {
      audibleAlertPreparedRef.current = false;
      closeAudibleAlert(true);
      stopRecognition();
      void player.close();
      setPhase("idle");
      setState("off");
    }
  }, [closeAudibleAlert, finishSession, player, setPhase, stopRecognition]);

  // Kept as a compatibility alias for the existing voice core callers.
  const enableHandsFree = startListening;
  const beginPushToTalk = startListening;
  const endPushToTalk = useCallback(() => undefined, []);

  const sendTypedFallback = useCallback((text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return false;
    if (socketRef.current?.readyState !== WebSocket.OPEN || !gatewayReadyRef.current || !sessionActiveRef.current) return false;
    player.stop();
    send("text", trimmed);
    setPhase("processing");
    setState("thinking");
    return true;
  }, [player, send, setPhase]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") stop();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      stop();
    };
  }, [stop]);

  return {
    state,
    error,
    waveformLevel,
    playbackLevel,
    captureMode,
    isCapturing,
    sessionPhase,
    sessionOutcome,
    sessionSecondsRemaining,
    sessionActive,
    startListening,
    enableHandsFree,
    beginPushToTalk,
    endPushToTalk,
    sendTypedFallback,
    prepareAudibleAlertAudio,
    speakAudibleRiskAlert,
    stopAudibleRiskAlert: () => closeAudibleAlert(true),
    stop
  };
}
