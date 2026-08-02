"use client";

import type { ReactNode } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  Camera,
  CheckCircle2,
  ChevronRight,
  CircleAlert,
  CircleOff,
  Clock3,
  Expand,
  Eye,
  Info,
  LoaderCircle,
  ShieldAlert,
  ShieldCheck,
  Video,
  WifiOff,
} from "lucide-react";

import { appConfig } from "@/lib/config";
import { cn, formatTime } from "@/lib/utils";
import type { Camera as CameraType, RiskEvent, StatusResponse } from "@/types";

type CameraCondition = "live" | "delayed" | "offline" | "unavailable";
type ReviewKind = "alert" | "offline" | "delayed";

type ReviewItem = {
  camera: CameraType;
  event?: RiskEvent;
  kind: ReviewKind;
  priority: number;
  summary: string;
  timestamp?: string | number;
};

const STATUS_ACTION_CLASS = "inline-flex min-h-10 items-center gap-1 rounded-md border border-white/10 bg-command-950/40 px-3 text-sm font-semibold text-slate-100 transition hover:border-signal-cyan/60 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan";

type OperatorDashboardProps = {
  cameras: CameraType[];
  events: RiskEvent[];
  status?: StatusResponse;
  isLoading: boolean;
  isUnavailable: boolean;
  onRetry: () => void;
};

function cameraName(camera: CameraType) {
  if (camera.name?.trim()) return camera.name.trim();
  const numericSuffix = camera.camera_id.match(/(\d+)$/)?.[1];
  return numericSuffix ? `Camera ${numericSuffix}` : "Registered camera";
}

function cameraCondition(camera: CameraType): CameraCondition {
  const runtime = camera.runtime;
  if (["offline", "error", "stopped"].includes(runtime.status)) return "offline";
  if (runtime.status === "reconnecting") return "delayed";
  if (runtime.status === "online" && runtime.running) return "live";
  return "unavailable";
}

function conditionLabel(condition: CameraCondition) {
  if (condition === "live") return "Live";
  if (condition === "delayed") return "Delayed";
  if (condition === "offline") return "Offline";
  return "Unavailable";
}

function priorityFromEvent(event: RiskEvent) {
  const level = String(event.risk_level ?? event.severity ?? event.level ?? "").toUpperCase();
  if (level === "CRITICAL") return 3;
  if (level === "HIGH") return 2;
  if (["MEDIUM", "CANDIDATE_MEDIUM", "WARNING"].includes(level)) return 1;
  return 0;
}

function eventTime(event?: RiskEvent) {
  if (!event?.timestamp) return 0;
  if (typeof event.timestamp === "number") return event.timestamp * 1_000;
  return Date.parse(event.timestamp) || 0;
}

function eventSummary(event: RiskEvent) {
  const object = String(event.object_class ?? event.object_type ?? event.class_name ?? "").trim().toLowerCase();
  const friendlyObject = ["person", "vehicle", "car", "bus", "truck", "motorcycle", "bicycle"].includes(object)
    ? object.replace(/^./, (letter) => letter.toUpperCase())
    : "Activity";
  return priorityFromEvent(event) >= 2 ? "High-priority activity needs review" : `${friendlyObject} activity needs review`;
}

function buildReviewItems(cameras: CameraType[], events: RiskEvent[]) {
  const byId = new Map(cameras.map((camera) => [camera.camera_id, camera]));
  const items = new Map<string, ReviewItem>();
  const add = (item: ReviewItem) => {
    const existing = items.get(item.camera.camera_id);
    if (!existing || item.priority > existing.priority || (item.priority === existing.priority && eventTime(item.event) > eventTime(existing.event))) {
      items.set(item.camera.camera_id, item);
    }
  };

  for (const event of events) {
    const priority = priorityFromEvent(event);
    const camera = event.camera_id ? byId.get(event.camera_id) : undefined;
    if (!camera || priority === 0) continue;
    add({ camera, event, kind: "alert", priority, summary: eventSummary(event), timestamp: event.timestamp });
  }

  for (const camera of cameras) {
    const condition = cameraCondition(camera);
    if (condition === "offline") add({ camera, kind: "offline", priority: 2, summary: "Camera offline", timestamp: camera.runtime.last_frame_time ?? undefined });
    if (condition === "delayed") add({ camera, kind: "delayed", priority: 1, summary: "Live image is delayed", timestamp: camera.runtime.last_frame_time ?? undefined });
  }

  return Array.from(items.values()).sort((left, right) => right.priority - left.priority || eventTime(right.event) - eventTime(left.event));
}

