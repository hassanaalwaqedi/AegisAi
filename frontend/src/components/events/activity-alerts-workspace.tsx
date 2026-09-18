"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import {
  AlertTriangle,
  BellRing,
  Camera,
  CheckCircle2,
  ChevronDown,
  CircleAlert,
  CircleOff,
  Clock3,
  ExternalLink,
  Eye,
  Info,
  Search,
  ShieldAlert,
  SlidersHorizontal,
  WifiOff,
} from "lucide-react";

import {
  activityStatusLabel,
  activitySummary,
  buildActivityAlertItems,
  cameraCondition,
  eventObjectLabel,
  eventTimestamp,
  filterActivityAlertItems,
  type ActivityAlertItem,
  type ActivityFilter,
  type ActivityStatus,
} from "@/lib/activity-alerts";
import { appConfig } from "@/lib/config";
import { cn } from "@/lib/utils";
import type { Camera as CameraType, OperationalAlert, RiskEvent } from "@/types";

type ActivityAlertsWorkspaceProps = {
  cameras: CameraType[];
  events: RiskEvent[];
  alerts?: OperationalAlert[];
  isLoading: boolean;
  isUnavailable: boolean;
  camerasUnavailable: boolean;
  onRetry: () => void;
};

const filterLabels: Array<{ id: ActivityFilter; label: string }> = [
  { id: "all", label: "All" },
  { id: "review", label: "Needs review" },
  { id: "high", label: "High priority" },
  { id: "resolved", label: "Resolved" },
  { id: "camera", label: "Camera issues" },
];

export function ActivityAlertsWorkspace({ cameras, events, alerts, isLoading, isUnavailable, camerasUnavailable, onRetry }: ActivityAlertsWorkspaceProps) {
  const t = useTranslations("events");
  const [filter, setFilter] = useState<ActivityFilter>("all");
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null | undefined>(undefined);
  const allItems = useMemo(() => buildActivityAlertItems(cameras, events, alerts), [alerts, cameras, events]);
  const items = useMemo(() => filterActivityAlertItems(allItems, filter, search), [allItems, filter, search]);
  const summary = useMemo(() => activitySummary(allItems), [allItems]);
  const selected = selectedId === null ? null : items.find((item) => item.id === selectedId) ?? items[0] ?? null;
  const hasResolvedSource = allItems.some((item) => item.status === "resolved");

  if (isLoading) return <ActivityLoading />;

  return (
    <section className="events-workspace mx-auto w-full max-w-[1800px] px-4 py-4 sm:px-6 lg:px-8" aria-labelledby="activity-alerts-title">
      <header className="events-page-header">
        <div className="flex items-center gap-3"><span className="camera-title-icon"><BellRing className="h-4 w-4" aria-hidden /></span><h1 id="activity-alerts-title" className="text-xl font-medium tracking-tight text-white">{t("title")}</h1></div>
        {!isUnavailable ? <div className="events-summary" aria-label="Activity summary"><span><i className="bg-amber-300" />{t("needsReview")}<strong>{summary.review}</strong></span><span><i className="bg-rose-400" />{t("highPriority")}<strong>{summary.high}</strong></span></div> : null}
      </header>

      {isUnavailable ? <ActivityUnavailable onRetry={onRetry} /> : (
        <>
          <ActivityToolbar filter={filter} search={search} hasResolvedSource={hasResolvedSource} onFilterChange={setFilter} onSearchChange={setSearch} />
          {camerasUnavailable ? <p className="mt-3 rounded-lg border border-amber-300/20 bg-amber-300/[0.05] px-3 py-2 text-sm text-amber-100">Camera details are temporarily unavailable. Available activity is still shown.</p> : null}
          <div className={cn("events-content", selectedId != null && "has-selection")}>
            <ReviewQueue items={items} filter={filter} selectedId={selected?.id ?? null} onSelect={setSelectedId} />
            <AlertInvestigationPanel key={selected?.id ?? "empty"} item={selected} onBack={() => setSelectedId(null)} />
          </div>
        </>
      )}
    </section>
  );
}

// Kept as an explicit page-level export so other operator surfaces can reuse
// the complete workspace without depending on the route implementation.
export const ActivityAlertsPage = ActivityAlertsWorkspace;

