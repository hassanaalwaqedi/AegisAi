"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
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
  isNewActivity,
  type ActivityAlertItem,
  type ActivityFilter,
  type ActivityStatus,
} from "@/lib/activity-alerts";
import { appConfig } from "@/lib/config";
import { cn } from "@/lib/utils";
import type { Camera as CameraType, RiskEvent } from "@/types";

type ActivityAlertsWorkspaceProps = {
  cameras: CameraType[];
  events: RiskEvent[];
  isLoading: boolean;
  isUnavailable: boolean;
  camerasUnavailable: boolean;
  onRetry: () => void;
};

type SummaryCardProps = {
  label: string;
  value: number;
  icon: typeof BellRing;
  tone: "danger" | "warning" | "success";
};

const filterLabels: Array<{ id: ActivityFilter; label: string }> = [
  { id: "all", label: "All" },
  { id: "review", label: "Needs review" },
  { id: "high", label: "High priority" },
  { id: "resolved", label: "Resolved" },
  { id: "camera", label: "Camera issues" },
];

export function ActivityAlertsWorkspace({ cameras, events, isLoading, isUnavailable, camerasUnavailable, onRetry }: ActivityAlertsWorkspaceProps) {
  const [filter, setFilter] = useState<ActivityFilter>("all");
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null | undefined>(undefined);
  const allItems = useMemo(() => buildActivityAlertItems(cameras, events), [cameras, events]);
  const items = useMemo(() => filterActivityAlertItems(allItems, filter, search), [allItems, filter, search]);
  const summary = useMemo(() => activitySummary(allItems), [allItems]);
  const selected = selectedId === null ? null : items.find((item) => item.id === selectedId) ?? items[0] ?? null;
  const hasResolvedSource = allItems.some((item) => item.status === "resolved");

  if (isLoading) return <ActivityLoading />;

  return (
    <section className="mx-auto w-full max-w-[1800px] px-4 py-6 sm:px-6 lg:px-8" aria-labelledby="activity-alerts-title">
      <header className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-signal-cyan">Operator workspace</p>
          <h1 id="activity-alerts-title" className="mt-2 text-3xl font-semibold tracking-tight text-white sm:text-4xl">Activity &amp; Alerts</h1>
          <p className="mt-2 text-sm text-slate-400">Review important activity and investigate alerts.</p>
        </div>
        {!isUnavailable ? <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap" aria-label="Activity summary">
          <SummaryCard label="Needs review" value={summary.review} icon={BellRing} tone="warning" />
          <SummaryCard label="High priority" value={summary.high} icon={ShieldAlert} tone="danger" />
          {hasResolvedSource ? <SummaryCard label="Resolved" value={summary.resolved} icon={CheckCircle2} tone="success" /> : null}
        </div> : null}
      </header>

      {isUnavailable ? <ActivityUnavailable onRetry={onRetry} /> : (
        <>
          <ActivityToolbar filter={filter} search={search} hasResolvedSource={hasResolvedSource} onFilterChange={setFilter} onSearchChange={setSearch} />
          {camerasUnavailable ? <p className="mt-3 rounded-lg border border-amber-300/20 bg-amber-300/[0.05] px-3 py-2 text-sm text-amber-100">Camera details are temporarily unavailable. Available activity is still shown.</p> : null}
          <div className="mt-4 grid gap-4 xl:h-[min(68vh,720px)] xl:grid-cols-[minmax(310px,0.72fr)_minmax(0,1.45fr)]">
            <ReviewQueue items={items} filter={filter} selectedId={selected?.id ?? null} onSelect={setSelectedId} />
            <AlertInvestigationPanel item={selected} onBack={() => setSelectedId(null)} />
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
    <div className="mt-6 flex flex-col gap-3 rounded-xl border border-white/10 bg-white/[0.035] p-3 lg:flex-row lg:items-center lg:justify-between">
      <ActivityFilterBar filter={filter} hasResolvedSource={hasResolvedSource} onFilterChange={onFilterChange} />
      <label className="relative block w-full lg:max-w-sm">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" aria-hidden />
        <input value={search} onChange={(event) => onSearchChange(event.target.value)} placeholder="Search activity" aria-label="Search activity" className="h-10 w-full rounded-lg border border-white/10 bg-black/20 pl-9 pr-3 text-sm text-white outline-none placeholder:text-slate-500 focus:border-signal-cyan/60 focus:ring-2 focus:ring-signal-cyan/20" />
      </label>
    </div>
  );
}

export function ReviewQueue({ items, filter, selectedId, onSelect }: { items: ActivityAlertItem[]; filter: ActivityFilter; selectedId: string | null; onSelect: (id: string) => void }) {
  return (
    <aside className="glass-panel flex min-h-[420px] flex-col rounded-xl p-4 sm:p-5 xl:h-full xl:min-h-0" aria-labelledby="review-queue-title">
      <div className="flex items-center justify-between gap-3 border-b border-white/[0.08] pb-4">
        <div><p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Review queue</p><h2 id="review-queue-title" className="mt-1 text-xl font-semibold text-white">Needs review</h2></div>
        {items.length ? <span className="rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-sm font-semibold text-slate-200">{items.length}</span> : null}
      </div>
      {items.length ? <div className="custom-scrollbar mt-4 min-h-0 flex-1 space-y-2 overflow-y-auto pr-1" aria-label="Activity review queue">
        {items.map((item) => <ReviewQueueItem key={item.id} item={item} selected={item.id === selectedId} onSelect={onSelect} />)}
      </div> : <ActivityEmptyState filter={filter} />}
    </aside>
  );
}

export function ReviewQueueItem({ item, selected, onSelect }: { item: ActivityAlertItem; selected: boolean; onSelect: (id: string) => void }) {
  return (
    <button type="button" onClick={() => onSelect(item.id)} aria-current={selected ? "true" : undefined} className={cn("w-full rounded-xl border p-3.5 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan", selected ? "border-signal-cyan/70 bg-signal-cyan/[0.09] shadow-[inset_3px_0_0_#22d3ee]" : `${statusTone(item.status)} hover:border-signal-cyan/35`)}>
      <div className="flex items-start gap-3">
        <span className={cn("mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full border", statusIconTone(item.status))}><StatusIcon status={item.status} /></span>
        <span className="min-w-0 flex-1">
          <span className="flex items-center justify-between gap-2"><span className={cn("text-xs font-semibold", statusTextTone(item.status))}>{activityStatusLabel(item.status)}</span>{isNewActivity(item.occurredAt) ? <span className="rounded bg-signal-cyan/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-signal-cyan">New</span> : null}</span>
          <span className="mt-1 block truncate text-sm font-semibold text-white">{item.cameraLabel}</span>
          <span className="mt-1 block line-clamp-2 text-sm text-slate-300">{item.summary}</span>
          <span className="mt-2 flex items-center justify-between gap-2 text-xs text-slate-500"><span className="truncate">{item.location ?? "Location unavailable"}</span><span className="shrink-0">{relativeTime(item.occurredAt)}</span></span>
        </span>
      </div>
    </button>
  );
}

export function AlertInvestigationPanel({ item, onBack }: { item: ActivityAlertItem | null; onBack: () => void }) {
  if (!item) return <section className="glass-panel flex min-h-[420px] flex-col items-center justify-center rounded-xl p-8 text-center xl:h-full xl:min-h-0" aria-label="Alert investigation"><CircleAlert className="h-8 w-8 text-slate-500" aria-hidden /><h2 className="mt-4 text-xl font-semibold text-white">Select an item to review its details.</h2><p className="mt-2 max-w-sm text-sm leading-6 text-slate-400">Choose activity from the review queue to see available evidence and next actions.</p></section>;
  const evidenceId = `evidence-${item.id.replace(/[^a-zA-Z0-9_-]/g, "-")}`;
  const hasEvidence = Boolean(item.event || item.camera?.runtime.last_frame_time || item.relatedEvents.length);
  const focusHref = item.camera ? `/cameras?camera=${encodeURIComponent(item.camera.camera_id)}&view=focus` : null;

  return (
    <section className="glass-panel min-h-[420px] overflow-hidden rounded-xl xl:h-full xl:min-h-0 xl:overflow-y-auto" aria-labelledby="investigation-title">
      <div className="border-b border-white/[0.08] p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-3"><div><p className={cn("text-sm font-semibold", statusTextTone(item.status))}>{activityStatusLabel(item.status)}</p><h2 id="investigation-title" className="mt-1 text-2xl font-semibold tracking-tight text-white">{item.cameraLabel}</h2>{item.location ? <p className="mt-1 text-sm text-slate-400">{item.location}</p> : null}</div><p className="text-sm text-slate-400">{relativeTime(item.occurredAt)}</p></div>
        <h3 className="mt-5 text-xl font-semibold text-white">{item.summary}</h3>
      </div>
      <div className="grid gap-5 p-5 sm:p-6 2xl:grid-cols-[minmax(0,1fr)_260px]">
        <div className="min-w-0 space-y-5">
          <AlertEvidencePreview item={item} />
          <section><h3 className="text-base font-semibold text-white">What happened</h3><p className="mt-2 text-sm leading-6 text-slate-300">{operatorExplanation(item)}</p></section>
          <section id={evidenceId} tabIndex={-1} className="scroll-mt-24 rounded-xl border border-white/[0.08] bg-black/15 p-4 focus:outline-none focus:ring-2 focus:ring-signal-cyan"><h3 className="text-base font-semibold text-white">Evidence</h3><EvidenceTimeline item={item} /></section>
          <AlertActionBar focusHref={focusHref} evidenceId={hasEvidence ? evidenceId : undefined} />
          <WhyFlaggedDetailsDrawer item={item} />
        </div>
        <aside className="rounded-xl border border-white/[0.08] bg-black/15 p-4"><p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Activity status</p><div className="mt-3 flex items-center gap-2"><span className={cn("h-2.5 w-2.5 rounded-full", statusDotTone(item.status))} aria-hidden /><span className="text-sm font-medium text-white">{activityStatusLabel(item.status)}</span></div>{item.camera?.runtime.last_frame_time ? <p className="mt-4 text-sm leading-6 text-slate-400">Latest camera image: {relativeTime(item.camera.runtime.last_frame_time)}</p> : <p className="mt-4 text-sm leading-6 text-slate-400">Latest camera image time is unavailable.</p>}<button type="button" onClick={onBack} className="mt-5 inline-flex min-h-9 text-sm font-medium text-signal-cyan hover:text-cyan-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan xl:hidden">Back to queue</button></aside>
      </div>
    </section>
  );
}

export function AlertEvidencePreview({ item }: { item: ActivityAlertItem }) {
  const [generation, setGeneration] = useState(0);
  const [failed, setFailed] = useState(false);
  const canPreview = Boolean(item.camera && cameraCondition(item.camera) === "live");
  useEffect(() => {
    if (!canPreview) return undefined;
    const timer = window.setInterval(() => setGeneration((value) => value + 1), 5_000);
    return () => window.clearInterval(timer);
  }, [canPreview]);
  if (!canPreview || !item.camera || failed) {
    const copy = item.status === "offline" ? "Camera offline - check connection." : item.status === "delayed" ? "Live image is delayed." : "No visual evidence is available for this activity.";
    return <div className="flex aspect-video flex-col items-center justify-center rounded-xl border border-white/[0.08] bg-black/35 px-6 text-center"><Camera className="h-8 w-8 text-slate-600" aria-hidden /><p className="mt-3 text-sm text-slate-300">{copy}</p>{canPreview && failed ? <button type="button" onClick={() => { setFailed(false); setGeneration((value) => value + 1); }} className="mt-3 text-sm font-medium text-signal-cyan focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan">Retry preview</button> : null}</div>;
  }
  return <div className="relative aspect-video overflow-hidden rounded-xl border border-white/[0.08] bg-black">
    {/* eslint-disable-next-line @next/next/no-img-element -- snapshots flow through the server-side authenticated proxy. */}
    <img src={`${appConfig.apiUrl}/cameras/${encodeURIComponent(item.camera.camera_id)}/snapshot?activity=${generation}`} alt={`Latest camera image from ${item.cameraLabel}`} className="h-full w-full object-cover" onError={() => setFailed(true)} />
    <span className="absolute left-3 top-3 rounded-md border border-signal-cyan/30 bg-command-950/80 px-2 py-1 text-xs font-semibold text-signal-cyan">Live camera preview</span>
  </div>;
}

export function EvidenceTimeline({ item }: { item: ActivityAlertItem }) {
  const timeline = item.relatedEvents.slice().sort((left, right) => eventTimestamp(right) - eventTimestamp(left)).slice(0, 3);
  if (!timeline.length && !item.camera?.runtime.last_frame_time) return <p className="mt-2 text-sm text-slate-400">No visual evidence is available for this activity.</p>;
  return <ol className="mt-3 space-y-3 border-l border-white/10 pl-4">
    {timeline.map((event, index) => <li key={String(event.id ?? event.event_id ?? `${event.timestamp}-${index}`)} className="relative text-sm"><span className="absolute -left-[21px] top-1.5 h-2 w-2 rounded-full bg-signal-cyan" aria-hidden /><p className="font-medium text-slate-200">{timelineCopy(event)}</p><p className="mt-0.5 text-xs text-slate-500">{relativeTime(event.timestamp)}</p></li>)}
    {!timeline.length && item.camera?.runtime.last_frame_time ? <li className="relative text-sm"><span className="absolute -left-[21px] top-1.5 h-2 w-2 rounded-full bg-slate-400" aria-hidden /><p className="font-medium text-slate-200">Latest camera image received</p><p className="mt-0.5 text-xs text-slate-500">{relativeTime(item.camera.runtime.last_frame_time)}</p></li> : null}
  </ol>;
}

export function AlertActionBar({ focusHref, evidenceId }: { focusHref: string | null; evidenceId?: string }) {
  return <div className="flex flex-wrap gap-2 border-t border-white/[0.08] pt-5">{focusHref ? <Link href={focusHref} className="inline-flex min-h-10 items-center gap-2 rounded-md bg-signal-cyan px-3 text-sm font-semibold text-command-950 transition hover:bg-cyan-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan"><Camera className="h-4 w-4" aria-hidden />Open camera<ExternalLink className="h-3.5 w-3.5" aria-hidden /></Link> : null}{evidenceId ? <button type="button" onClick={() => document.getElementById(evidenceId)?.focus()} className="inline-flex min-h-10 items-center gap-2 rounded-md border border-white/15 px-3 text-sm font-semibold text-slate-200 transition hover:border-signal-cyan/50 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan"><Eye className="h-4 w-4" aria-hidden />Review evidence</button> : null}</div>;
}

export function WhyFlaggedDetailsDrawer({ item }: { item: ActivityAlertItem }) {
  const [open, setOpen] = useState(false);
  const details = technicalDetails(item);
  if (!details.length) return null;
  return <details open={open} onToggle={(event) => setOpen((event.currentTarget as HTMLDetailsElement).open)} className="rounded-xl border border-white/[0.08] bg-black/15 p-4"><summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-sm font-semibold text-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan">Why did Aegis flag this?<ChevronDown className={cn("h-4 w-4 transition", open && "rotate-180")} aria-hidden /></summary>{open ? <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">{details.map((detail) => <div key={detail.label} className="rounded-lg border border-white/[0.07] bg-white/[0.025] p-3"><dt className="text-xs text-slate-500">{detail.label}</dt><dd className="mt-1 break-words font-medium text-slate-200">{detail.value}</dd></div>)}</dl> : null}</details>;
}

export function ActivityEmptyState({ filter }: { filter: ActivityFilter }) {
  return <div className="flex flex-1 flex-col items-center justify-center px-4 text-center"><CheckCircle2 className="h-7 w-7 text-slate-600" aria-hidden /><p className="mt-3 text-sm font-semibold text-white">{filter === "all" ? "Nothing needs review right now." : "No activity matches this filter."}</p><p className="mt-1 text-sm text-slate-400">New operator-relevant activity will appear here when it is reported.</p></div>;
}

function ActivityUnavailable({ onRetry }: { onRetry: () => void }) {
  return <div className="mt-6 rounded-xl border border-rose-400/25 bg-rose-500/[0.06] p-6"><div className="flex items-start gap-3"><WifiOff className="mt-0.5 h-5 w-5 text-rose-300" aria-hidden /><div><h2 className="text-lg font-semibold text-rose-100">Activity is temporarily unavailable.</h2><p className="mt-1 text-sm text-rose-100/75">Try again when the activity service is available.</p><button type="button" onClick={onRetry} className="mt-4 inline-flex min-h-9 items-center rounded-md border border-rose-300/35 px-3 text-sm font-semibold text-rose-100 transition hover:bg-rose-400/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-200">Retry</button></div></div></div>;
}

function ActivityLoading() {
  return <section className="mx-auto w-full max-w-[1800px] px-4 py-6 sm:px-6 lg:px-8" aria-busy="true" aria-label="Loading activity and alerts"><div className="h-10 w-64 animate-pulse rounded bg-white/[0.06]" /><div className="mt-3 h-5 w-96 max-w-full animate-pulse rounded bg-white/[0.04]" /><div className="mt-6 grid gap-4 xl:min-h-[650px] xl:grid-cols-[minmax(310px,0.72fr)_minmax(0,1.45fr)]"><div className="h-[500px] animate-pulse rounded-xl border border-white/10 bg-white/[0.035]" /><div className="h-[500px] animate-pulse rounded-xl border border-white/10 bg-white/[0.035]" /></div></section>;
}

function SummaryCard({ label, value, icon: Icon, tone }: SummaryCardProps) {
  return <div className={cn("flex min-w-[152px] items-center gap-3 rounded-xl border px-4 py-3", tone === "danger" ? "border-rose-400/25 bg-rose-400/[0.055]" : tone === "warning" ? "border-amber-300/25 bg-amber-300/[0.05]" : "border-emerald-300/25 bg-emerald-400/[0.05]")}><span className={cn("flex h-9 w-9 items-center justify-center rounded-full border", tone === "danger" ? "border-rose-300/40 text-rose-200" : tone === "warning" ? "border-amber-300/40 text-amber-100" : "border-emerald-300/40 text-emerald-200")}><Icon className="h-4.5 w-4.5" aria-hidden /></span><span><span className="block text-xs text-slate-400">{label}</span><span className={cn("mt-0.5 block text-2xl font-semibold", tone === "danger" ? "text-rose-200" : tone === "warning" ? "text-amber-100" : "text-emerald-200")}>{value}</span></span></div>;
}

function operatorExplanation(item: ActivityAlertItem) {
  if (item.status === "offline") return "The camera is currently offline. Check the camera connection before reviewing new activity.";
  if (item.status === "delayed") return "The camera is reconnecting or its latest image is delayed.";
  if (item.status === "high") return `A high-priority ${item.event ? eventObjectLabel(item.event).toLowerCase() : "activity"} alert was reported for this camera and should be reviewed promptly.`;
  if (item.status === "resolved") return "This activity was marked resolved by the returned event state.";
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
  add("Source timestamp", typeof item.occurredAt === "string" ? item.occurredAt : item.occurredAt ? new Date(item.occurredAt * 1_000).toISOString() : undefined);
  add("Camera reference", event?.camera_id ?? item.camera?.camera_id);
  add("Track reference", event?.track_id);
  add("Event reference", event?.event_id ?? event?.id);
  add("Evidence reference", event?.evidence_type);
  add("Verification state", event?.verification_status);
  add("Confidence", event?.confidence);
  add("Risk score", event?.risk_score ?? event?.edge_risk_score);
  add("Model source", event?.model_source?.join(", "));
  add("Risk factors", event?.reason_codes?.join(", ") ?? event?.triggers?.join(", "));
  add("Snapshot reference", event?.snapshot_path);
  add("Camera runtime", item.camera?.runtime.status);
  add("Camera diagnostic", item.camera?.runtime.error_message ?? undefined);
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

function statusTone(status: ActivityStatus) {
  if (status === "high") return "border-rose-400/25 bg-rose-400/[0.045]";
  if (status === "attention" || status === "delayed") return "border-amber-300/20 bg-amber-300/[0.04]";
  if (status === "offline" || status === "unavailable") return "border-slate-400/20 bg-white/[0.025]";
  if (status === "resolved") return "border-emerald-300/20 bg-emerald-400/[0.035]";
  return "border-white/[0.08] bg-white/[0.025]";
}

function statusIconTone(status: ActivityStatus) {
  if (status === "high") return "border-rose-300/45 bg-rose-400/10 text-rose-200";
  if (status === "attention" || status === "delayed") return "border-amber-300/45 bg-amber-300/10 text-amber-100";
  if (status === "resolved") return "border-emerald-300/45 bg-emerald-400/10 text-emerald-200";
  return "border-slate-400/35 bg-white/[0.035] text-slate-300";
}

function statusTextTone(status: ActivityStatus) {
  if (status === "high") return "text-rose-200";
  if (status === "attention" || status === "delayed") return "text-amber-100";
  if (status === "resolved") return "text-emerald-200";
  return "text-slate-300";
}

function statusDotTone(status: ActivityStatus) {
  if (status === "high") return "bg-rose-400";
  if (status === "attention" || status === "delayed") return "bg-amber-300";
  if (status === "resolved") return "bg-emerald-400";
  return "bg-slate-400";
}
