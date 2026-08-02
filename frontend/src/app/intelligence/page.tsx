"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Shield, X } from "lucide-react";

import ActivityFeed from "@/components/intelligence/ActivityFeed";
import AegisVoiceCore from "@/components/intelligence/AegisVoiceCore";
import type { VoiceCapabilityNodeId } from "@/components/intelligence/voice-core";
import { useIntelligenceContext, type IntelligenceContextState } from "@/hooks/useIntelligenceContext";
import {
  availabilityLabel,
  formatFreshness,
  type Availability,
  type IntelligenceContext,
  type IntelligenceHealthCheck,
} from "@/lib/intelligence-context";
import type { AgentNode, IntelligenceFeedItem } from "@/types/intelligence";

const routeAllowlist = new Set(["/cameras", "/analytics", "/semantic", "/tracks", "/events"]);

function isSupportedRoute(href?: string | null) {
  return Boolean(href && routeAllowlist.has(href));
}

function severityForRiskLevel(level?: string | null): IntelligenceFeedItem["severity"] {
  if (level === "CRITICAL") return "critical";
  if (level === "HIGH") return "high";
  if (level === "MEDIUM" || level === "CANDIDATE_MEDIUM") return "medium";
  if (level === "LOW") return "low";
  return "info";
}

function availabilityForPipelineStage(context: IntelligenceContext | null, stageName: string): { availability: Availability; reason?: string } {
  if (!context) return { availability: "unavailable", reason: "The Intelligence context has not returned a pipeline state." };
  const stage = context.pipeline.stages.find((candidate) => candidate.name.toLowerCase().includes(stageName));
  if (!stage) return { availability: "unavailable", reason: `The pipeline did not return a ${stageName} stage state.` };
  return { availability: stage.status, reason: stage.detail ?? undefined };
}

function availabilityForHealthCheck(context: IntelligenceContext | null, checkName: IntelligenceHealthCheck["name"]): { availability: Availability; reason?: string } {
  if (!context) return { availability: "unavailable", reason: "The Intelligence context has not loaded." };
  const check = context.overall.checks.find((candidate) => candidate.name === checkName);
  if (!check) return { availability: "unavailable", reason: `No ${checkName.replace("_", " ")} health check was returned.` };
  return { availability: check.status, reason: check.detail ?? undefined };
}

/** Capability placement mirrors the left-inbound/right-outbound command map. */
export function buildCapabilityNodes(context: IntelligenceContext | null): AgentNode[] {
  const tracking = availabilityForPipelineStage(context, "tracking");
  const risk = availabilityForPipelineStage(context, "risk");
  const eventStream = availabilityForHealthCheck(context, "event_stream");
  const engineering = availabilityForHealthCheck(context, "pipeline");
  const riskColor = typeof context?.alerts.activeCount === "number" && context.alerts.activeCount > 0 ? "#ff4f64" : "#38d6ff";

  return [
    { id: "semantic", label: "Semantic Search", sublabel: "Evidence search", icon: "Search", x: 69, y: 24, color: "#38d6ff", availability: context?.semantic.capability ?? "unavailable", href: "/semantic", labelSide: "right", reason: context?.semantic.reason ?? (context ? undefined : "Semantic capability state is unavailable until context loads.") },
    { id: "memory", label: "Memory", sublabel: "Grounded context", icon: "BrainCircuit", x: 73, y: 38, color: "#38d6ff", availability: context?.ai.evidenceGrounding ?? "unavailable", labelSide: "right", reason: context?.ai.reason ?? (context ? undefined : "Evidence grounding state is unavailable until context loads.") },
    { id: "evidence", label: "Evidence", sublabel: "Validated references", icon: "FileCheck2", x: 89, y: 38, color: "#38d6ff", availability: context?.semantic.freshness.status ?? "unavailable", href: "/semantic", labelSide: "right", mobileHidden: true, reason: context?.semantic.freshness.reason ?? (context ? "Evidence freshness is supplied by the semantic context." : "Evidence state is unavailable until context loads.") },
    { id: "design", label: "Design", sublabel: "AI assistant", icon: "Sparkles", x: 74, y: 60, color: "#38d6ff", availability: context?.ai.chat ?? "unavailable", labelSide: "right", reason: context?.ai.reason ?? (context ? "AI assistant capability state is returned by context." : "AI assistant state is unavailable until context loads.") },
    { id: "engineering", label: "Engineering", sublabel: "Pipeline state", icon: "CircuitBoard", x: 74, y: 73, color: "#38d6ff", availability: engineering.availability, labelSide: "right", reason: engineering.reason },
    { id: "cameras", label: "Cameras", sublabel: "Runtime", icon: "Camera", x: 27, y: 55, color: "#38d6ff", availability: context?.cameras.freshness.status ?? "unavailable", href: "/cameras", labelSide: "left", reason: context?.cameras.freshness.reason ?? (context ? undefined : "Camera runtime state is unavailable until context loads.") },
    { id: "tracking", label: "Tracking", sublabel: "Live objects", icon: "ScanSearch", x: 29, y: 63, color: "#38d6ff", availability: tracking.availability, href: "/tracks", labelSide: "left", reason: tracking.reason },
    { id: "risk", label: "Risk", sublabel: "Risk analysis", icon: "ShieldAlert", x: 32, y: 71, color: riskColor, availability: risk.availability, href: "/analytics", labelSide: "left", reason: risk.reason },
    { id: "events", label: "Events", sublabel: "Event stream", icon: "BellRing", x: 35, y: 79, color: "#38d6ff", availability: eventStream.availability, href: "/events", labelSide: "left", reason: eventStream.reason },
    { id: "ops", label: "Ops", sublabel: "Authorised staffing", icon: "Users", x: 39, y: 87, color: "#38d6ff", availability: "unavailable", labelSide: "left", reason: "No authorised staffing source is connected." },
  ];
}

