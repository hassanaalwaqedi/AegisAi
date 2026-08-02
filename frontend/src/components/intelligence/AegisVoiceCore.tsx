"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { BellOff, BellRing, ExternalLink, Keyboard, MessageSquareText, Mic, RotateCcw, Settings2, ShieldCheck, Square, X } from "lucide-react";

import AIOrb from "@/components/intelligence/AIOrb";
import NodeOrbit from "@/components/intelligence/NodeOrbit";
import { useGeminiLiveVoice } from "@/hooks/useGeminiLiveVoice";
import { useAudibleRiskAlerts, type AudibleRiskAlert } from "@/hooks/useAudibleRiskAlerts";
import { sendChatMessage } from "@/lib/ai-api";
import { fetchLiveCapabilities, type AegisVoiceCoreState, type LiveCitation, type SafeUICommand } from "@/lib/live-voice";
import { availabilityLabel, type Availability, type IntelligenceContext } from "@/lib/intelligence-context";
import type { AgentNode } from "@/types/intelligence";
import {
  applySafeUiCommand,
  nodeForCitation,
  nodeForLiveTool,
  nodeForSafeUiCommand,
  routeForCitation,
  voiceCoreStateLabel,
  type VoiceCapabilityNodeId,
} from "./voice-core";

type ConversationEntry = {
  id: string;
  speaker: "operator" | "aegis";
  text: string;
  citations: LiveCitation[];
};

function coreStateFor(
  voiceState: Exclude<AegisVoiceCoreState, "degraded">,
  voiceError: string | null,
  contextAvailability: Availability,
  capabilityAvailability?: Availability,
): AegisVoiceCoreState {
  if (voiceError || voiceState === "error") return "error";
  if (capabilityAvailability && capabilityAvailability !== "live") return "degraded";
  if (contextAvailability !== "live") return "degraded";
  return voiceState;
}

function commandLabel(command: SafeUICommand) {
  const labels: Record<SafeUICommand["kind"], string> = {
    open_cameras: "Open cameras",
    show_track_evidence: "Open tracking evidence",
    open_semantic_evidence: "Open semantic evidence",
    show_risk_evidence: "Open risk evidence",
    focus_health: "View health checks",
  };
  return labels[command.kind];
}

/**
 * The operator-facing Gemini Live surface. It owns no microphone or websocket
 * resources itself: the existing hook retains those lifecycles and performs
 * stop/unmount/error cleanup. This component only makes that safe capability
 * feel native to the Intelligence Core.
 */
