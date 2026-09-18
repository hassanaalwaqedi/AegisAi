"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { AudioLines, Mic, Radio, Send, ShieldCheck, Square } from "lucide-react";

import { useGeminiLiveVoice, voiceStateLabel } from "@/hooks/useGeminiLiveVoice";
import { fetchLiveCapabilities, type LiveCapabilities, type LiveCitation, type SafeUICommand, type VoiceState } from "@/lib/live-voice";
import { availabilityLabel, formatFreshness, type Availability } from "@/lib/intelligence-context";

type Transcript = {
  id: string;
  speaker: "operator" | "aegis";
  text: string;
  citations: LiveCitation[];
};

const routeForCitation = (citation: LiveCitation) => {
  if (citation.kind === "camera") return "/cameras";
  if (citation.kind === "track" || citation.kind === "detection") return "/tracks";
  if (citation.kind === "event" || citation.kind === "alert" || citation.kind === "recording") return "/events";
  return null;
};

export function applySafeUiCommand(command: SafeUICommand) {
  if (command.kind === "focus_health") {
    document.getElementById("intelligence-health-panel")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    return;
  }
  const route = command.kind === "open_cameras"
    ? "/cameras"
    : command.kind === "open_semantic_evidence"
      ? "/semantic"
      : command.kind === "show_track_evidence"
        ? "/tracks"
        : "/events";
  window.location.assign(route);
}

function StateWaveform({ state, level }: { state: VoiceState; level: number }) {
  const active = state === "listening" || state === "speaking";
  return (
    <div className="flex h-7 items-center gap-0.5" aria-hidden="true">
      {Array.from({ length: 18 }, (_, index) => {
        const amplitude = active ? Math.min(1, Math.max(0, level)) * (0.45 + ((index * 7) % 6) / 8) : 0;
        return <span key={index} className={`w-0.5 rounded-full ${active ? "bg-signal-cyan" : "bg-white/15"}`} style={{ height: `${Math.round(5 + amplitude * 20)}px`, opacity: active ? 0.45 + amplitude * 0.55 : 0.5, transition: "height 120ms ease, opacity 120ms ease" }} />;
      })}
    </div>
  );
}

