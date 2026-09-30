"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { Activity, Bot, Camera, Radio, ShieldAlert, type LucideIcon } from "lucide-react";

import { AegisIntelligenceNetwork, type AegisNetworkNodeId } from "@/components/intelligence/aegis-intelligence-network";
import { IntelligenceCore } from "@/components/intelligence/intelligence-core";
import { ProjectionLayer } from "@/components/intelligence/projection-layer";
import VoiceCopilot from "@/components/intelligence/VoiceCopilot";
import { useOperatorController } from "@/hooks/use-operator-controller";
import { useOperatorScene } from "@/hooks/use-operator-scene";
import { defaultProjectionAnchors, stateLabelKey, type OperatorAssetStatus, type ProjectionAnchor, type ProjectionAnchorName } from "@/lib/operator-runtime";
import { useEvidenceSearchStatusQuery } from "@/hooks/use-aegis-api";
import { useSystemMonitor } from "@/hooks/use-system-monitor";
import type { IntelligenceContextState } from "@/hooks/useIntelligenceContext";
import { appConfig } from "@/lib/config";
import type { Availability } from "@/lib/intelligence-context";
import type { AegisVoiceSessionState, SafeUICommand, VoiceState } from "@/lib/live-voice";
const SAFE_TARGET = /^\/(cameras|events|semantic|tracks|analytics)(?:[/?]|$)/;

function countRisk(state: IntelligenceContextState, levels: string[]) {
  return state.context?.alerts.items.filter((item) => item.level && levels.includes(item.level.toUpperCase())).length ?? 0;
}

function normalizeSignals(values: Array<number | null | undefined>) {
  const safe = values.map((value) => Math.max(0, Number(value) || 0));
  const peak = Math.max(1, ...safe);
  return safe.map((value) => value / peak);
}

function riskSignal(level?: string | null) {
  const normalized = level?.toUpperCase();
  if (normalized === "CRITICAL") return 1;
  if (normalized === "HIGH") return .82;
  if (normalized?.includes("MEDIUM")) return .56;
  if (normalized === "LOW") return .28;
  return .12;
}

function nodeForCommand(message: string): AegisNetworkNodeId | null {
  const command = message.toLowerCase();
  if (/camera|cam\b/.test(command)) return "cameras";
  if (/risk|alert|threat/.test(command)) return "risk";
  if (/event/.test(command)) return "events";
  if (/semantic|search/.test(command)) return "semantic";
  if (/evidence|similar/.test(command)) return "evidence";
  if (/track/.test(command)) return "tracking";
  if (/analytic|statistic/.test(command)) return "analytics";
  if (/incident/.test(command)) return "incidents";
  if (/system|health|status/.test(command)) return "system";
  return null;
}