export function ActivityFilterBar({ filter, hasResolvedSource, onFilterChange }: {
  filter: ActivityFilter;
  hasResolvedSource: boolean;
  onFilterChange: (filter: ActivityFilter) => void;
}) {
  return <div className="flex max-w-full gap-1 overflow-x-auto rounded-lg border border-white/10 bg-black/15 p-1" role="tablist" aria-label="Activity filters">
    {filterLabels.filter((item) => item.id !== "resolved" || hasResolvedSource).map((item) => (
      <button key={item.id} type="button" role="tab" aria-selected={filter === item.id} onClick={() => onFilterChange(item.id)} className={cn("inline-flex min-h-9 shrink-0 items-center gap-2 rounded-md px-3 text-sm font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan", filter === item.id ? "bg-signal-cyan/15 text-signal-cyan" : "text-slate-300 hover:bg-white/[0.06] hover:text-white")}>
        {item.id === "camera" ? <SlidersHorizontal className="h-3.5 w-3.5" aria-hidden /> : null}{item.label}
      </button>
    ))}
  </div>;
}

export function ActivityToolbar({ filter, search, hasResolvedSource, onFilterChange, onSearchChange }: {
  filter: ActivityFilter;
  search: string;
  hasResolvedSource: boolean;
  onFilterChange: (filter: ActivityFilter) => void;
  onSearchChange: (value: string) => void;
}) {
  return (
    <div className="events-toolbar">
      <ActivityFilterBar filter={filter} hasResolvedSource={hasResolvedSource} onFilterChange={onFilterChange} />
      <label className="relative block w-full lg:max-w-[260px]">
        <Search className="pointer-events-none absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" aria-hidden />
        <input value={search} onChange={(event) => onSearchChange(event.target.value)} placeholder="Search activity" aria-label="Search activity" className="h-10 w-full rounded-lg border border-white/10 bg-black/20 ps-9 pe-3 text-sm text-white outline-none placeholder:text-slate-500 focus:border-signal-cyan/60 focus:ring-2 focus:ring-signal-cyan/20" />
      </label>
    </div>
  );
}

export function ReviewQueue({ items, filter, selectedId, onSelect }: { items: ActivityAlertItem[]; filter: ActivityFilter; selectedId: string | null; onSelect: (id: string) => void }) {
  const t = useTranslations("events");
  return (
    <aside className="events-queue" aria-labelledby="review-queue-title">
      <div className="events-queue-heading"><h2 id="review-queue-title">{t("simple.activity")}</h2><span>{items.length}</span></div>
      {items.length ? <div className="events-queue-list custom-scrollbar" aria-label="Activity review queue">
        {items.map((item) => <ReviewQueueItem key={item.id} item={item} selected={item.id === selectedId} onSelect={onSelect} />)}
      </div> : <ActivityEmptyState filter={filter} />}
    </aside>
  );
}

export function ReviewQueueItem({ item, selected, onSelect }: { item: ActivityAlertItem; selected: boolean; onSelect: (id: string) => void }) {
  return (
    <button type="button" onClick={() => onSelect(item.id)} aria-current={selected ? "true" : undefined} className={cn("events-queue-item", selected && "is-selected")}>
      <span className={cn("events-item-icon", statusIconTone(item.status))}><StatusIcon status={item.status} /></span>
      <span className="min-w-0 flex-1"><span className="events-item-title">{item.summary}</span><span className="events-item-camera">{item.cameraLabel}{item.location ? ` \u00b7 ${item.location}` : ""}</span><span className="events-item-time">{relativeTime(item.occurredAt)}</span></span>
      <ExternalLink className="h-3.5 w-3.5 shrink-0 text-slate-500" aria-hidden />
    </button>
  );
}