export default function AegisVoiceCore({
  contextAvailability,
  textChatAvailability = "unavailable",
  nodes,
  activeCapability,
  onCapabilityHighlight,
  onOpenOperations,
  intelligenceContext = null,
}: {
  contextAvailability: Availability;
  /** Existing read-only text path, used only when no Live session is open. */
  textChatAvailability?: Availability;
  nodes: AgentNode[];
  activeCapability: VoiceCapabilityNodeId | null;
  onCapabilityHighlight: (node: VoiceCapabilityNodeId | null) => void;
  onOpenOperations?: () => void;
  intelligenceContext?: IntelligenceContext | null;
}) {
  const [capability, setCapability] = useState<Awaited<ReturnType<typeof fetchLiveCapabilities>> | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [textFallbackOpen, setTextFallbackOpen] = useState(false);
  const [typedText, setTypedText] = useState("");
  const [typedError, setTypedError] = useState<string | null>(null);
  const [typedLoading, setTypedLoading] = useState(false);
  const [latestOperatorText, setLatestOperatorText] = useState<string | null>(null);
  const [latestResponse, setLatestResponse] = useState<string | null>(null);
  const [citations, setCitations] = useState<LiveCitation[]>([]);
  const [conversation, setConversation] = useState<ConversationEntry[]>([]);
  const [approvedCommand, setApprovedCommand] = useState<SafeUICommand | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const onSpokenRiskAlert = useCallback((alert: AudibleRiskAlert) => {
    const label = alert.level === "CRITICAL" ? "Critical" : "High Risk";
    setConversation((current) => [
      ...current,
      {
        id: `voice-alert-${alert.id}-${Date.now()}`,
        speaker: "aegis" as const,
        text: `Voice Alert · ${label} — ${alert.panelText}`,
        citations: [],
      },
    ].slice(-20));
  }, []);

  const {
    state: voiceState,
    error: voiceError,
    waveformLevel,
    playbackLevel,
    isCapturing,
    sessionPhase,
    sessionOutcome,
    sessionSecondsRemaining,
    sessionActive,
    startListening,
    sendTypedFallback,
    prepareAudibleAlertAudio,
    speakAudibleRiskAlert,
    stopAudibleRiskAlert,
    stop,
  } = useGeminiLiveVoice({
    onTranscript: (entry) => {
      if (!entry.isFinal) {
        if (entry.speaker === "operator") setLatestOperatorText(entry.text);
        return;
      }
      const entryCitations = entry.speaker === "aegis" ? citations : [];
      setConversation((current) => [
        ...current,
        { id: `${entry.speaker}-${Date.now()}-${current.length}`, speaker: entry.speaker as ConversationEntry["speaker"], text: entry.text, citations: entryCitations },
      ].slice(-20));
      if (entry.speaker === "operator") setLatestOperatorText(entry.text);
      else setLatestResponse(entry.text);
    },
    onCitations: (nextCitations) => {
      setCitations(nextCitations);
      const capabilityNode = nextCitations.map(nodeForCitation).find((node): node is VoiceCapabilityNodeId => node !== null);
      if (capabilityNode) onCapabilityHighlight(capabilityNode);
    },
    onUiCommand: (command) => {
      setApprovedCommand(command);
      const capabilityNode = nodeForSafeUiCommand(command);
      if (capabilityNode) onCapabilityHighlight(capabilityNode);
    },
    onToolActivity: (activity) => {
      const capabilityNode = nodeForLiveTool(activity.tool);
      if (activity.status === "calling" && capabilityNode) onCapabilityHighlight(capabilityNode);
      if (activity.status !== "calling") onCapabilityHighlight(null);
    },
  });

  const geminiAudibleAvailable = contextAvailability === "live" && capability?.availability === "live" && capability.nativeAudio;
  const audibleAlerts = useAudibleRiskAlerts({
    context: intelligenceContext,
    geminiAvailable: geminiAudibleAvailable,
    prepareGeminiAudio: prepareAudibleAlertAudio,
    speakWithGemini: speakAudibleRiskAlert,
    stopGeminiAudio: stopAudibleRiskAlert,
    onSpokenAlert: onSpokenRiskAlert,
  });

  useEffect(() => {
    const controller = new AbortController();
    void fetchLiveCapabilities(controller.signal)
      .then((next) => setCapability(next))
      .catch(() => setCapability(null));
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target;
      if (target instanceof HTMLElement && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName))) return;
      if (event.key === "Escape") {
        stop();
        onCapabilityHighlight(null);
        return;
      }
      if (event.key === "/") {
        event.preventDefault();
        setTextFallbackOpen(true);
        window.setTimeout(() => inputRef.current?.focus(), 0);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onCapabilityHighlight, stop]);

  // The hook already owns resource cleanup. This second, idempotent guard
  // ensures the visual shell cannot leave an active session on route exit.
  useEffect(() => () => stop(), [stop]);

  const coreState = coreStateFor(voiceState, voiceError, contextAvailability, capability?.availability);
  const canUseVoice = contextAvailability === "live" && capability?.availability === "live";
  const unavailableMessage = "Voice unavailable";
  const passiveVoiceState = voiceState === "off" || voiceState === "ready";
  const audibleStateLabel = audibleAlerts.state === "high_risk"
    ? "High Risk"
    : audibleAlerts.state === "attention"
      ? "Attention"
      : audibleAlerts.state === "watching"
        ? "Watching"
        : audibleAlerts.state === "muted"
          ? "Muted"
          : "Unavailable";
  const beaconLabel = isCapturing ? "Listening" : passiveVoiceState ? audibleStateLabel : voiceCoreStateLabel(coreState);

  const toggleListening = () => {
    if (!canUseVoice) return;
    void startListening();
  };

  const submitTextFallback = async (event: FormEvent) => {
    event.preventDefault();
    const message = typedText.trim();
    if (!message) return;
    if (sendTypedFallback(message)) {
      setTypedError(null);
      setLatestOperatorText(message);
      setConversation((current) => [
        ...current,
        { id: `operator-${Date.now()}-${current.length}`, speaker: "operator" as const, text: message, citations: [] },
      ].slice(-20));
      setTypedText("");
      return;
    }

    if (textChatAvailability !== "live") {
      setTypedError("Typed fallback is unavailable until either a Live session or the read-only text service is live.");
      return;
    }

    setTypedLoading(true);
    setTypedError(null);
    try {
      const response = await sendChatMessage(message);
      setLatestOperatorText(message);
      setLatestResponse(response.answer);
      setConversation((current) => [
        ...current,
        { id: `operator-${Date.now()}-${current.length}`, speaker: "operator" as const, text: message, citations: [] },
        { id: `aegis-${Date.now()}-${current.length + 1}`, speaker: "aegis" as const, text: response.answer, citations: [] },
      ].slice(-20));
      setTypedText("");
    } catch (nextError) {
      setTypedError(nextError instanceof Error ? nextError.message : "Typed fallback could not be completed.");
    } finally {
      setTypedLoading(false);
    }
  };

  const stopVoice = () => {
    stop();
    onCapabilityHighlight(null);
  };

  const reconnectVoice = () => {
    if (!canUseVoice) return;
    // A provider or network failure can leave an old browser socket open.
    // Close it before creating one fresh, explicit operator-initiated session.
    stopVoice();
    void startListening();
  };

  return (
    <section className="aegis-voice-surface relative flex w-full flex-col items-center" aria-labelledby="aegis-voice-core-title" data-voice-state={coreState} data-audible-risk={audibleAlerts.visualState}>
      <h2 id="aegis-voice-core-title" className="sr-only">Aegis Voice Intelligence Core</h2>
      <div className="aegis-voice-map relative w-full">
        <div className="aegis-listening-beacon" data-state={coreState} aria-live="polite">
          <span className="aegis-beacon-wave" aria-hidden="true"><i /><i /><i /><i /><i /><i /><i /></span>
          <span className="aegis-beacon-state"><b />{beaconLabel}</span>
        </div>
        <NodeOrbit nodes={nodes} activeNodeId={activeCapability} />
        <div className="aegis-orb-anchor absolute flex items-center justify-center">
          <AIOrb
            contextStatus={contextAvailability}
            voiceState={coreState}
            microphoneLevel={waveformLevel}
            playbackLevel={playbackLevel}
            activeCapability={activeCapability}
            onActivate={toggleListening}
            onListenToggle={toggleListening}
            listeningEnabled={canUseVoice}
            voiceSessionActive={sessionActive}
            audibleRiskState={audibleAlerts.visualState}
          />
        </div>
      </div>

      <div className="aegis-voice-dock">
        {sessionActive && (
          <div className="aegis-session-inline" role="status" aria-live="polite">
            <span>{sessionPhase === "listening" ? "Listening" : sessionPhase === "processing" ? "Thinking" : "Responding"}</span>
            <span className="tabular-nums">{sessionSecondsRemaining}s remaining</span>
            <div role="progressbar" aria-label="Voice session time remaining" aria-valuemin={0} aria-valuemax={60} aria-valuenow={sessionSecondsRemaining}><i style={{ width: `${Math.max(0, Math.min(100, (sessionSecondsRemaining / 60) * 100))}%` }} /></div>
          </div>
        )}

        {(sessionOutcome === "timeout" || sessionOutcome === "cancelled") && <span className="aegis-voice-status-badge" role="status">{sessionOutcome === "timeout" ? "Voice session timed out" : "Listening cancelled"}</span>}
        {latestOperatorText && sessionPhase === "listening" && <span className="sr-only" aria-live="polite">{latestOperatorText}</span>}
        {latestResponse && <button type="button" onClick={() => setDrawerOpen(true)} className="aegis-response-ready" aria-label="Open Conversation and Evidence">Response ready<span className="sr-only">{latestResponse}</span></button>}

        <div className="aegis-compact-controls">
        {sessionActive && (
          <button type="button" onClick={stopVoice} className="aegis-compact-button is-stop" aria-label="Stop listening, microphone capture, and audio playback">
            <Square size={11} /> Cancel
          </button>
        )}
        <button type="button" onClick={() => setTextFallbackOpen((open) => !open)} className="aegis-compact-button" aria-expanded={textFallbackOpen} aria-controls="aegis-voice-text-fallback">
          <MessageSquareText size={12} /> Ask <span>/</span>
        </button>
        <button type="button" onClick={() => void startListening()} disabled={!canUseVoice} title={canUseVoice ? "Start a voice session" : "Voice is unavailable"} className="aegis-compact-button" aria-label={canUseVoice ? "Ask Aegis by voice" : "Voice unavailable"}>
          <Mic size={12} /> Voice
        </button>
        <button
          type="button"
          onClick={() => void audibleAlerts.setEnabled(!audibleAlerts.enabled)}
          disabled={!geminiAudibleAvailable && audibleAlerts.browserFallbackAvailable === false}
          title={audibleAlerts.enabled ? "Mute audible risk alerts" : "Enable audible risk alerts"}
          className="aegis-compact-button aegis-audible-alert-toggle"
          aria-pressed={audibleAlerts.enabled}
          aria-label={audibleAlerts.enabled ? "Mute audible risk alerts" : !geminiAudibleAvailable && audibleAlerts.browserFallbackAvailable === false ? "Audible risk alerts unavailable" : "Enable audible risk alerts"}
        >
          {audibleAlerts.enabled ? <BellRing size={12} /> : <BellOff size={12} />}
        </button>
        {audibleAlerts.state !== "unavailable" && <span className="aegis-audible-alert-state" data-state={audibleAlerts.state} role="status">{audibleStateLabel}</span>}
        {(conversation.length > 0 || citations.length > 0) && (
          <button type="button" onClick={() => setDrawerOpen(true)} className="aegis-compact-button" aria-label="Open Conversation and Evidence">
            <MessageSquareText size={12} /> Evidence
          </button>
        )}
        {onOpenOperations && <button type="button" onClick={onOpenOperations} className="aegis-compact-button" aria-label="Open operational context"><Settings2 size={12} /> Settings</button>}
        </div>

        {coreState === "degraded" && <span className="aegis-voice-status-badge">{unavailableMessage}</span>}
        {voiceError && <span className="aegis-voice-status-badge" role="alert">Voice needs attention<span className="sr-only">: {voiceError}</span></span>}
        {coreState === "error" && !voiceError && <span className="aegis-voice-status-badge" role="alert">Voice unavailable</span>}
        {coreState === "error" && canUseVoice && <button type="button" onClick={reconnectVoice} className="aegis-reconnect"><RotateCcw size={11} />Reconnect voice</button>}

      {textFallbackOpen && (
        <form id="aegis-voice-text-fallback" onSubmit={submitTextFallback} className="aegis-typed-fallback" aria-label="Typed voice fallback">
          <Keyboard size={13} className="ml-1 text-signal-cyan/70" />
          <input ref={inputRef} value={typedText} onChange={(event) => setTypedText(event.target.value)} placeholder="Type a request for Live voice or the read-only text service" className="min-w-0 flex-1 bg-transparent text-[11px] text-white/90 outline-none placeholder:text-white/30" />
          <button type="submit" disabled={typedLoading} className="rounded-md bg-signal-cyan px-2 py-1 text-[10px] font-semibold text-[#061019] disabled:opacity-45">{typedLoading ? "Sending" : "Send"}</button>
          <button type="button" onClick={() => setTextFallbackOpen(false)} className="rounded p-1 text-white/50 hover:text-white" aria-label="Close typed fallback"><X size={13} /></button>
          {typedError && <p className="sr-only" role="alert">{typedError}</p>}
        </form>
      )}
        {typedError && textFallbackOpen && <p className="aegis-typed-error">{typedError}</p>}

      {approvedCommand && (
        <button type="button" onClick={() => applySafeUiCommand(approvedCommand)} className="aegis-command-link">
          <ExternalLink size={11} /> {commandLabel(approvedCommand)}
        </button>
      )}

        <span className="sr-only"><ShieldCheck size={10} /> Microphone stays off until Ask Aegis. Escape stops immediately.</span>
      </div>

      {drawerOpen && (
        <aside className="fixed inset-y-0 right-0 z-50 flex w-[min(420px,calc(100vw-1rem))] flex-col border-l border-signal-cyan/15 bg-[#090f1b]/98 p-4 shadow-[-18px_0_60px_rgba(0,0,0,0.45)]" role="dialog" aria-modal="true" aria-labelledby="conversation-evidence-title">
          <div className="flex items-center justify-between gap-3">
            <div><h3 id="conversation-evidence-title" className="text-sm font-semibold text-white/90">Conversation &amp; Evidence</h3><p className="mt-1 text-[10px] text-white/45">Only this session&apos;s returned transcript and evidence are shown.</p></div>
            <button type="button" onClick={() => setDrawerOpen(false)} className="rounded p-1 text-white/60 hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan" aria-label="Close Conversation and Evidence"><X size={17} /></button>
          </div>
          <div className="custom-scrollbar mt-4 flex-1 space-y-2 overflow-y-auto pr-1">
            {conversation.length === 0 && <p className="rounded-lg border border-dashed border-white/10 p-3 text-[10px] leading-relaxed text-white/40">No voice conversation has been returned for this session.</p>}
            {conversation.map((entry) => (
              <div key={entry.id} className={`rounded-lg border p-2.5 ${entry.speaker === "operator" ? "border-signal-cyan/15 bg-signal-cyan/[0.04]" : "border-white/[0.07] bg-white/[0.03]"}`}>
                <p className="text-[8px] font-semibold uppercase tracking-wider text-white/40">{entry.speaker === "operator" ? "Operator" : "Aegis"}</p>
                <p className="mt-1 text-[11px] leading-relaxed text-white/80">{entry.text}</p>
                {entry.citations.map((citation) => <CitationLink key={citation.evidenceId} citation={citation} />)}
              </div>
            ))}
            {citations.length > 0 && <div className="rounded-lg border border-white/[0.07] bg-white/[0.02] p-2.5"><p className="text-[8px] font-semibold uppercase tracking-wider text-white/40">Latest evidence</p>{citations.map((citation) => <CitationLink key={citation.evidenceId} citation={citation} />)}</div>}
          </div>
        </aside>
      )}
    </section>
  );
}

function CitationLink({ citation }: { citation: LiveCitation }) {
  const route = routeForCitation(citation);
  const label = `${citation.label} · ${availabilityLabel(citation.availability)}`;
  if (!route) return <p className="mt-2 text-[9px] text-white/45">{label}</p>;
  return <a href={route} className="mt-2 inline-flex max-w-full items-center gap-1 rounded border border-signal-cyan/15 bg-signal-cyan/[0.04] px-2 py-1 text-[9px] text-signal-cyan hover:bg-signal-cyan/[0.1]"><ExternalLink size={10} /><span className="truncate">{label}</span></a>;
}
