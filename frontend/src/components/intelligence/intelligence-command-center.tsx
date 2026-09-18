"use client";

import dynamic from "next/dynamic";
import { useCallback, useRef, useState } from "react";
import { Activity, Camera, Database, LoaderCircle, Mic, Send, ShieldAlert, Sparkles, Waypoints, X } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";

import { IntelligenceCore } from "@/components/intelligence/intelligence-core";
import { ProjectionLayer } from "@/components/intelligence/projection-layer";
import { useOperatorScene } from "@/hooks/use-operator-scene";
import { operatorPresence } from "@/lib/operator-scene";
import { useEvidenceSearchStatusQuery } from "@/hooks/use-aegis-api";
import type { IntelligenceContextState } from "@/hooks/useIntelligenceContext";
import { appConfig } from "@/lib/config";
import type { Availability } from "@/lib/intelligence-context";
import type { SafeUICommand, VoiceState } from "@/lib/live-voice";

const VoiceCopilot = dynamic(() => import("@/components/intelligence/VoiceCopilot"), { ssr: false });
const SAFE_TARGET = /^\/(cameras|events|semantic|tracks|analytics)(?:[/?]|$)/;
const QUICK_KEYS = ["quickCamera", "quickRisk", "quickEvidence", "quickTrack", "quickSummary"] as const;

function countRisk(state: IntelligenceContextState, levels: string[]) {
  return state.context?.alerts.items.filter((item) => item.level && levels.includes(item.level.toUpperCase())).length ?? 0;
}