export function AlertInvestigationPanel({ item, onBack }: { item: ActivityAlertItem | null; onBack: () => void }) {
  const locale = useLocale();
  const t = useTranslations("events.simple");
  if (!item) return <section className="events-detail events-detail-empty" aria-label="Alert investigation"><CheckCircle2 className="h-8 w-8 text-slate-500" aria-hidden /><h2>{t("selectActivity")}</h2><p>{t("selectHint")}</p></section>;
  const evidenceId = `evidence-${item.id.replace(/[^a-zA-Z0-9_-]/g, "-")}`;
  const focusHref = item.camera ? `/${locale}/cameras?camera=${encodeURIComponent(item.camera.camera_id)}&view=focus` : null;
  const connectionIssue = ["offline", "delayed", "unavailable"].includes(item.status);

  return (
    <section className="events-detail" aria-labelledby="investigation-title">
      <button type="button" onClick={onBack} className="events-back">{t("back")}</button>
      <div className="events-detail-header">
        <div className="flex items-center gap-2"><span className={cn("h-1.5 w-1.5 rounded-full", statusDotTone(item.status))} /><span>{activityStatusLabel(item.status)}</span></div><time>{relativeTime(item.occurredAt)}</time>
      </div>
      <div className="events-detail-title"><h2 id="investigation-title">{item.cameraLabel}</h2>{item.location ? <p>{item.location}</p> : null}</div>
      <div className="events-story"><h3>{connectionIssue ? t("connectionTitle") : item.summary}</h3><p>{operatorExplanation(item)}</p></div>
      <AlertActionBar focusHref={focusHref} />
      <div className="events-evidence"><AlertEvidencePreview key={item.id} item={item} /></div>
      <details className="events-history"><summary>{t("history")}<ChevronDown className="h-4 w-4" aria-hidden /></summary><section id={evidenceId} tabIndex={-1}><EvidenceTimeline item={item} /></section></details>
      <WhyFlaggedDetailsDrawer item={item} />
    </section>
  );
}

export function AlertEvidencePreview({ item }: { item: ActivityAlertItem }) {
  const [generation, setGeneration] = useState(0);
  const [failed, setFailed] = useState(false);
  const evidenceId = typeof item.event?.event_id === "string" ? item.event.event_id : undefined;
  const hasSavedEvidence = Boolean(evidenceId && item.event?.snapshot_status === "saved");
  const canPreview = hasSavedEvidence || Boolean(item.camera && cameraCondition(item.camera) === "live");
  useEffect(() => {
    if (!canPreview || hasSavedEvidence) return undefined;
    const timer = window.setInterval(() => setGeneration((value) => value + 1), 5_000);
    return () => window.clearInterval(timer);
  }, [canPreview, hasSavedEvidence]);
  if (!canPreview || failed) {
    const copy = item.status === "offline" ? "Camera offline - check connection." : item.status === "delayed" ? "Live image is delayed." : "No visual evidence is available for this activity.";
    return <div className="events-preview-unavailable"><Camera className="h-8 w-8 text-slate-600" aria-hidden /><p className="mt-3 text-sm text-slate-300">{copy}</p>{canPreview && failed ? <button type="button" onClick={() => { setFailed(false); setGeneration((value) => value + 1); }} className="mt-3 text-sm font-medium text-signal-cyan focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan">Retry preview</button> : null}</div>;
  }
  const source = hasSavedEvidence
    ? `${appConfig.apiUrl}/events/evidence/${encodeURIComponent(evidenceId!)}/snapshot`
    : `${appConfig.apiUrl}/cameras/${encodeURIComponent(item.camera!.camera_id)}/snapshot?activity=${generation}`;
  return <div className="events-preview relative aspect-video overflow-hidden rounded-xl border border-white/[0.08] bg-black">
    {/* eslint-disable-next-line @next/next/no-img-element -- snapshots flow through the server-side authenticated proxy. */}
    <img src={source} alt={`${hasSavedEvidence ? "Saved evidence" : "Latest camera image"} from ${item.cameraLabel}`} className="h-full w-full object-contain" onError={() => setFailed(true)} />
    <span className="absolute start-3 top-3 rounded-md border border-signal-cyan/30 bg-command-950/80 px-2 py-1 text-xs font-semibold text-signal-cyan">{hasSavedEvidence ? "Saved evidence" : "Live camera preview"}</span>
  </div>;
}

export function EvidenceTimeline({ item }: { item: ActivityAlertItem }) {
  const timeline = item.relatedEvents.slice().sort((left, right) => eventTimestamp(right) - eventTimestamp(left)).slice(0, 3);
  if (!timeline.length && !item.camera?.runtime.last_frame_time) return <p className="mt-2 text-sm text-slate-400">No visual evidence is available for this activity.</p>;
  return <ol className="mt-3 space-y-3 border-s border-white/10 ps-4">
    {timeline.map((event, index) => <li key={String(event.id ?? event.event_id ?? `${event.timestamp}-${index}`)} className="relative text-sm"><span className="absolute -left-[21px] top-1.5 h-2 w-2 rounded-full bg-signal-cyan" aria-hidden /><p className="font-medium text-slate-200">{timelineCopy(event)}</p><p className="mt-0.5 text-xs text-slate-500">{relativeTime(event.timestamp)}</p></li>)}
    {!timeline.length && item.camera?.runtime.last_frame_time ? <li className="relative text-sm"><span className="absolute -left-[21px] top-1.5 h-2 w-2 rounded-full bg-slate-400" aria-hidden /><p className="font-medium text-slate-200">Latest camera image received</p><p className="mt-0.5 text-xs text-slate-500">{relativeTime(item.camera.runtime.last_frame_time)}</p></li> : null}
  </ol>;
}