function cameraCounts(cameras: CameraType[], reviewItems: ReviewItem[]) {
  const attentionIds = new Set(reviewItems.map((item) => item.camera.camera_id));
  const conditions = cameras.map(cameraCondition);
  return {
    total: cameras.length,
    live: conditions.filter((condition) => condition === "live").length,
    attention: cameras.filter((camera) => attentionIds.has(camera.camera_id) && cameraCondition(camera) !== "offline").length,
    offline: conditions.filter((condition) => condition === "offline").length,
  };
}

function focusCamera(cameras: CameraType[], reviewItems: ReviewItem[]) {
  return reviewItems[0]?.camera ?? cameras.find((camera) => cameraCondition(camera) === "live") ?? cameras[0];
}

function focusHref(camera: CameraType) {
  return `/cameras?camera=${encodeURIComponent(camera.camera_id)}&view=focus`;
}

export function OperatorDashboard({ cameras, events, status, isLoading, isUnavailable, onRetry }: OperatorDashboardProps) {
  const reviewItems = useMemo(() => buildReviewItems(cameras, events), [cameras, events]);
  const counts = useMemo(() => cameraCounts(cameras, reviewItems), [cameras, reviewItems]);
  const selectedCamera = useMemo(() => focusCamera(cameras, reviewItems), [cameras, reviewItems]);
  const systemDegraded = status?.system?.running === false;

  return (
    <section className="mx-auto w-full max-w-[1800px] px-4 py-6 sm:px-6 lg:px-8">
      <header className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-slate-400">Security overview</p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight text-white sm:text-4xl">Operations dashboard</h1>
        </div>
        <Link href="/cameras" className="inline-flex min-h-10 items-center gap-2 rounded-md border border-white/10 px-3 text-sm font-semibold text-slate-200 transition hover:border-signal-cyan/50 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan">
          <Camera className="h-4 w-4" aria-hidden />Open camera wall
        </Link>
      </header>

      {isLoading ? <DashboardLoading /> : null}
      {!isLoading ? (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1.45fr)_minmax(330px,0.7fr)] xl:items-start">
          <OperationalStatus
            cameras={cameras}
            reviewItems={reviewItems}
            liveCount={counts.live}
            systemDegraded={systemDegraded}
            unavailable={isUnavailable}
            onRetry={onRetry}
          />
          <NeedsReview items={reviewItems} unavailable={isUnavailable} />
          <LiveCameraFocus camera={selectedCamera} unavailable={isUnavailable} />
          <CameraOverview cameras={cameras} counts={counts} reviewItems={reviewItems} unavailable={isUnavailable} />
          <RecentActivity items={reviewItems} unavailable={isUnavailable} />
          <DashboardDiagnostics status={status} cameras={cameras} events={events} unavailable={isUnavailable} />
        </div>
      ) : null}
    </section>
  );
}