/** Maps only records that the context server returned; it never creates a status row. */
export function activityFromContext(context: IntelligenceContext | null): IntelligenceFeedItem[] {
  if (!context) return [];

  const alerts = context.alerts.items
    .filter((alert) => alert.evidence.some((reference) => reference.serverValidated))
    .map<IntelligenceFeedItem>((alert) => ({
      id: `alert-${alert.alertId}`,
      type: "alert",
      severity: severityForRiskLevel(alert.level),
      title: alert.level ? `Risk alert · ${alert.level}` : `Risk alert · ${alert.alertId}`,
      description: alert.evidence[0]?.label ?? "Evidence reference unavailable for this alert.",
      observedAt: alert.freshness.observedAt,
      source: `Alert ${alert.alertId}`,
      availability: alert.freshness.status,
    }));
  const events = context.events
    .filter((event) => event.evidence.some((reference) => reference.serverValidated))
    .map<IntelligenceFeedItem>((event) => ({
      id: `event-${event.eventId}`,
      type: "event",
      severity: severityForRiskLevel(event.riskLevel),
      title: `Event ${event.eventId}`,
      description: event.summary,
      observedAt: event.freshness.observedAt,
      source: event.evidence[0]?.label ?? `Event ${event.eventId}`,
      availability: event.freshness.status,
    }));
  const tracks = context.tracks
    .filter((track) => track.evidence.some((reference) => reference.serverValidated))
    .map<IntelligenceFeedItem>((track) => ({
      id: `track-${track.trackId}`,
      type: "track",
      severity: "info",
      title: `${track.className} track ${track.trackId}`,
      description: track.evidence[0]?.label ?? "Evidence reference unavailable for this track.",
      observedAt: track.freshness.observedAt,
      source: track.cameraId ? `Camera ${track.cameraId}` : `Track ${track.trackId}`,
      availability: track.freshness.status,
    }));

  return [...alerts, ...events, ...tracks]
    .sort((left, right) => Date.parse(right.observedAt) - Date.parse(left.observedAt))
    .slice(0, 10);
}

function SuggestionsPanel({ context, phase }: { context: IntelligenceContext | null; phase: IntelligenceContextState["phase"] }) {
  if (!context) {
    return <p className="aegis-tray-empty" role={phase === "loading" ? "status" : undefined}>{phase === "loading" ? "Loading evidence-backed suggestions…" : "Suggestions unavailable because the Intelligence context is unavailable."}</p>;
  }
  if (context.suggestions.length === 0) return <p className="aegis-tray-empty">No evidence-backed suggestions were returned by the context source.</p>;

  return (
    <div className="custom-scrollbar flex max-h-56 flex-col gap-2 overflow-y-auto pr-1">
      {context.suggestions.map((suggestion) => {
        const actionable = suggestion.availability === "live" && isSupportedRoute(suggestion.href);
        const content = <><strong>{suggestion.label}</strong><span>{suggestion.reason}</span><small>Evidence: {suggestion.evidence[0].label}</small></>;
        return actionable ? <a key={suggestion.suggestionId} href={suggestion.href!} className="aegis-tray-suggestion">{content}</a> : <div key={suggestion.suggestionId} className="aegis-tray-suggestion is-muted">{content}</div>;
      })}
    </div>
  );
}

function ContextNotice({ state }: { state: IntelligenceContextState }) {
  if (state.phase === "loading" && !state.context) {
    return <span className="aegis-context-notice" role="status">Context loading<span className="sr-only">. Operational values remain unavailable until the backend responds.</span></span>;
  }
  if (state.phase === "error" && !state.context) {
    return <span className="aegis-context-notice is-attention" role="alert">Context unavailable<span className="sr-only">: {state.error?.message ?? "The backend did not return a context."}</span></span>;
  }
  if (state.phase === "error" && state.context) {
    return <span className="aegis-context-notice is-attention" role="alert">Refresh failed<span className="sr-only">: {state.error?.message ?? "Unknown request failure."}</span></span>;
  }
  if (state.isStale) return <span className="aegis-context-notice is-attention" role="status">Context stale<span className="sr-only">: its server-provided refresh interval has elapsed.</span></span>;
  return null;
}