export function AlertActionBar({ focusHref, evidenceId }: { focusHref: string | null; evidenceId?: string }) {
  return <div className="events-actions flex flex-wrap gap-2">{focusHref ? <Link href={focusHref} className="inline-flex min-h-10 items-center gap-2 rounded-md bg-signal-cyan px-3 text-sm font-semibold text-command-950 transition hover:bg-cyan-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan"><Camera className="h-4 w-4" aria-hidden />Open camera<ExternalLink className="h-3.5 w-3.5" aria-hidden /></Link> : null}{evidenceId ? <button type="button" onClick={() => document.getElementById(evidenceId)?.focus()} className="inline-flex min-h-10 items-center gap-2 rounded-md border border-white/15 px-3 text-sm font-semibold text-slate-200 transition hover:border-signal-cyan/50 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan"><Eye className="h-4 w-4" aria-hidden />Review evidence</button> : null}</div>;
}

export function WhyFlaggedDetailsDrawer({ item }: { item: ActivityAlertItem }) {
  const [open, setOpen] = useState(false);
  const details = technicalDetails(item);
  if (!details.length) return null;
  return <details open={open} onToggle={(event) => setOpen((event.currentTarget as HTMLDetailsElement).open)} className="rounded-xl border border-white/[0.08] bg-black/15 p-4"><summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-sm font-semibold text-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan">Why did Aegis flag this?<ChevronDown className={cn("h-4 w-4 transition", open && "rotate-180")} aria-hidden /></summary>{open ? <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">{details.map((detail) => <div key={detail.label} className="rounded-lg border border-white/[0.07] bg-white/[0.025] p-3"><dt className="text-xs text-slate-500">{detail.label}</dt><dd className="mt-1 break-words font-medium text-slate-200">{detail.value}</dd></div>)}</dl> : null}</details>;
}

export function ActivityEmptyState({ filter }: { filter: ActivityFilter }) {
  return <div className="flex flex-1 flex-col items-center justify-center px-4 text-center"><CheckCircle2 className="h-7 w-7 text-slate-600" aria-hidden /><p className="mt-3 text-sm font-semibold text-white">{filter === "all" ? "Nothing needs review right now." : "No activity matches this filter."}</p><p className="mt-1 text-sm text-slate-400">New alerts will appear here when reported.</p></div>;
}

function ActivityUnavailable({ onRetry }: { onRetry: () => void }) {
  return <div className="mt-6 rounded-xl border border-eose-400/25 bg-rose-500/[0.06] p-6"><div className="flex items-start gap-3"><WifiOff className="mt-0.5 h-5 w-5 text-rose-300" aria-hidden /><div><h2 className="text-lg font-semibold text-rose-100">Activity is temporarily unavailable.</h2><p className="mt-1 text-sm text-rose-100/75">Try again when the activity service is available.</p><button type="button" onClick={onRetry} className="mt-4 inline-flex min-h-9 items-center rounded-md border border-eose-300/35 px-3 text-sm font-semibold text-rose-100 transition hover:bg-rose-400/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-200">Retry</button></div></div></div>;
}

function ActivityLoading() {
  return <section className="mx-auto w-full max-w-[1800px] px-4 py-6 sm:px-6 lg:px-8" aria-busy="true" aria-label="Loading activity and alerts"><div className="h-10 w-64 animate-pulse rounded bg-white/[0.06]" /><div className="mt-3 h-5 w-96 max-w-full animate-pulse rounded bg-white/[0.04]" /><div className="mt-6 grid gap-4 xl:min-h-[650px] xl:grid-cols-[minmax(310px,0.72fr)_minmax(0,1.45fr)]"><div className="h-[500px] animate-pulse rounded-xl border border-white/10 bg-white/[0.035]" /><div className="h-[500px] animate-pulse rounded-xl border border-white/10 bg-white/[0.035]" /></div></section>;
}