function OperationalStatus({ cameras, reviewItems, liveCount, systemDegraded, unavailable, onRetry }: { cameras: CameraType[]; reviewItems: ReviewItem[]; liveCount: number; systemDegraded: boolean; unavailable: boolean; onRetry: () => void }) {
  let title = "All clear";
  let detail = "No urgent activity needs review.";
  let tone: "good" | "attention" | "high" | "unavailable" = "good";
  let action: ReactNode = <Link href="/cameras" className={STATUS_ACTION_CLASS}>Open camera wall<ChevronRight className="h-4 w-4" aria-hidden /></Link>;

  if (unavailable) {
    title = "System unavailable";
    detail = "Live status is temporarily unavailable.";
    tone = "unavailable";
    action = <button type="button" onClick={onRetry} className={STATUS_ACTION_CLASS}>Retry<ChevronRight className="h-4 w-4" aria-hidden /></button>;
  } else if (cameras.length === 0) {
    title = "No cameras connected";
    detail = "Add a camera to begin monitoring.";
    tone = "attention";
    action = <Link href="/cameras" className={STATUS_ACTION_CLASS}>Add camera<ChevronRight className="h-4 w-4" aria-hidden /></Link>;
  } else if (systemDegraded) {
    title = "Needs attention";
    detail = "Live service needs review.";
    tone = "attention";
  } else if (reviewItems[0]?.priority === 3) {
    title = "High priority";
    detail = "Immediate review recommended.";
    tone = "high";
    action = <Link href={focusHref(reviewItems[0].camera)} className={STATUS_ACTION_CLASS}>Review alerts<ChevronRight className="h-4 w-4" aria-hidden /></Link>;
  } else if (reviewItems.length > 0) {
    title = "Needs attention";
    detail = `${reviewItems.length} ${reviewItems.length === 1 ? "item needs" : "items need"} review.`;
    tone = "attention";
    action = <Link href={focusHref(reviewItems[0].camera)} className={STATUS_ACTION_CLASS}>Review alerts<ChevronRight className="h-4 w-4" aria-hidden /></Link>;
  } else if (liveCount === 0) {
    title = "Needs attention";
    detail = "No live camera is available.";
    tone = "attention";
  }

  const Icon = tone === "good" ? ShieldCheck : tone === "high" ? ShieldAlert : tone === "unavailable" ? WifiOff : CircleAlert;
  return <section className={cn("glass-panel rounded-xl p-5 sm:p-6 xl:col-start-1 xl:row-start-1", tone === "good" ? "border-emerald-300/25" : tone === "high" ? "border-rose-300/35" : tone === "attention" ? "border-amber-300/30" : "border-rose-300/30")} aria-labelledby="operational-status-title"><div className="flex flex-wrap items-start justify-between gap-4"><div className="flex items-start gap-4"><span className={cn("flex h-12 w-12 shrink-0 items-center justify-center rounded-lg border", tone === "good" ? "border-emerald-300/30 bg-emerald-400/10 text-emerald-200" : tone === "high" ? "border-rose-300/30 bg-rose-400/10 text-rose-100" : tone === "attention" ? "border-amber-300/30 bg-amber-300/10 text-amber-100" : "border-rose-300/30 bg-rose-400/10 text-rose-100")}><Icon className="h-6 w-6" aria-hidden /></span><div><p className="text-sm font-medium text-slate-400">Current status</p><h2 id="operational-status-title" className="mt-1 text-2xl font-semibold text-white">{title}</h2><p className="mt-1 text-sm text-slate-300">{detail}</p></div></div>{action}</div></section>;
}