export default function VoiceCopilot({
  contextAvailability,
  contextReason,
  onActivity,
  onUiCommand,
  onUserTurn,
  onToolActivity,
  onProjection,
  sceneContext,
  onCitation,
}: {
  contextAvailability: Availability;
  contextReason?: string | null;
  onActivity?: (activity: { state: VoiceState; inputLevel: number; outputLevel: number; sessionActive: boolean; isCapturing: boolean }) => void;
  onUiCommand?: (command: SafeUICommand) => void;
  onUserTurn?: (message: string) => void;
  onToolActivity?: (activity: { tool: string; status: "calling" | "completed" | "failed" }) => void;
  onProjection?: (execution: import("@/lib/operator-api").OperatorExecution) => void;
  sceneContext?: string;
  onCitation?: (citation: LiveCitation) => void;
}) {
  const [capabilities, setCapabilities] = useState<LiveCapabilities | null>(null);
  const [capabilityError, setCapabilityError] = useState<string | null>(null);
  const [transcripts, setTranscripts] = useState<Transcript[]>([]);
  const [pendingCitations, setPendingCitations] = useState<LiveCitation[]>([]);
  const [typedCommand, setTypedCommand] = useState("");
  const pendingCitationsRef = useRef<LiveCitation[]>([]);
  const userTurnRef = useRef("");
  const transcriptSequenceRef = useRef(0);
  const flushUserTurn = useCallback(() => {
    if (!userTurnRef.current.trim()) return;
    onUserTurn?.(userTurnRef.current.trim());
    userTurnRef.current = "";
  }, [onUserTurn]);

  const onTranscript = useCallback((entry: { speaker: "operator" | "aegis"; text: string; isFinal: boolean }) => {
    if (!entry.isFinal) return;
    if (entry.speaker === "operator") userTurnRef.current += entry.text;
    setTranscripts((current) => [
      ...current,
      {
        // Multiple final transcript events can be delivered in one browser
        // task. A sequence remains unique in that case, unlike Date.now().
        id: `${entry.speaker}-${++transcriptSequenceRef.current}`,
        speaker: entry.speaker,
        text: entry.text,
        citations: entry.speaker === "aegis" ? pendingCitationsRef.current : []
      }
    ].slice(-8));
    if (entry.speaker === "aegis") {
      pendingCitationsRef.current = [];
      setPendingCitations([]);
    }
  }, []);

  const onCitations = useCallback((next: LiveCitation[]) => {
    pendingCitationsRef.current = next;
    setPendingCitations(next);
  }, []);

  const voice = useGeminiLiveVoice({
    onTranscript,
    onCitations,
    onToolActivity,
    sceneContext,
    onProjection: (execution) => {
      flushUserTurn();
      onProjection?.(execution);
    },
    onTurnComplete: flushUserTurn,
    onUiCommand: (command) => {
      flushUserTurn();
      if (onUiCommand) onUiCommand(command);
      else applySafeUiCommand(command);
    }
  });

  useEffect(() => {
    onActivity?.({
      state: voice.state,
      inputLevel: voice.waveformLevel,
      outputLevel: voice.playbackLevel,
      sessionActive: voice.sessionActive,
      isCapturing: voice.isCapturing,
    });
  }, [onActivity, voice.isCapturing, voice.playbackLevel, voice.sessionActive, voice.state, voice.waveformLevel]);

  useEffect(() => {
    const controller = new AbortController();
    void fetchLiveCapabilities(controller.signal)
      .then((next) => {
        setCapabilities(next);
        setCapabilityError(null);
      })
      .catch(() => setCapabilityError("Voice assistance is temporarily unavailable."));
    return () => controller.abort();
  }, []);

  const enabled = capabilities?.availability === "live" && contextAvailability === "live";
  const unavailableReason = capabilityError
    ?? capabilities?.reason
    ?? contextReason
    ?? "Voice assistance is temporarily unavailable.";
  const isOff = !voice.sessionActive;

  const submitTypedFallback = (event: FormEvent) => {
    event.preventDefault();
    if (voice.sendTypedFallback(typedCommand)) setTypedCommand("");
  };

  return (
    <section className="w-full rounded-xl border border-signal-cyan/15 bg-[#0a0f1a]/90 p-3 shadow-[0_0_32px_rgba(56,214,255,0.06)]" aria-labelledby="aegis-voice-title">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <div className={`rounded-lg p-1.5 ${voice.state === "error" ? "bg-signal-red/10 text-signal-red" : "bg-signal-cyan/10 text-signal-cyan"}`}><AudioLines size={15} /></div>
          <div>
            <h2 id="aegis-voice-title" className="text-[11px] font-semibold text-white/85">Aegis Voice</h2>
            <p className="text-[9px] text-white/40">Live voice · verified Aegis information</p>
          </div>
        </div>
        <div className={`flex items-center gap-1.5 rounded-full px-2 py-1 text-[9px] ${voice.state === "error" ? "bg-signal-red/10 text-signal-red" : "bg-white/[0.04] text-white/60"}`} role="status" aria-live="polite">
          <Radio size={10} className={voice.state === "listening" ? "animate-pulse text-signal-cyan" : undefined} />
          {voiceStateLabel(voice.state)}
        </div>
      </div>

      <div className="mt-2 flex items-center justify-between rounded-lg border border-white/[0.05] bg-white/[0.02] px-2.5 py-1.5">
        <StateWaveform state={voice.state} level={voice.state === "speaking" ? voice.playbackLevel : voice.isCapturing ? voice.waveformLevel : 0} />
        <span className="ms-2 text-end text-[9px] text-white/35">{voice.captureMode === "speech-recognition" ? "Listening through this browser" : "Microphone is active only during this voice session"}</span>
      </div>

      <div className="mt-2 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => void voice.startListening()}
          disabled={!enabled}
          className="inline-flex items-center gap-1.5 rounded-lg bg-signal-cyan px-3 py-1.5 text-[10px] font-semibold text-[#061019] transition hover:bg-signal-cyan/90 disabled:cursor-not-allowed disabled:opacity-35"
          title={enabled ? (isOff ? "Ask Aegis. Microphone access begins only after this click." : "Stop the active listening session.") : unavailableReason}
        >
          <Mic size={12} /> {isOff ? "Ask Aegis" : "Stop listening"}
        </button>
        {voice.sessionActive && (
          <button type="button" onClick={voice.stop} className="inline-flex items-center gap-1.5 rounded-lg border border-signal-red/20 bg-signal-red/[0.05] px-3 py-1.5 text-[10px] text-signal-red" title="Stop microphone capture and native audio. Escape also stops voice.">
            <Square size={11} /> Stop
          </button>
        )}
      </div>

      {!enabled && <p className="mt-2 text-[9px] leading-relaxed text-signal-amber/80">Voice unavailable: {unavailableReason}</p>}
      {voice.error && <p className="mt-2 text-[9px] leading-relaxed text-signal-red/85" role="alert">Microphone capture and audio playback have stopped. {voice.error}</p>}
      {capabilities?.nativeAudio && <p className="mt-1 text-[8px] text-white/25">Voice audio is secured and starts only after you ask.</p>}

      <form onSubmit={submitTypedFallback} className="mt-2 flex gap-1.5">
        <input value={typedCommand} onChange={(event) => setTypedCommand(event.target.value)} disabled={voice.state === "off" || voice.state === "error"} placeholder="Type a request for Aegis" className="min-w-0 flex-1 rounded-md border border-white/[0.07] bg-black/10 px-2 py-1.5 text-[10px] text-white/80 outline-none placeholder:text-white/20 disabled:opacity-40" />
        <button type="submit" disabled={!typedCommand.trim() || voice.state === "off" || voice.state === "error"} className="rounded-md p-1.5 text-signal-cyan disabled:opacity-30" title="Send text request to Aegis"><Send size={13} /></button>
      </form>

      {transcripts.length > 0 && (
        <div className="custom-scrollbar mt-2 max-h-40 space-y-1.5 overflow-y-auto rounded-lg border border-white/[0.05] bg-black/10 p-2" aria-label="Voice transcript">
          {transcripts.map((entry) => (
            <div key={entry.id} className={`rounded-md px-2 py-1.5 ${entry.speaker === "operator" ? "bg-signal-cyan/[0.06]" : "bg-white/[0.03]"}`}>
              <p className="text-[8px] font-semibold uppercase tracking-wider text-white/35">{entry.speaker === "operator" ? "Operator" : "Aegis"}</p>
              <p className="mt-0.5 text-[10px] leading-relaxed text-white/80">{entry.text}</p>
              {entry.citations.length > 0 && <CitationLinks citations={entry.citations} onCitation={onCitation} />}
            </div>
          ))}
        </div>
      )}
      {pendingCitations.length > 0 && <div className="mt-2"><CitationLinks citations={pendingCitations} onCitation={onCitation} /></div>}
      <p className="mt-2 flex items-center gap-1 text-[8px] text-white/25"><ShieldCheck size={10} /> Escape, Stop, route exit, and connection errors immediately stop local microphone capture.</p>
    </section>
  );
}

function CitationLinks({ citations, onCitation }: { citations: LiveCitation[]; onCitation?: (citation: LiveCitation) => void }) {
  return (
    <div className="mt-1.5 flex flex-wrap gap-1" aria-label="Evidence citations">
      {citations.map((citation) => {
        const route = routeForCitation(citation);
        const action = onCitation ? () => onCitation(citation) : route ? () => window.location.assign(route) : () => applySafeUiCommand({ kind: "focus_health" });
        return <button key={citation.evidenceId} type="button" onClick={action} className="rounded border border-signal-cyan/15 bg-signal-cyan/[0.04] px-1.5 py-0.5 text-[8px] text-signal-cyan/85 hover:bg-signal-cyan/[0.1]" title={`${citation.label} · ${availabilityLabel(citation.availability)} · ${formatFreshness(citation.observedAt)}`}>{citation.label}</button>;
      })}
    </div>
  );
}