function operatorExplanation(item: ActivityAlertItem) {
  if (item.status === "offline") return "The camera is currently offline. Check the camera connection before reviewing new activity.";
  if (item.status === "delayed") return "The camera is reconnecting or its latest image is delayed.";
  if (item.status === "high") return `A high-priority ${item.event ? eventObjectLabel(item.event).toLowerCase() : "activity"} alert was reported for this camera and should be reviewed promptly.`;
  if (item.status === "resolved") return "This activity has been reviewed.";
  return "Activity from this camera needs attention.";
}

function timelineCopy(event: RiskEvent) {
  const level = String(event.risk_level ?? event.severity ?? event.level ?? "").toUpperCase();
  if (["HIGH", "CRITICAL"].includes(level)) return "High-priority activity reported";
  if (["MEDIUM", "CANDIDATE_MEDIUM", "WARNING"].includes(level)) return "Activity needs attention";
  return "Activity reported";
}

function technicalDetails(item: ActivityAlertItem) {
  const event = item.event;
  const rows: Array<{ label: string; value: string }> = [];
  const add = (label: string, value: unknown) => { if (typeof value === "string" && value.trim()) rows.push({ label, value }); if (typeof value === "number" && Number.isFinite(value)) rows.push({ label, value: String(value) }); };
  add("Recorded time", typeof item.occurredAt === "string" ? item.occurredAt : item.occurredAt ? new Date(item.occurredAt * 1_000).toISOString() : undefined);
  add("Camera reference", event?.camera_id ?? item.camera?.camera_id);
  add("Track reference", event?.track_id);
  add("Event reference", event?.event_id ?? event?.id);
  add("Evidence reference", event?.evidence_type);
  add("Verification state", event?.verification_status);
  add("Confidence", event?.confidence);
  add("Risk score", event?.risk_score ?? event?.edge_risk_score);
  add("Detection source", event?.model_source?.join(", "));
  add("Risk signals", event?.reason_codes?.join(", ") ?? event?.triggers?.join(", "));
  add("Snapshot reference", event?.snapshot_path);
  add("Camera runtime", item.camera?.runtime.status);
  if (item.camera?.runtime.error_message) add("Camera status", "Needs attention");
  return rows;
}

function relativeTime(value?: string | number) {
  if (value === undefined || value === null) return "Time unavailable";
  const timestamp = typeof value === "number" ? value * 1_000 : Date.parse(value);
  if (!Number.isFinite(timestamp)) return "Time unavailable";
  const delta = Date.now() - timestamp;
  if (delta < 0) return new Date(timestamp).toLocaleString();
  if (delta < 60_000) return "Just now";
  if (delta < 3_600_000) return `${Math.floor(delta / 60_000)} min ago`;
  if (delta < 86_400_000) return `${Math.floor(delta / 3_600_000)} hr ago`;
  return new Date(timestamp).toLocaleString();
}

function StatusIcon({ status }: { status: ActivityStatus }) {
  const className = "h-4.5 w-4.5";
  if (status === "high") return <ShieldAlert className={className} aria-hidden />;
  if (status === "attention") return <AlertTriangle className={className} aria-hidden />;
  if (status === "resolved") return <CheckCircle2 className={className} aria-hidden />;
  if (status === "offline") return <CircleOff className={className} aria-hidden />;
  if (status === "delayed") return <Clock3 className={className} aria-hidden />;
  if (status === "monitoring") return <Eye className={className} aria-hidden />;
  return <Info className={className} aria-hidden />;
}

function statusIconTone(status: ActivityStatus) {
  if (status === "high") return "border-eose-300/45 bg-rose-400/10 text-rose-200";
  if (status === "attention" || status === "delayed") return "border-amber-300/45 bg-amber-300/10 text-amber-100";
  if (status === "resolved") return "border-emerald-300/45 bg-emerald-400/10 text-emerald-200";
  return "border-slate-400/35 bg-white/[0.035] text-slate-300";
}

function statusDotTone(status: ActivityStatus) {
  if (status === "high") return "bg-rose-400";
  if (status === "attention" || status === "delayed") return "bg-amber-300";
  if (status === "resolved") return "bg-emerald-400";
  return "bg-slate-400";
}