export function IntelligenceCommandCenter({ state }: { state: IntelligenceContextState }) {
  const t = useTranslations("intelligence.operator");
  const locale = useLocale();
  const router = useRouter();
  const index = useEvidenceSearchStatusQuery();
  const [query, setQuery] = useState("");
  const [voiceOpen, setVoiceOpen] = useState(false);
  const [voiceState, setVoiceState] = useState<VoiceState>("off");
  const [voiceLevel, setVoiceLevel] = useState(0);
  const [capturing, setCapturing] = useState(false);
  const [toolPending, setToolPending] = useState(false);
  const spokenRequest = useRef("");
  const projectedVoiceTurn = useRef(false);
  const context = state.context;
  const systemStatus: Availability = context?.overall.status ?? "unavailable";
  const cameraTotal = context?.cameras.totalConfigured ?? context?.cameras.total;
  const canUseVoice = context?.ai.voice.pushToTalk === "live";
  const activeHighRisk = countRisk(state, ["HIGH", "CRITICAL"]);
  const statusText = (status: Availability) => t(`status.${status}`);

  const openTarget = useCallback((target: string) => {
    if (!SAFE_TARGET.test(target)) return;
    router.push(`/${locale}${target}`);
  }, [locale, router]);

  const scene = useOperatorScene(openTarget);
  const { execution, pending, error: commandError, domain: activeDomain, run: runCommand } = scene;
  const presence = operatorPresence({ voice: voiceState, capturing, pending, toolPending, execution, warning: activeHighRisk > 0 });

  const handleVoiceCommand = useCallback((command: SafeUICommand) => {
    // Voice tools project their results into the same persistent scene.
    if (projectedVoiceTurn.current) return;
    projectedVoiceTurn.current = true;
    const message = spokenRequest.current || (command.kind === "open_cameras" ? `Open camera ${command.cameraId || command.targetId || ""}` : command.kind === "show_track_evidence" ? `Show track ${command.targetId || ""}` : command.kind === "open_semantic_evidence" ? "Find recent evidence" : command.kind === "show_risk_evidence" ? "Show high-risk events" : "Show system status");
    void runCommand(message);
  }, [runCommand]);

  const handleUserTurn = useCallback((message: string) => {
    spokenRequest.current = message;
    projectedVoiceTurn.current = false;
  }, []);

  const handleVoiceActivity = useCallback((activity: { state: VoiceState; inputLevel: number; outputLevel: number; isCapturing: boolean }) => {
    setVoiceState(activity.state);
    setCapturing(activity.isCapturing);
    setVoiceLevel(activity.state === "speaking" ? activity.outputLevel : activity.isCapturing ? activity.inputLevel : 0);
    if (activity.state === "off" || activity.state === "error") setToolPending(false);
  }, []);

  const onlineCameras = context?.cameras.online;
  const firstCamera = context?.cameras.items.find((camera) => camera.runtime === "live") || context?.cameras.items[0];
  const recentEvent = context?.events[0];
  const trackingStatus = context?.pipeline.stages.find((stage) => stage.name.toLowerCase().includes("track"))?.status ?? "unavailable";
  const coreStateLabel = t(`presence.${presence}`);

  return <section className="intelligence-command-center cinematic-intelligence" data-phase={state.phase} data-presence={presence}>
    <div className="cinematic-space" aria-hidden><i /><i /><i /><i /><i /></div>

    <header className="cinematic-status-strip">
      <div className="cinematic-scene-title"><span>{t("eyebrow")}</span><h1>{t("title")}</h1></div>
      <div className="cinematic-vitals">
        <Vital label={t("systemStatus")} value={context ? statusText(systemStatus) : t("unavailable")} status={systemStatus} />
        <Vital label={t("liveCameras")} value={typeof onlineCameras === "number" && typeof cameraTotal === "number" ? `${onlineCameras} / ${cameraTotal}` : "—"} status={context?.cameras.freshness.status ?? "unavailable"} />
        <Vital label={t("activeRisk")} value={context?.alerts.activeCount == null ? "—" : String(context.alerts.activeCount)} status={activeHighRisk ? "degraded" : context?.alerts.freshness.status ?? "unavailable"} />
        <Vital label={t("aiOperator")} value={coreStateLabel} status={context?.ai.chat ?? "unavailable"} />
      </div>
    </header>

    <div className="cinematic-stage">
      <svg className="cinematic-connections" viewBox="0 0 1400 760" preserveAspectRatio="none" aria-hidden>
        <path className={activeDomain === "cameras" ? "is-active" : ""} d="M 610 390 C 500 340 390 292 245 270" />
        <path className={activeDomain === "events" ? "is-active" : ""} d="M 605 430 C 460 480 360 545 205 570" />
        <path className={activeDomain === "evidence" || activeDomain === "tracks" ? "is-active" : ""} d="M 790 390 C 930 330 1035 285 1180 260" />
        <path className={activeDomain === "analytics" || activeDomain === "system" ? "is-active" : ""} d="M 795 435 C 930 500 1040 545 1200 575" />
      </svg>

      <div className="cinematic-left-projection">
        <ContextSurface icon={Camera} eyebrow={t("visionNetwork")} title={t("cameras")} value={typeof onlineCameras === "number" && typeof cameraTotal === "number" ? `${onlineCameras}/${cameraTotal}` : "—"} status={context?.cameras.freshness.status ?? "unavailable"} active={activeDomain === "cameras"} onClick={() => void runCommand(`Open camera ${firstCamera?.cameraId || ""}`)}>
          <div className="cinematic-camera-frame">
            {firstCamera?.runtime === "live" ? <>
              {/* eslint-disable-next-line @next/next/no-img-element -- current authenticated frame is served by the local Aegis proxy. */}
              <img src={`${appConfig.apiUrl}/cameras/${encodeURIComponent(firstCamera.cameraId)}/snapshot?operator=scene`} alt="" />
              <span>LIVE</span>
            </> : <div><Camera aria-hidden /><span>{t("previewUnavailable")}</span></div>}
          </div>
          <p>{firstCamera ? `${firstCamera.name || firstCamera.cameraId} · ${statusText(firstCamera.runtime)}` : t("cameraDataUnavailable")}</p>
        </ContextSurface>
        <button className={`cinematic-beacon ${activeDomain === "events" ? "is-active" : ""}`} type="button" onClick={() => void runCommand("Show high-risk events")}><ShieldAlert aria-hidden /><span>{t("risk")}</span><strong>{context?.alerts.activeCount ?? "—"}</strong></button>
      </div>

      <div className="cinematic-center">
        <IntelligenceCore presence={presence} activeDomain={activeDomain} status={systemStatus} statusLabel={context ? statusText(systemStatus) : t("unavailable")} stateLabel={coreStateLabel} voiceLevel={voiceLevel} />
      </div>

      <div className="cinematic-right-projection">
        <ContextSurface icon={recentEvent ? Activity : Database} eyebrow={recentEvent ? t("recentActivity") : t("semanticIndex")} title={recentEvent ? t("events") : t("evidence")} value={recentEvent ? String(context?.events.length ?? 0) : index.data ? String(index.data.indexed_evidence) : "—"} status={recentEvent?.freshness.status ?? (index.data?.state === "ready" ? "live" : "unavailable")} active={activeDomain === "events" || activeDomain === "evidence"} onClick={() => void runCommand(recentEvent ? "Show recent events" : "Find recent evidence")}>
          <div className="cinematic-signal-visual" aria-hidden>{Array.from({ length: 22 }, (_, indexValue) => <i key={indexValue} />)}</div>
          <p>{recentEvent?.summary || (index.data ? t("pendingEvidence", { count: index.data.pending_evidence }) : t("indexUnavailable"))}</p>
          {recentEvent && index.data ? <span className="cinematic-index-count"><small>{t("evidence")}</small><b>{index.data.indexed_evidence}</b></span> : null}
        </ContextSurface>
        <button className={`cinematic-beacon ${activeDomain === "tracks" ? "is-active" : ""}`} type="button" onClick={() => void runCommand("Show active tracks")}><Waypoints aria-hidden /><span>{t("tracking")}</span><strong>{context?.tracks.length ?? 0}</strong><i data-status={trackingStatus} /></button>
      </div>

      <ProjectionLayer execution={execution} pending={pending} domain={activeDomain} selectedId={scene.selectedId} onSelect={scene.select} onDismiss={scene.dismiss} onOpen={openTarget} onFindSimilar={(id) => void runCommand(t("findSimilarCommand"), id)} onRelated={() => void runCommand("Show related evidence")} />

      <div className="cinematic-command-deck">
        <div className="cinematic-state-line"><span data-presence={presence} /><strong>{coreStateLabel}</strong><i />{activeDomain ? <small>{activeDomain}</small> : <small>{t("awaitingCommand")}</small>}</div>
        <form className="operator-command-bar" onSubmit={(event) => { event.preventDefault(); void runCommand(query); setQuery(""); }}>
          <Sparkles aria-hidden />
          <label className="sr-only" htmlFor="operator-command">{t("commandPlaceholder")}</label>
          <input id="operator-command" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("commandPlaceholder")} disabled={pending} autoComplete="off" />
          <button type="button" className="operator-voice-button" onClick={() => setVoiceOpen(true)} disabled={!canUseVoice} title={canUseVoice ? t("openVoice") : context?.ai.voice.reason || t("voiceUnavailable")}><Mic aria-hidden /></button>
          <button type="submit" disabled={pending || query.trim().length < 2}>{pending ? <LoaderCircle className="animate-spin" aria-hidden /> : <Send aria-hidden />}<span>{pending ? t("executing") : t("send")}</span></button>
        </form>
        {commandError ? <p className="operator-command-error" role="alert">{commandError}</p> : null}
        <div className="operator-suggestions">{QUICK_KEYS.map((key) => <button key={key} type="button" onClick={() => void runCommand(t(key))} disabled={pending}>{t(key)}</button>)}</div>
      </div>

      {voiceOpen ? <div className="operator-voice-dock" role="dialog" aria-modal="false" aria-label={t("voicePanel")}><button type="button" className="operator-voice-close" onClick={() => { setVoiceOpen(false); setVoiceState("off"); setVoiceLevel(0); setCapturing(false); setToolPending(false); }} aria-label={t("closeVoice")}><X aria-hidden /></button><VoiceCopilot contextAvailability={context?.ai.voice.pushToTalk ?? "unavailable"} contextReason={context?.ai.voice.reason} onActivity={handleVoiceActivity} onUiCommand={handleVoiceCommand} onUserTurn={handleUserTurn} sceneContext={scene.sceneContext} onCitation={(citation) => { const id = citation.evidenceId.replace(/^[^:]+:/, ""); void runCommand(citation.kind === "camera" ? `Open camera ${citation.cameraId || id}` : citation.kind === "track" ? `Show track ${id}` : "Show related evidence", id); }} onProjection={(result) => { projectedVoiceTurn.current = true; scene.present(result, spokenRequest.current); }} onToolActivity={(activity) => setToolPending(activity.status === "calling")} /></div> : null}
    </div>
  </section>;
}

function Vital({ label, value, status }: { label: string; value: string; status: Availability }) {
  return <div className="cinematic-vital"><span className="intelligence-state-dot" data-status={status} /><small>{label}</small><strong>{value}</strong></div>;
}

function ContextSurface({ icon: Icon, eyebrow, title, value, status, active, onClick, children }: { icon: LucideIcon; eyebrow: string; title: string; value: string; status: Availability; active: boolean; onClick: () => void; children: React.ReactNode }) {
  return <button type="button" className={`cinematic-context-surface ${active ? "is-active" : ""}`} data-status={status} onClick={onClick}><header><Icon aria-hidden /><span><small>{eyebrow}</small><strong>{title}</strong></span><b>{value}</b></header>{children}<footer><i data-status={status} /><span>{status}</span></footer></button>;
}
