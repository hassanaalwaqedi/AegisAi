"use client";

import { ArrowUpRight, Camera, Check, Database, ExternalLink, Radar, Search, ShieldAlert, Waypoints, XCircle } from "lucide-react";
import { useTranslations } from "next-intl";

import { appConfig } from "@/lib/config";
import { formatTime } from "@/lib/utils";
import type { OperatorExecution } from "@/lib/operator-api";
import { recordId, resultRecords } from "@/lib/operator-scene";
import { CameraProjection } from "./camera-projection";

type RecordValue = Record<string, unknown>;

function records(value: unknown): RecordValue[] {
  return Array.isArray(value) ? value.filter((item): item is RecordValue => Boolean(item) && typeof item === "object") : [];
}

function text(value: unknown): string | null {
  return typeof value === "string" && value.length ? value : null;
}

function numeric(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function OperatorResultWorkspace({ execution, onOpen, onFindSimilar, selectedId, onSelect, onRelated }: { execution: OperatorExecution | null; onOpen: (target: string) => void; onFindSimilar: (eventId: string) => void; selectedId?: string | null; onSelect?: (id: string) => void; onRelated?: () => void }) {
  const t = useTranslations("intelligence.operator");
  if (!execution) return <section className="operator-result-empty"><Radar aria-hidden /><h2>{t("workspaceReady")}</h2><p>{t("workspaceHint")}</p></section>;

  return <section className="operator-result" aria-live="polite">
    <header><div><small>{t("resultWorkspace")}</small><h2>{execution.answer}</h2></div><span>{execution.intent}</span></header>
    {execution.error ? <div className="operator-result-error"><XCircle aria-hidden />{execution.error}</div> : null}
    {resultRecords(execution).length > 1 && <div className="projection-selection" aria-label="Displayed results">{resultRecords(execution).map((item, index) => <button key={recordId(item) || index} type="button" aria-pressed={recordId(item) === selectedId} onClick={() => onSelect?.(recordId(item))}>Result {index + 1}</button>)}</div>}
    <ResultBody execution={selectedId && resultRecords(execution).some((item) => recordId(item) === selectedId) ? { ...execution, result: { ...execution.result, ...(execution.panel === "events" ? { events: resultRecords(execution).filter((item) => recordId(item) === selectedId) } : execution.panel === "evidence" ? { evidence: resultRecords(execution).filter((item) => recordId(item) === selectedId) } : execution.panel === "tracks" ? { tracks: resultRecords(execution).filter((item) => recordId(item) === selectedId) } : {}) } } : execution} onFindSimilar={onFindSimilar} />
    {selectedId && execution.panel === "events" && <button type="button" className="operator-open-workspace" onClick={onRelated}>Show related evidence</button>}
    {selectedId && <dl className="projection-details">{Object.entries(resultRecords(execution).find((item) => recordId(item) === selectedId) || {}).filter(([key, value]) => ["event_id", "track_id", "camera_id", "timestamp", "risk_level", "risk_score", "bbox", "position", "zone", "zone_name"].includes(key) && value !== null && value !== undefined).map(([key, value]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{typeof value === "object" ? JSON.stringify(value) : String(value)}</dd></div>)}</dl>}
    <div className="operator-trace"><small>{t("executionTrace")}</small>{execution.trace.map((step) => <span key={`${step.key}-${step.label}`} data-status={step.status}>{step.status === "error" ? <XCircle aria-hidden /> : <Check aria-hidden />}{step.label}</span>)}</div>
    {execution.target ? <button type="button" onClick={() => onOpen(execution.target! + (selectedId && execution.panel === "events" ? `${execution.target!.includes("?") ? "&" : "?"}event=${encodeURIComponent(selectedId)}` : ""))} className="operator-open-workspace"><ExternalLink aria-hidden />{t("openWorkspace")}</button> : null}
  </section>;
}

function ResultBody({ execution, onFindSimilar }: { execution: OperatorExecution; onFindSimilar: (eventId: string) => void }) {
  const t = useTranslations("intelligence.operator");
  if (execution.panel === "camera") {
    const camera = execution.result.camera as RecordValue | undefined;
    if (!camera) return <ResultUnavailable />;
    const cameraId = text(camera.camera_id);
    const online = text(camera.status) === "online";
    return <div className="operator-camera-result">
      {cameraId && online ? <CameraProjection key={cameraId} cameraId={cameraId} label={t("cameraPreviewAlt", { camera: text(camera.name) || cameraId })} /> : <div className="operator-camera-media"><Camera aria-hidden /><span>{t("previewUnavailable")}</span></div>}
      <dl><div><dt>{t("camera")}</dt><dd>{text(camera.name) || cameraId || t("unavailable")}</dd></div><div><dt>{t("runtime")}</dt><dd>{text(camera.status) || t("unavailable")}</dd></div><div><dt>{t("source")}</dt><dd>{text(camera.source_type) || t("unavailable")}</dd></div></dl>
    </div>;
  }
  if (execution.panel === "evidence") {
    const evidence = records(execution.result.evidence);
    return <div className="operator-result-list">{evidence.length ? evidence.map((item) => {
      const id = text(item.event_id)!;
      const snapshot = item.snapshot_available === true;
      return <article key={id}><div className="operator-evidence-thumb">{snapshot ? <>
        {/* eslint-disable-next-line @next/next/no-img-element -- protected saved evidence is served through the authenticated proxy. */}
        <img src={`${appConfig.apiUrl}/events/evidence/${encodeURIComponent(id)}/snapshot`} alt={t("savedEvidenceAlt")} />
      </> : <Database aria-hidden />}</div><div><strong>{text(item.reason) || text(item.event_type) || t("storedEvidence")}</strong><span>{text(item.camera_name) || text(item.camera_id) || t("cameraUnavailable")}</span><small>{text(item.timestamp) ? formatTime(text(item.timestamp)!) : t("timeUnavailable")} · {text(item.risk_level) || t("unclassified")}</small></div><button type="button" onClick={() => onFindSimilar(id)} title={t("findSimilar")}><Search aria-hidden /></button></article>;
    }) : <ResultUnavailable />}</div>;
  }
  if (execution.panel === "events") {
    const events = records(execution.result.events);
    return <div className="operator-result-list">{events.length ? events.map((item, index) => <article key={text(item.event_id) || text(item.id) || String(index)}><EventThumbnail event={item} /><div><strong>{text(item.message) || text(item.event_type) || t("event")}</strong><span>{text(item.camera_id) || t("cameraUnavailable")}</span><small>{text(item.timestamp) ? formatTime(text(item.timestamp)!) : t("timeUnavailable")} · {text(item.risk_level) || t("unclassified")}</small></div></article>) : <ResultUnavailable />}</div>;
  }
  if (execution.panel === "tracks") {
    const tracks = records(execution.result.tracks);
    return <div className="operator-result-list">{tracks.length ? tracks.map((item, index) => <article key={text(item.track_id) || String(index)}><span className="operator-list-icon"><Waypoints aria-hidden /></span><div><strong>{text(item.class_name) || t("track")}</strong><span>{text(item.camera_id) || t("cameraUnavailable")}</span><small>{t("riskScore")}: {numeric(item.risk_score)?.toFixed(2) ?? t("unavailable")}</small></div></article>) : <ResultUnavailable />}</div>;
  }
  if (execution.panel === "analytics" || execution.panel === "system") {
    const context = execution.result.context as RecordValue | undefined;
    const overall = context?.overall as RecordValue | undefined;
    const checks = records(overall?.checks);
    return <div className="operator-health-grid">{checks.map((check, index) => <div key={text(check.name) || String(index)}><span>{text(check.name) || t("service")}</span><strong data-status={text(check.status) || "unavailable"}>{text(check.status) || t("unavailable")}</strong></div>)}</div>;
  }
  return execution.sources.length ? <div className="operator-sources">{execution.sources.map((source, index) => <span key={`${source.type}-${source.id || index}`}><ArrowUpRight aria-hidden />{source.label}</span>)}</div> : null;
}

function ResultUnavailable() {
  const t = useTranslations("intelligence.operator");
  return <div className="operator-result-unavailable"><Database aria-hidden /><span>{t("noResultData")}</span></div>;
}

function EventThumbnail({ event }: { event: RecordValue }) {
  const id = text(event.event_id);
  if (!id || (event.snapshot_available !== true && event.snapshot_status !== "saved")) return <span className="operator-list-icon"><ShieldAlert aria-hidden /></span>;
  return <div className="operator-evidence-thumb">
    {/* eslint-disable-next-line @next/next/no-img-element -- protected evidence snapshot. */}
    <img src={`${appConfig.apiUrl}/events/evidence/${encodeURIComponent(id)}/snapshot`} alt="Saved event evidence" />
  </div>;
}