function DegradedReasons({ context, isStale }: { context: IntelligenceContext | null; isStale: boolean }) {
  if (!context) return <p className="aegis-tray-empty">Health checks are unavailable until the Intelligence context loads.</p>;
  const reasons = [...context.overall.degradedReasons];
  for (const check of context.overall.checks) {
    if (check.status !== "live" && check.detail && !reasons.includes(check.detail)) reasons.push(check.detail);
  }
  if (isStale) reasons.push("The context exceeded its server-provided refresh interval.");
  if (reasons.length === 0) return <p className="aegis-tray-empty">No degraded signals were returned by the current Intelligence context.</p>;

  return <ul className="aegis-tray-reasons">{reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>;
}

function SystemHealthBar({ checks }: { checks: IntelligenceHealthCheck[] | null }) {
  if (!checks || checks.length === 0) return <p className="aegis-tray-empty">Health checks unavailable until the Intelligence context loads.</p>;
  return (
    <div className="aegis-health-grid">
      {checks.map((check) => <div key={check.name} title={check.detail ?? undefined}><span>{check.name.replace("_", " ")}</span><strong data-status={check.status}>{availabilityLabel(check.status)}</strong><small>{formatFreshness(check.observedAt)}</small></div>)}
    </div>
  );
}

function LocalTime() {
  const [currentTime, setCurrentTime] = useState<Date | null>(null);
  useEffect(() => {
    const update = () => setCurrentTime(new Date());
    update();
    const timer = window.setInterval(update, 60_000);
    return () => window.clearInterval(timer);
  }, []);
  return <span className="aegis-local-time">{currentTime?.toLocaleTimeString() ?? "—"}</span>;
}

function OperationsTray({
  open, onClose, state, feedItems, activityEmptyMessage,
}: {
  open: boolean;
  onClose: () => void;
  state: IntelligenceContextState;
  feedItems: IntelligenceFeedItem[];
  activityEmptyMessage: string;
}) {
  if (!open) return null;
  return (
    <aside className="aegis-operations-tray" role="dialog" aria-modal="true" aria-labelledby="operations-tray-title">
      <div className="aegis-tray-header"><div><span>Operational context</span><h2 id="operations-tray-title">Verified signals</h2></div><button type="button" onClick={onClose} aria-label="Close operational context"><X size={16} /></button></div>
      <div className="aegis-tray-scroll custom-scrollbar">
        <section><h3>Evidence-backed suggestions</h3><SuggestionsPanel context={state.context} phase={state.phase} /></section>
        <section><h3>Recent evidence</h3><ActivityFeed items={feedItems} emptyMessage={activityEmptyMessage} /></section>
        <section><h3>Degraded signals</h3><DegradedReasons context={state.context} isStale={state.isStale} /></section>
        <section id="intelligence-health-panel"><h3>Source health</h3><SystemHealthBar checks={state.context?.overall.checks ?? null} /></section>
      </div>
    </aside>
  );
}

/** The visual map is intentionally sparse in copy; detail remains available from Settings. */
export function IntelligencePageContent({ state }: { state: IntelligenceContextState }) {
  const context = state.context;
  const nodes = useMemo(() => buildCapabilityNodes(context), [context]);
  const feedItems = useMemo(() => activityFromContext(context), [context]);
  const [activeCapability, setActiveCapability] = useState<VoiceCapabilityNodeId | null>(null);
  const [operationsOpen, setOperationsOpen] = useState(false);
  const activityEmptyMessage = !context
    ? state.phase === "loading" ? "Loading recent evidence from the Intelligence context." : "Recent evidence unavailable because the Intelligence context is unavailable."
    : "No alerts, events, or tracks were returned by the current Intelligence context.";

  return (
    <div className="aegis-intelligence-page min-h-screen" data-state={state.phase}>
      <header className="aegis-intelligence-header">
        <h1 className="sr-only">Aegis Intelligence</h1>
        <div className="aegis-brand-lockup"><span className="aegis-brand-shield"><Shield size={22} /></span><span><strong>AEGIS</strong><small>AEGISAI INTELLIGENCE</small></span></div>
        <div className="aegis-header-status"><ContextNotice state={state} /><span className="aegis-secure-state"><Shield size={11} /> {context ? availabilityLabel(context.overall.status) : "Unavailable"}</span><LocalTime /></div>
      </header>
      <main className="aegis-intelligence-main">
        <section className="aegis-command-stage" aria-label="Aegis intelligence command surface">
          <div className="aegis-stage-grid" aria-hidden="true" />
          <AegisVoiceCore
            contextAvailability={context?.ai.voice.handsFree ?? "unavailable"}
            textChatAvailability={context?.ai.chat ?? "unavailable"}
            nodes={nodes}
            activeCapability={activeCapability}
            onCapabilityHighlight={setActiveCapability}
            onOpenOperations={() => setOperationsOpen(true)}
            intelligenceContext={context}
          />
        </section>
      </main>
      <OperationsTray open={operationsOpen} onClose={() => setOperationsOpen(false)} state={state} feedItems={feedItems} activityEmptyMessage={activityEmptyMessage} />
    </div>
  );
}

export default function IntelligencePage() {
  return <IntelligencePageContent state={useIntelligenceContext()} />;
}