function LiveCameraFocus({ camera, unavailable }: { camera?: CameraType; unavailable: boolean }) {
  const panelRef = useRef<HTMLElement>(null);
  if (unavailable) return <section className="glass-panel rounded-xl p-6 xl:col-start-1 xl:row-start-2" aria-labelledby="live-view-title"><p className="text-sm font-medium text-slate-400">Live view</p><h2 id="live-view-title" className="mt-1 text-xl font-semibold text-white">Live data is temporarily unavailable.</h2><button type="button" className="mt-5 inline-flex min-h-10 items-center gap-2 rounded-md border border-white/10 px-3 text-sm font-semibold text-slate-200" disabled>Preview unavailable</button></section>;
  if (!camera) return <section className="glass-panel rounded-xl p-6 xl:col-start-1 xl:row-start-2" aria-labelledby="live-view-title"><p className="text-sm font-medium text-slate-400">Live view</p><h2 id="live-view-title" className="mt-1 text-xl font-semibold text-white">No live camera available.</h2><p className="mt-2 text-sm text-slate-400">Open the camera wall to register or review sources.</p><Link href="/cameras" className="mt-5 inline-flex min-h-10 items-center gap-2 rounded-md bg-signal-cyan px-3 text-sm font-semibold text-command-950">Open camera wall<ChevronRight className="h-4 w-4" aria-hidden /></Link></section>;

  const condition = cameraCondition(camera);
  const canPreview = condition === "live";
  const unavailableCopy = condition === "offline" ? "Camera offline — check connection." : condition === "delayed" ? "Live image is delayed." : "Live data is temporarily unavailable.";
  return <section ref={panelRef} className="glass-panel overflow-hidden rounded-xl xl:col-start-1 xl:row-start-2" aria-labelledby="live-view-title"><div className="flex flex-wrap items-start justify-between gap-4 p-5"><div><p className="text-sm font-medium text-slate-400">Live view</p><div className="mt-1 flex flex-wrap items-center gap-2"><h2 id="live-view-title" className="text-xl font-semibold text-white">{cameraName(camera)}</h2><CameraStatus condition={condition} /></div><p className="mt-1 text-sm text-slate-400">{camera.runtime.last_frame_time ? `Updated ${formatTime(camera.runtime.last_frame_time)}` : "Update time unavailable"}</p></div><button type="button" onClick={() => void panelRef.current?.requestFullscreen?.()} className="inline-flex min-h-9 items-center gap-2 rounded-md border border-white/10 px-3 text-sm font-medium text-slate-200 transition hover:border-signal-cyan/50 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan"><Expand className="h-4 w-4" aria-hidden />Fullscreen</button></div><div className="relative aspect-video bg-black">{canPreview ? <DashboardSnapshot camera={camera} className="h-full w-full object-cover" /> : <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-gradient-to-br from-command-900 to-black text-center text-sm text-slate-300"><Video className="h-8 w-8 text-slate-600" aria-hidden />{unavailableCopy}</div>}</div><div className="flex flex-wrap gap-2 border-t border-white/10 p-4"><Link href={focusHref(camera)} className="inline-flex min-h-10 items-center gap-2 rounded-md bg-signal-cyan px-3 text-sm font-semibold text-command-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan"><Camera className="h-4 w-4" aria-hidden />Open camera wall</Link><Link href={focusHref(camera)} className="inline-flex min-h-10 items-center gap-2 rounded-md border border-white/10 px-3 text-sm font-semibold text-slate-200 transition hover:border-signal-cyan/50 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan"><Eye className="h-4 w-4" aria-hidden />View details</Link></div></section>;
}

function NeedsReview({ items, unavailable }: { items: ReviewItem[]; unavailable: boolean }) {
  return <section className="glass-panel rounded-xl p-5 xl:col-start-2 xl:row-start-1 xl:row-span-2" aria-labelledby="needs-review-title"><div className="flex items-center justify-between gap-3"><div><p className="text-sm font-medium text-slate-400">Priority queue</p><h2 id="needs-review-title" className="mt-1 text-xl font-semibold text-white">Needs review</h2></div>{items.length ? <span className="rounded-full bg-amber-300/10 px-2.5 py-1 text-sm font-semibold text-amber-100">{items.length}</span> : null}</div>{unavailable ? <p className="mt-5 text-sm text-slate-400">Live data is temporarily unavailable.</p> : items.length === 0 ? <p className="mt-5 text-sm text-slate-400">Nothing needs review right now.</p> : <div className="mt-4 space-y-3">{items.slice(0, 5).map((item) => <ReviewCard key={item.camera.camera_id} item={item} />)}</div>}</section>;
}

function ReviewCard({ item }: { item: ReviewItem }) {
  const Icon = item.kind === "offline" ? CircleOff : item.priority >= 2 ? AlertTriangle : Clock3;
  const tone = item.kind === "offline" ? "border-slate-400/25 bg-white/[0.035] text-slate-200" : item.priority >= 2 ? "border-rose-300/30 bg-rose-400/[0.06] text-rose-100" : "border-amber-300/30 bg-amber-300/[0.06] text-amber-100";
  return <article className={cn("rounded-lg border p-3.5", tone)}><div className="flex gap-3"><span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-command-950/45"><Icon className="h-4 w-4" aria-hidden /></span><div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold text-white">{cameraName(item.camera)}</p><p className="mt-1 text-sm text-slate-300">{item.summary}</p><p className="mt-1 text-xs text-slate-400">{item.timestamp ? displayTime(item.timestamp) : "Time unavailable"}</p><div className="mt-3 flex flex-wrap gap-2"><Link href={focusHref(item.camera)} className="inline-flex min-h-8 flex-1 items-center justify-center rounded-md border border-signal-cyan/60 px-2 text-xs font-semibold text-signal-cyan transition hover:bg-signal-cyan/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan">Review</Link>{item.event ? <details className="group relative"><summary className="inline-flex min-h-8 cursor-pointer list-none items-center rounded-md border border-white/10 px-2 text-xs font-semibold text-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan">Why did Aegis flag this?</summary><div className="absolute right-0 z-10 mt-2 w-72 rounded-md border border-white/10 bg-command-950 p-3 text-xs leading-relaxed text-slate-300 shadow-xl">{item.event.explanation ?? item.event.description ?? "An evidence explanation was not returned for this alert."}</div></details> : null}</div></div></div></article>;
}

function CameraOverview({ cameras, counts, reviewItems, unavailable }: { cameras: CameraType[]; counts: { total: number; live: number; attention: number; offline: number }; reviewItems: ReviewItem[]; unavailable: boolean }) {
  const attentionIds = new Set(reviewItems.map((item) => item.camera.camera_id));
  const previewCameras = cameras.slice(0, 4);
  return <section className="glass-panel rounded-xl p-5 xl:col-start-1 xl:row-start-3" aria-labelledby="camera-overview-title"><div className="flex flex-wrap items-end justify-between gap-3"><div><p className="text-sm font-medium text-slate-400">Camera overview</p><h2 id="camera-overview-title" className="mt-1 text-xl font-semibold text-white">Cameras</h2></div><Link href="/cameras" className="inline-flex min-h-9 items-center gap-1 text-sm font-semibold text-signal-cyan hover:text-cyan-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan">View all cameras<ChevronRight className="h-4 w-4" aria-hidden /></Link></div>{unavailable ? <p className="mt-5 text-sm text-slate-400">Live camera data is temporarily unavailable.</p> : <><div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4"><CountPill label="total" value={counts.total} /><CountPill label="live" value={counts.live} tone="good" /><CountPill label="need attention" value={counts.attention} tone="attention" /><CountPill label="offline" value={counts.offline} tone="offline" /></div>{cameras.length === 0 ? <p className="mt-5 text-sm text-slate-400">No cameras connected yet.</p> : <div className="mt-4 grid gap-3 sm:grid-cols-2 2xl:grid-cols-4">{previewCameras.map((camera) => <OverviewCamera key={camera.camera_id} camera={camera} attention={attentionIds.has(camera.camera_id)} />)}</div>}</>}</section>;
}

function OverviewCamera({ camera, attention }: { camera: CameraType; attention: boolean }) {
  const condition = cameraCondition(camera);
  const label = attention && condition === "live" ? "Needs attention" : conditionLabel(condition);
  return <Link href={focusHref(camera)} className="group overflow-hidden rounded-lg border border-white/10 bg-black/20 transition hover:border-signal-cyan/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan"><div className="relative aspect-video bg-command-900">{condition === "live" ? <DashboardSnapshot camera={camera} className="h-full w-full object-cover" compact /> : <div className="absolute inset-0 flex items-center justify-center text-xs text-slate-400">{condition === "offline" ? "Camera offline" : condition === "delayed" ? "Live image is delayed" : "Preview unavailable"}</div>}</div><div className="flex items-center justify-between gap-2 p-2.5"><span className="min-w-0 truncate text-sm font-medium text-white">{cameraName(camera)}</span><span className={cn("inline-flex shrink-0 items-center gap-1.5 text-xs", label === "Live" ? "text-emerald-200" : label === "Offline" ? "text-slate-300" : "text-amber-100")}><span className={cn("h-2 w-2 rounded-full", label === "Live" ? "bg-emerald-400" : label === "Offline" ? "bg-slate-400" : "bg-amber-300")} />{label}</span></div></Link>;
}

function RecentActivity({ items, unavailable }: { items: ReviewItem[]; unavailable: boolean }) {
  return <section className="glass-panel rounded-xl p-5 xl:col-start-2 xl:row-start-3" aria-labelledby="recent-activity-title"><div className="flex items-end justify-between gap-3"><div><p className="text-sm font-medium text-slate-400">Latest updates</p><h2 id="recent-activity-title" className="mt-1 text-xl font-semibold text-white">Recent activity</h2></div><Link href="/events" className="inline-flex min-h-9 items-center gap-1 text-sm font-semibold text-signal-cyan hover:text-cyan-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan">View all activity<ChevronRight className="h-4 w-4" aria-hidden /></Link></div>{unavailable ? <p className="mt-5 text-sm text-slate-400">Live data is temporarily unavailable.</p> : items.length === 0 ? <p className="mt-5 text-sm text-slate-400">No operator-relevant activity yet.</p> : <div className="mt-4 space-y-2">{items.slice(0, 5).map((item) => <Link key={`activity-${item.camera.camera_id}`} href={focusHref(item.camera)} className="flex items-center gap-3 rounded-md border border-white/8 bg-black/20 p-3 transition hover:border-signal-cyan/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan"><span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-signal-cyan/10 text-signal-cyan"><Info className="h-4 w-4" aria-hidden /></span><span className="min-w-0 flex-1"><span className="block truncate text-sm font-medium text-white">{item.summary}</span><span className="mt-0.5 block truncate text-xs text-slate-400">{cameraName(item.camera)}</span></span><span className="shrink-0 text-xs text-slate-400">{item.timestamp ? displayTime(item.timestamp) : "Time unavailable"}</span></Link>)}</div>}</section>;
}

function DashboardDiagnostics({ status, cameras, events, unavailable }: { status?: StatusResponse; cameras: CameraType[]; events: RiskEvent[]; unavailable: boolean }) {
  return <details className="glass-panel rounded-xl p-4 xl:col-start-2 xl:row-start-4"><summary className="cursor-pointer list-none text-sm font-semibold text-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan">Diagnostics</summary><dl className="mt-4 grid gap-3 text-sm sm:grid-cols-3"><DiagnosticRow label="Status data" value={unavailable ? "Unavailable" : status ? "Available" : "Not returned"} /><DiagnosticRow label="Camera sources" value={unavailable ? "Unavailable" : `${cameras.length} returned`} /><DiagnosticRow label="Alert records" value={unavailable ? "Unavailable" : `${events.length} returned`} /></dl></details>;
}

function DiagnosticRow({ label, value }: { label: string; value: string }) { return <div className="rounded-md border border-white/8 bg-black/20 p-3"><dt className="text-xs text-slate-500">{label}</dt><dd className="mt-1 font-medium text-slate-200">{value}</dd></div>; }
function CountPill({ label, value, tone = "neutral" }: { label: string; value: number; tone?: "neutral" | "good" | "attention" | "offline" }) { return <div className={cn("rounded-md border p-3", tone === "good" ? "border-emerald-300/20 bg-emerald-400/[0.05]" : tone === "attention" ? "border-amber-300/20 bg-amber-300/[0.05]" : tone === "offline" ? "border-slate-400/20 bg-white/[0.03]" : "border-white/10 bg-black/15")}><p className="text-lg font-semibold text-white">{value}</p><p className="text-xs text-slate-400">{label}</p></div>; }
function CameraStatus({ condition }: { condition: CameraCondition }) { const Icon = condition === "live" ? CheckCircle2 : condition === "offline" ? CircleOff : condition === "delayed" ? Clock3 : WifiOff; return <span className={cn("inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold", condition === "live" ? "border-emerald-300/30 bg-emerald-400/10 text-emerald-100" : condition === "offline" ? "border-slate-300/20 bg-white/[0.05] text-slate-200" : "border-amber-300/30 bg-amber-300/10 text-amber-100")}><Icon className="h-3.5 w-3.5" aria-hidden />{conditionLabel(condition)}</span>; }
function displayTime(value: string | number) { return typeof value === "string" ? formatTime(value) : new Date(value * 1_000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); }

export function DashboardSnapshot({ camera, className, compact = false }: { camera: CameraType; className?: string; compact?: boolean }) {
  const [generation, setGeneration] = useState(0);
  const [failedGeneration, setFailedGeneration] = useState<number | null>(null);
  const active = cameraCondition(camera) === "live";
  useEffect(() => {
    if (!active) return undefined;
    const interval = window.setInterval(() => setGeneration((current) => current + 1), compact ? 7_000 : 4_000);
    return () => window.clearInterval(interval);
  }, [active, compact]);
  const failed = failedGeneration === generation;
  if (!active || failed) return <div className={cn("flex items-center justify-center bg-command-900 text-xs text-slate-400", className)}>Preview unavailable</div>;
  // eslint-disable-next-line @next/next/no-img-element -- authenticated snapshot requests are throttled and flow through the server-side proxy.
  return <img src={`${appConfig.apiUrl}/cameras/${encodeURIComponent(camera.camera_id)}/snapshot?dashboard=${generation}`} alt={`${cameraName(camera)} live view`} className={className} loading={compact ? "lazy" : "eager"} onError={() => setFailedGeneration(generation)} />;
}

function DashboardLoading() { return <div className="grid gap-4 xl:grid-cols-[minmax(0,1.45fr)_minmax(330px,0.7fr)]" aria-busy="true" aria-label="Loading security overview"><div className="h-40 animate-pulse rounded-xl border border-white/10 bg-white/[0.035]" /><div className="h-64 animate-pulse rounded-xl border border-white/10 bg-white/[0.035] xl:row-span-2" /><div className="aspect-video animate-pulse rounded-xl border border-white/10 bg-white/[0.035]" /><div className="h-56 animate-pulse rounded-xl border border-white/10 bg-white/[0.035]" /></div>; }

export const operatorDashboardInternals = { cameraName, cameraCondition, buildReviewItems, cameraCounts, focusCamera, priorityFromEvent };