export function IntelligenceCommandCenter({ state }: { state: IntelligenceContextState }) {
  const t = useTranslations("intelligence.operator");
  const locale = useLocale();
  const router = useRouter();
  const index = useEvidenceSearchStatusQuery();
  const [textModeOpen, setTextModeOpen] = useState(false);
  const [textCommand, setTextCommand] = useState("");
  const [voiceState, setVoiceState] = useState<VoiceState>("off");
  const [voiceSessionState, setVoiceSessionState] = useState<AegisVoiceSessionState>("DISABLED");
  const [listeningLevel, setListeningLevel] = useState(0);
  const [speakingLevel, setSpeakingLevel] = useState(0);
  const [capturing, setCapturing] = useState(false);
  const [toolPending, setToolPending] = useState(false);
  const [projectionAnchors, setProjectionAnchors] = useState(defaultProjectionAnchors);
  const [operatorAssetStatus, setOperatorAssetStatus] = useState<OperatorAssetStatus>("checking");
  const [networkRequestNode, setNetworkRequestNode] = useState<AegisNetworkNodeId | null>(null);
  const [bootStep, setBootStep] = useState(0);
  const spokenRequest = useRef("");
  const projectedVoiceTurn = useRef(false);
  const context = state.context;
  const monitor = useSystemMonitor({ context, phase: state.phase, isStale: state.isStale });
  const systemStatus: Availability = context?.overall.status ?? "unavailable";
  const cameraTotal = context?.cameras.totalConfigured ?? context?.cameras.total;
  const activeHighRisk = countRisk(state, ["HIGH", "CRITICAL"]);
  const statusText = (status: Availability) => t(`status.${status}`);
  useEffect(() => {
    const timers = [2000, 4000, 6000, 9000, 11500, 14000].map((delay, index) => window.setTimeout(() => setBootStep(index + 1), delay));
    return () => timers.forEach((timer) => window.clearTimeout(timer));
  }, []);
  const updateProjectionAnchors = useCallback((next: Record<ProjectionAnchorName, ProjectionAnchor>) => {
    setProjectionAnchors((current) => {
      const unchanged = (Object.keys(current) as ProjectionAnchorName[]).every((name) => {
        const before = current[name];
        const after = next[name];
        return before.fromRig === after.fromRig && Math.abs(before.x - after.x) < 0.2 && Math.abs(before.y - after.y) < 0.2;
      });
      return unchanged ? current : next;
    });
  }, []);

  const openTarget = useCallback((target: string) => {
    if (!SAFE_TARGET.test(target)) return;
    router.push(`/${locale}${target}`);
  }, [locale, router]);

  const scene = useOperatorScene(openTarget);
  const { execution, pending, error: commandError, domain: activeDomain, run: runCommand } = scene;
  const operatorTarget = networkRequestNode ?? nodeForCommand(activeDomain ?? "") ?? (activeHighRisk > 0 ? "risk" : null);
  const runtime = useOperatorController({
    voiceState,
    voiceSessionState,
    microphoneActive: capturing,
    commandPending: pending,
    toolPending,
    execution,
    activeDomain,
    warning: activeHighRisk > 0,
    error: commandError,
    listeningLevel,
    speakingLevel,
    target: operatorTarget,
  });
  const presence = stateLabelKey(runtime.state);
  const showOperatorContext = runtime.state !== "IDLE";

  useEffect(() => {
    window.dispatchEvent(new CustomEvent("aegis:domain-focus", {
      detail: { domain: showOperatorContext ? runtime.target : null, state: runtime.state },
    }));
  }, [runtime.state, runtime.target, showOperatorContext]);

  useEffect(() => () => {
    window.dispatchEvent(new CustomEvent("aegis:domain-focus", { detail: { domain: null, state: "IDLE" } }));
  }, []);

  const handleVoiceCommand = useCallback((command: SafeUICommand) => {
    // Voice tools project their results into the same persistent scene.
    if (projectedVoiceTurn.current) return;
    projectedVoiceTurn.current = true;
    const message = spokenRequest.current || (command.kind === "open_cameras" ? `Open camera ${command.cameraId || command.targetId || ""}` : command.kind === "show_track_evidence" ? `Show track ${command.targetId || ""}` : command.kind === "open_semantic_evidence" ? "Find recent evidence" : command.kind === "show_risk_evidence" ? "Show high-risk events" : "Show system status");
    setNetworkRequestNode(nodeForCommand(message));
    void runCommand(message);
  }, [runCommand]);

  const handleUserTurn = useCallback((message: string) => {
    spokenRequest.current = message;
    projectedVoiceTurn.current = false;
    setNetworkRequestNode(nodeForCommand(message));
  }, []);

  const submitTextCommand = useCallback(() => {
    const command = textCommand.trim();
    if (!command || pending) return;
    setTextCommand("");
    setNetworkRequestNode(nodeForCommand(command));
    void runCommand(command);
  }, [pending, runCommand, textCommand]);

  const handleVoiceActivity = useCallback((activity: { state: VoiceState; sessionState: AegisVoiceSessionState; inputLevel: number; outputLevel: number; isCapturing: boolean }) => {
    setVoiceState(activity.state);
    setVoiceSessionState(activity.sessionState);
    setCapturing(activity.isCapturing);
    setListeningLevel(activity.isCapturing ? activity.inputLevel : 0);
    setSpeakingLevel(activity.state === "speaking" ? activity.outputLevel : 0);
    if (activity.state === "off" || activity.state === "error") setToolPending(false);
  }, []);

  const onlineCameras = context?.cameras.online;
  const firstCamera = context?.cameras.items.find((camera) => camera.runtime === "live") || context?.cameras.items[0];
  const coreStateLabel = runtime.state === "ERROR" ? t("requestFailed") : t(`presence.${presence}`);
  const networkMetrics = {
    cameras: typeof onlineCameras === "number" && typeof cameraTotal === "number" ? `${onlineCameras}/${cameraTotal} live` : "Unavailable",
    events: context ? `${context.events.length} recent` : "Unavailable",
    risk: context?.alerts.activeCount == null ? "Unavailable" : `${context.alerts.activeCount} active`,
    tracking: context ? `${context.tracks.length} active` : "Unavailable",
    evidence: index.data ? `${index.data.indexed_evidence} indexed` : "Unavailable",
    semantic: context?.semantic.capability === "live" ? "Live evidence" : context?.semantic.capability ?? "Unavailable",
    analytics: context?.detections.recentCount == null ? "Unavailable" : `${context.detections.recentCount} detections`,
    incidents: context?.incidents.activeCount == null ? "Unavailable" : `${context.incidents.activeCount} active`,
    system: context ? statusText(systemStatus) : "Unavailable",
  };
  const networkStatuses = {
    cameras: context?.cameras.freshness.status ?? "unavailable",
    events: context?.events[0]?.freshness.status ?? "unavailable",
    risk: context?.alerts.freshness.status ?? "unavailable",
    tracking: context?.tracks[0]?.freshness.status ?? context?.pipeline.freshness.status ?? "unavailable",
    evidence: index.data?.state === "ready" ? "live" : "unavailable",
    semantic: context?.semantic.capability ?? "unavailable",
    analytics: context?.detections.freshness.status ?? "unavailable",
    incidents: context?.incidents.capability ?? "unavailable",
    system: systemStatus,
  };
  const networkSignals = {
    events: context?.events.map((event) => event.riskScore ?? .12) ?? [],
    risk: context?.alerts.items.map((alert) => riskSignal(alert.level)) ?? [],
    tracking: context?.tracks.map((track) => track.riskScore ?? .12) ?? [],
    evidence: index.data ? normalizeSignals([index.data.indexed_evidence, index.data.pending_evidence]) : [],
    semantic: context?.semantic.evidence.map((item) => item.serverValidated ? 1 : .45) ?? [],
    analytics: context ? normalizeSignals([context.events.length, context.tracks.length, context.detections.recentCount]) : [],
    incidents: context?.incidents.activeCount == null ? [] : normalizeSignals([context.incidents.activeCount]),
  };
  const cameraPreviewUrl = firstCamera?.runtime === "live" ? `${appConfig.apiUrl}/cameras/${encodeURIComponent(firstCamera.cameraId)}/snapshot?operator=scene` : null;
  const monitorLabel = monitor.kind === "risk"
    ? t("monitor.risk", { count: monitor.count })
    : monitor.kind === "update"
      ? t("monitor.update", { count: monitor.count })
      : t(`monitor.${monitor.kind}`);
  const monitorUrgent = monitor.kind === "risk" || monitor.kind === "degraded";

  return <section className="intelligence-command-center cinematic-intelligence" data-phase={state.phase} data-presence={presence} data-operator-state={runtime.state} data-operator-asset={operatorAssetStatus}>
    <div className="cinematic-space" aria-hidden><i /><i /><i /><i /><i /></div>

    <header className="cinematic-status-strip">
      <h1 className="sr-only">{t("title")}</h1>
      <div className="cinematic-vitals">
        <Vital Icon={Activity} label={t("systemStatus")} value={context ? statusText(systemStatus) : t("unavailable")} status={systemStatus} />
        <Vital Icon={Camera} label={t("liveCameras")} value={typeof onlineCameras === "number" && typeof cameraTotal === "number" ? `${onlineCameras} / ${cameraTotal}` : "—"} status={context?.cameras.freshness.status ?? "unavailable"} />
        <Vital Icon={ShieldAlert} label={t("activeRisk")} value={context?.alerts.activeCount == null ? "—" : String(context.alerts.activeCount)} status={activeHighRisk ? "degraded" : context?.alerts.freshness.status ?? "unavailable"} />
        <Vital Icon={Bot} label={t("aiOperator")} value={coreStateLabel} status={context?.ai.chat ?? "unavailable"} />
      </div>
      <p className="px-3 pb-2 text-center text-[11px] text-slate-400" role="note">{t("humanReviewNote")}</p>
    </header>

    <div className="cinematic-stage" data-boot-step={bootStep}>
      <AegisIntelligenceNetwork runtime={runtime} activeDomain={activeDomain} metrics={networkMetrics} statuses={networkStatuses} signals={networkSignals} cameraPreviewUrl={cameraPreviewUrl} bootStep={bootStep} requestedNode={operatorTarget} onCommand={(command, node) => { setNetworkRequestNode(node); void runCommand(command === "Open camera" ? `Open camera ${firstCamera?.cameraId || ""}` : command); }} />

      <div className="cinematic-center">
        <IntelligenceCore runtime={runtime} status={systemStatus} statusLabel={context ? statusText(systemStatus) : t("unavailable")} stateLabel={coreStateLabel} onAnchors={updateProjectionAnchors} onAssetStatus={setOperatorAssetStatus} />
      </div>

      <div className="aegis-foreground-core" data-state={runtime.state} aria-hidden>
        <i className="aegis-foreground-core-ring" /><i className="aegis-foreground-core-ring" /><i className="aegis-foreground-core-sphere" />
        <span>{Array.from({ length: 10 }, (_, coreParticle) => <i key={coreParticle} style={{ "--core-particle": coreParticle } as React.CSSProperties} />)}</span>
      </div>

      <ProjectionLayer execution={execution} pending={pending} domain={activeDomain} anchorName={runtime.projectionAnchor} anchor={projectionAnchors[runtime.projectionAnchor]} selectedId={scene.selectedId} onSelect={scene.select} onDismiss={scene.dismiss} onOpen={openTarget} onFindSimilar={(id) => void runCommand(t("findSimilarCommand"), id)} onRelated={() => void runCommand("Show related evidence")} />

      <div className="cinematic-command-deck">
        <div className="operator-monitor-notice" data-state={monitor.kind} role={monitorUrgent ? "alert" : "status"} aria-live={monitorUrgent ? "assertive" : "polite"}>
          <Radio aria-hidden />
          <span>{t("monitor.title")}</span>
          <strong>{monitorLabel}</strong>
        </div>
        <VoiceCopilot contextAvailability={context?.ai.voice.handsFree ?? "unavailable"} contextReason={context?.ai.voice.reason} onActivity={handleVoiceActivity} onUiCommand={handleVoiceCommand} onUserTurn={handleUserTurn} sceneContext={scene.sceneContext} onCitation={(citation) => { const id = citation.evidenceId.replace(/^[^:]+:/, ""); void runCommand(citation.kind === "camera" ? `Open camera ${citation.cameraId || id}` : citation.kind === "track" ? `Show track ${id}` : "Show related evidence", id); }} onProjection={(result) => { projectedVoiceTurn.current = true; scene.present(result, spokenRequest.current); }} onToolActivity={(activity) => setToolPending(activity.status === "calling")} />
        <div className="cinematic-state-line" data-visible={showOperatorContext}><span data-presence={presence} /><strong>{coreStateLabel}</strong>{runtime.target ? <><i /><small>{runtime.target}</small></> : null}</div>
        <p className="operator-ambient-cue" data-visible={showOperatorContext} aria-live="polite">{runtime.state === "LISTENING" ? "Listening" : runtime.state === "THINKING" ? "Understanding request" : runtime.state === "EXECUTING" ? `Working with ${runtime.target ?? "Aegis"}` : runtime.state === "SPEAKING" ? "Responding" : runtime.state === "WARNING" || runtime.state === "ERROR" ? "Attention required" : coreStateLabel}</p>
        <button type="button" className="operator-text-mode-toggle" aria-expanded={textModeOpen} aria-controls="operator-text-mode" onClick={() => setTextModeOpen((open) => !open)}>{textModeOpen ? "Close text input" : "Use text instead"}</button>
        {textModeOpen ? <form id="operator-text-mode" className="operator-text-mode" onSubmit={(event) => { event.preventDefault(); submitTextCommand(); }}>
          <label className="sr-only" htmlFor="operator-text-command">Type a command for Aegis</label>
          <input id="operator-text-command" aria-label="Type a command for Aegis" value={textCommand} onChange={(event) => setTextCommand(event.target.value)} placeholder="Type a short command" disabled={pending} autoComplete="off" />
          <button type="submit" disabled={pending || textCommand.trim().length < 2}>{pending ? "Working" : "Execute"}</button>
        </form> : null}
        {commandError ? <p className="operator-command-error" role="alert">{commandError}</p> : null}
      </div>
    </div>
  </section>;
}

function Vital({ Icon, label, value, status }: { Icon: LucideIcon; label: string; value: string; status: Availability }) {
  return <div className="cinematic-vital" tabIndex={0} data-tooltip={`${label}: ${value}`}><Icon aria-hidden /><span className="intelligence-state-dot" data-status={status} /><span className="sr-only">{label}: {value}</span></div>;
}
