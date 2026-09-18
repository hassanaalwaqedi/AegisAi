"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  Car,
  CheckCircle2,
  ChevronDown,
  CircleAlert,
  Clock3,
  Crosshair,
  ExternalLink,
  Eye,
  Loader2,
  MapPin,
  MonitorX,
  Search,
  Users,
  Video,
  WifiOff,
} from "lucide-react";

import { appConfig, createAuthenticatedWebSocket, resolveCameraWebSocketUrl } from "@/lib/config";
import {
  buildLiveTrackingItems,
  cameraPreviewState,
  filterLiveTrackingItems,
  liveTrackingSummary,
  type CameraPreviewState,
  type LiveTrackingItem,
  type TrackingFilter,
} from "@/lib/live-tracking";
import { cameraWebSocketMessageSchema } from "@/lib/schemas";
import { cn } from "@/lib/utils";
import type { Camera, Track } from "@/types";

type LiveTrackingWorkspaceProps = {
  tracks: Track[];
  cameras: Camera[];
  isLoading: boolean;
  isUnavailable: boolean;
  camerasUnavailable: boolean;
  onRetry: () => void;
};

const filters: Array<{ id: TrackingFilter; label: string }> = [
  { id: "all", label: "All" },
  { id: "people", label: "People" },
  { id: "vehicles", label: "Vehicles" },
  { id: "attention", label: "Needs attention" },
];

export function LiveTrackingWorkspace({ tracks, cameras, isLoading, isUnavailable, camerasUnavailable, onRetry }: LiveTrackingWorkspaceProps) {
  const [filter, setFilter] = useState<TrackingFilter>("all");
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const allItems = useMemo(() => buildLiveTrackingItems(tracks, cameras), [tracks, cameras]);
  const items = useMemo(() => filterLiveTrackingItems(allItems, filter, search), [allItems, filter, search]);
  const summary = useMemo(() => liveTrackingSummary(allItems), [allItems]);
  const selected = items.find((item) => item.id === selectedId) ?? items[0] ?? null;

  if (isLoading) return <TrackingLoadingState />;

  return (
    <section className="mx-auto w-full max-w-[1800px] px-4 py-6 sm:px-6 lg:px-8" aria-labelledby="live-tracking-title">
      <TrackingHeader />

      {isUnavailable ? <TrackingUnavailableState onRetry={onRetry} /> : (
        <>
          <TrackingSummary total={summary.total} people={summary.people} vehicles={summary.vehicles} attention={summary.attention} />
          <TrackingToolbar filter={filter} search={search} onFilterChange={setFilter} onSearchChange={setSearch} />
          {camerasUnavailable ? <CameraDataUnavailableNotice /> : null}
          <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(360px,0.94fr)]">
            <TrackingObjectList items={items} selected={selected} onSelect={setSelectedId} />
            <TrackingDetailsPanel item={selected} />
          </div>
        </>
      )}
    </section>
  );
}

export const LiveTrackingPage = LiveTrackingWorkspace;

export function TrackingHeader() {
  return (
    <header>
      <h1 id="live-tracking-title" className="text-3xl font-semibold tracking-tight text-white sm:text-4xl">Live Tracking</h1>
      <p className="mt-2 text-base text-slate-400">See what is moving, where it is, and what needs attention.</p>
    </header>
  );
}

export function TrackingSummary({ total, people, vehicles, attention }: { total: number; people: number; vehicles: number; attention: number }) {
  const cards = [
    { label: "Objects tracked now", value: total, icon: Crosshair, tone: "cyan" as const },
    { label: "People", value: people, icon: Users, tone: "neutral" as const },
    { label: "Vehicles", value: vehicles, icon: Car, tone: "neutral" as const },
    { label: "Needs attention", value: attention, icon: AlertTriangle, tone: "amber" as const },
  ];

  return <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Live tracking summary">{cards.map((card) => <TrackingSummaryCard key={card.label} {...card} />)}</div>;
}

function TrackingSummaryCard({ label, value, icon: Icon, tone }: { label: string; value: number; icon: typeof Crosshair; tone: "cyan" | "neutral" | "amber" }) {
  return <div className={cn("flex min-h-[82px] items-center gap-4 rounded-xl border px-4 py-3", tone === "amber" ? "border-amber-300/35 bg-amber-300/[0.055]" : "border-white/10 bg-white/[0.035]")}><span className={cn("flex h-10 w-10 items-center justify-center rounded-full border", tone === "amber" ? "border-amber-300/70 text-amber-200" : tone === "cyan" ? "border-signal-cyan/60 bg-signal-cyan/[0.07] text-signal-cyan" : "border-slate-400/35 text-slate-300")}><Icon className="h-5 w-5" aria-hidden /></span><span><span className="block text-sm text-slate-400">{label}</span><span className={cn("mt-0.5 block text-2xl font-semibold", tone === "amber" ? "text-amber-200" : "text-white")}>{value}</span></span></div>;
}

export function TrackingToolbar({ filter, search, onFilterChange, onSearchChange }: { filter: TrackingFilter; search: string; onFilterChange: (filter: TrackingFilter) => void; onSearchChange: (value: string) => void }) {
  return <div className="mt-5 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between"><div className="flex max-w-full gap-1 overflow-x-auto rounded-lg border border-white/10 bg-white/[0.035] p-1" role="tablist" aria-label="Tracking filters">{filters.map((item) => <button key={item.id} type="button" role="tab" aria-selected={filter === item.id} onClick={() => onFilterChange(item.id)} className={cn("min-h-9 shrink-0 rounded-md px-4 text-sm font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan", filter === item.id ? "border border-signal-cyan bg-signal-cyan/[0.12] text-signal-cyan" : "text-slate-300 hover:bg-white/[0.06] hover:text-white")}>{item.label}</button>)}</div><label className="relative block w-full lg:max-w-[470px]"><Search className="pointer-events-none absolute start-3 top-1/2 h-4.5 w-4.5 -translate-y-1/2 text-slate-400" aria-hidden /><input value={search} onChange={(event) => onSearchChange(event.target.value)} placeholder="Search camera or activity" aria-label="Search camera or activity" className="h-11 w-full rounded-lg border border-white/10 bg-white/[0.025] ps-10 pe-4 text-sm text-white outline-none placeholder:text-slate-500 focus:border-signal-cyan/70 focus:ring-2 focus:ring-signal-cyan/20" /></label></div>;
}

export function TrackingObjectList({ items, selected, onSelect }: { items: LiveTrackingItem[]; selected: LiveTrackingItem | null; onSelect: (id: string) => void }) {
  if (!items.length) return <TrackingEmptyState />;
  const visibleCameraItems = uniqueCameraItems(items).slice(0, 3);

  return <section className="glass-panel min-w-0 overflow-hidden rounded-xl" aria-label="Live tracking monitor">
    <div className="flex flex-wrap items-start justify-between gap-3 border-b border-white/[0.08] px-5 py-4 sm:px-6"><div><h2 className="text-2xl font-semibold tracking-tight text-white">{selected?.cameraLabel ?? "Tracking activity"}</h2>{selected?.location ? <p className="mt-1 flex items-center gap-1.5 text-sm text-slate-400"><MapPin className="h-3.5 w-3.5" aria-hidden />{selected.location}</p> : <p className="mt-1 text-sm text-slate-400">{selected?.cameraId ? "Camera location unavailable" : "Camera relationship unavailable"}</p>}</div><TrackingStatusBadge state={selected?.cameraPreviewState ?? "unavailable"} /></div>
    <TrackingPreview key={selected?.id ?? "empty"} item={selected} />
    <div className="border-t border-white/[0.08] px-4 py-4 sm:px-5"><p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Tracked activity</p><div className="custom-scrollbar mt-3 flex gap-3 overflow-x-auto pb-1" aria-label="Select tracked activity">{items.map((item) => <TrackingObjectCard key={item.id} item={item} selected={item.id === selected?.id} onSelect={onSelect} />)}</div></div>
    {visibleCameraItems.length ? <div className="border-t border-white/[0.08] px-4 py-4 sm:px-5"><p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Camera views linked to current tracking</p><div className="mt-3 grid gap-3 sm:grid-cols-3">{visibleCameraItems.map((item) => <CameraViewCard key={item.camera?.camera_id ?? item.id} item={item} selected={item.id === selected?.id} onSelect={onSelect} />)}</div></div> : <div className="border-t border-white/[0.08] px-5 py-4 text-sm text-slate-400">No camera-linked tracking data is available.</div>}
  </section>;
}

export function TrackingObjectCard({ item, selected, onSelect }: { item: LiveTrackingItem; selected: boolean; onSelect: (id: string) => void }) {
  return <button type="button" onClick={() => onSelect(item.id)} aria-pressed={selected} className={cn("min-w-[190px] rounded-lg border p-3 text-start transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan", selected ? "border-signal-cyan bg-signal-cyan/[0.09] shadow-[inset_0_0_0_1px_rgba(34,211,238,0.18)]" : "border-white/[0.09] bg-black/15 hover:border-signal-cyan/40")}><span className="flex items-start justify-between gap-3"><span><span className="block text-sm font-semibold text-white">{item.label}</span><span className="mt-1 block text-xs text-slate-400">{item.cameraLabel}</span></span>{item.needsAttention ? <AlertTriangle className="h-4 w-4 shrink-0 text-amber-200" aria-label="Needs attention" /> : null}</span><span className="mt-3 block text-xs text-slate-400">{item.lastSeen ? `Last seen ${relativeTime(item.lastSeen)}` : "Last seen unavailable"}</span></button>;
}

function CameraViewCard({ item, selected, onSelect }: { item: LiveTrackingItem; selected: boolean; onSelect: (id: string) => void }) {
  const camera = item.camera;
  if (!camera) return null;
  const canShowImage = item.cameraPreviewState === "live";
  return <button type="button" onClick={() => onSelect(item.id)} aria-pressed={selected} className={cn("group relative min-h-[136px] overflow-hidden rounded-lg border bg-black/35 text-start transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan", selected ? "border-signal-cyan shadow-[0_0_0_1px_rgba(34,211,238,0.55)]" : "border-white/[0.1] hover:border-signal-cyan/45")}>{canShowImage ? <>
    {/* Snapshot images use the authenticated server-side proxy and cannot use Next's remote image optimiser. */}
    {/* eslint-disable-next-line @next/next/no-img-element */}
    <img src={snapshotUrl(camera.camera_id, `thumb-${item.id}`)} alt={`Latest image from ${item.cameraLabel}`} className="absolute inset-0 h-full w-full object-cover opacity-65 transition group-hover:opacity-80" />
  </> : null}<span className="absolute inset-x-0 top-0 flex items-center justify-between gap-2 bg-gradient-to-b from-command-950/90 to-transparent px-3 py-2"><span className="truncate text-sm font-semibold text-white">{item.cameraLabel}</span><span className={cn("h-2.5 w-2.5 shrink-0 rounded-full", item.cameraPreviewState === "live" ? "bg-emerald-400" : item.cameraPreviewState === "delayed" ? "bg-amber-300" : "bg-slate-400")} aria-hidden /></span>{!canShowImage ? <span className="absolute inset-0 flex items-center justify-center bg-black/45 text-center text-xs font-medium text-slate-300">{previewMessage(item.cameraPreviewState)}</span> : null}</button>;
}

export function TrackingPreview({ item }: { item: LiveTrackingItem | null }) {
  const camera = item?.camera;
  const state = item?.cameraPreviewState ?? "unavailable";
  const [frame, setFrame] = useState("");
  const [snapshotGeneration, setSnapshotGeneration] = useState(0);
  const [snapshotFailed, setSnapshotFailed] = useState(false);

  useEffect(() => {
    const canRefreshSnapshot = camera?.runtime.status === "online" && camera.runtime.running;
    if (!canRefreshSnapshot) return undefined;
    const timer = window.setInterval(() => setSnapshotGeneration((value) => value + 1), 50);
    return () => window.clearInterval(timer);
  }, [camera?.camera_id, camera?.runtime.running, camera?.runtime.status]);

  useEffect(() => {
    if (!camera || state !== "live" || typeof WebSocket === "undefined") return undefined;
    const endpoint = resolveCameraWebSocketUrl(camera.camera_id, "frames");
    if (!endpoint) return undefined;
    let disposed = false;
    let socket: WebSocket | undefined;
    let connectTimer: number | undefined;

    connectTimer = window.setTimeout(() => {
      if (disposed) return;
      void (async () => {
        try {
          socket = await createAuthenticatedWebSocket(endpoint);
          if (disposed) {
            socket.close();
            return;
          }
        socket.onmessage = (event) => {
          try {
            const parsed = cameraWebSocketMessageSchema.safeParse(JSON.parse(event.data));
            if (!disposed && parsed.success && parsed.data.type === "frame" && parsed.data.frame) setFrame(parsed.data.frame);
          } catch {
            // The snapshot proxy remains the truthful fallback when an endpoint
            // sends a malformed frame message.
          }
        };
        } catch {
          // Keep the authenticated snapshot fallback active.
        }
      })();
    }, 0);

    return () => {
      disposed = true;
      if (connectTimer !== undefined) window.clearTimeout(connectTimer);
      if (socket?.readyState === WebSocket.OPEN) socket.close();
    };
  }, [camera, state]);

  if (!item || !camera) return <PreviewUnavailable state="unavailable" />;
  if (state !== "live") return <PreviewUnavailable state={state} />;
  if (snapshotFailed && !frame) return <PreviewUnavailable state="delayed" onRetry={() => { setSnapshotFailed(false); setSnapshotGeneration((value) => value + 1); }} />;

  const source = frame || snapshotUrl(camera.camera_id, snapshotGeneration);
  return <div className="relative aspect-[16/9] min-h-[260px] bg-black sm:min-h-[380px]">
    {/* The source is either a WebSocket frame or the authenticated snapshot proxy. */}
    {/* eslint-disable-next-line @next/next/no-img-element */}
    <img src={source} alt={`Latest image from ${item.cameraLabel}`} className="h-full w-full object-contain" onError={() => { if (!frame) setSnapshotFailed(true); }} />
    {frame ? <span className="absolute start-4 top-4 rounded-md border border-emerald-300/40 bg-command-950/85 px-2.5 py-1 text-xs font-semibold text-emerald-200">Live image</span> : <span className="absolute start-4 top-4 rounded-md border border-signal-cyan/35 bg-command-950/85 px-2.5 py-1 text-xs font-semibold text-signal-cyan">Latest camera image</span>}
    <span className="absolute bottom-4 start-4 rounded-md border border-white/15 bg-command-950/85 px-2.5 py-1 text-xs font-semibold text-white">{item.label}</span>
    {item.needsAttention && item.riskLabel ? <span className="absolute bottom-4 end-4 rounded-md border border-amber-300/40 bg-amber-300/[0.16] px-2.5 py-1 text-xs font-semibold text-amber-100">{item.riskLabel}</span> : null}
  </div>;
}

function PreviewUnavailable({ state, onRetry }: { state: CameraPreviewState; onRetry?: () => void }) {
  return <div className="flex aspect-[16/9] min-h-[260px] flex-col items-center justify-center bg-black px-6 text-center sm:min-h-[380px]">{state === "offline" ? <WifiOff className="h-8 w-8 text-slate-500" aria-hidden /> : state === "delayed" ? <Clock3 className="h-8 w-8 text-amber-200" aria-hidden /> : <MonitorX className="h-8 w-8 text-slate-500" aria-hidden />}<p className="mt-4 text-base font-semibold text-slate-200">{previewMessage(state)}</p><p className="mt-1 text-sm text-slate-500">{state === "unavailable" ? "No camera view is available for this tracked activity." : state === "offline" ? "Check the camera connection before reviewing new activity." : "The latest camera image has not arrived yet."}</p>{onRetry ? <button type="button" onClick={onRetry} className="mt-4 min-h-9 rounded-md border border-signal-cyan/40 px-3 text-sm font-semibold text-signal-cyan transition hover:bg-signal-cyan/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan">Retry preview</button> : null}</div>;
}

export function TrackingDetailsPanel({ item }: { item: LiveTrackingItem | null }) {
  if (!item) return <section className="glass-panel flex min-h-[500px] flex-col items-center justify-center rounded-xl p-8 text-center"><Crosshair className="h-8 w-8 text-slate-600" aria-hidden /><h2 className="mt-4 text-xl font-semibold text-white">Select tracked activity</h2><p className="mt-2 max-w-sm text-sm leading-6 text-slate-400">Choose a person, vehicle, or other activity to review available information.</p></section>;
  const historyId = `tracking-history-${item.id.replace(/[^a-zA-Z0-9_-]/g, "-")}`;
  const cameraHref = item.camera ? `/cameras?camera=${encodeURIComponent(item.camera.camera_id)}&view=focus` : null;

  return <aside className="glass-panel min-w-0 overflow-hidden rounded-xl" aria-labelledby="selected-activity-title"><div className="border-b border-white/[0.08] px-5 py-4 sm:px-6"><p className="text-xs font-semibold uppercase tracking-[0.16em] text-signal-cyan">Selected activity</p><h2 id="selected-activity-title" className="mt-2 text-2xl font-semibold tracking-tight text-white">{item.label}</h2><p className="mt-1 text-sm text-slate-400">{item.cameraLabel}</p></div><div className="space-y-5 p-5 sm:p-6"><div className="flex items-start gap-4"><span className={cn("flex h-12 w-12 shrink-0 items-center justify-center rounded-full border", item.category === "vehicle" ? "border-signal-cyan/50 bg-signal-cyan/[0.1] text-signal-cyan" : item.category === "person" ? "border-blue-300/45 bg-blue-400/[0.1] text-blue-200" : "border-slate-400/40 bg-white/[0.04] text-slate-200")}>{item.category === "vehicle" ? <Car className="h-6 w-6" aria-hidden /> : item.category === "person" ? <Users className="h-6 w-6" aria-hidden /> : <Crosshair className="h-6 w-6" aria-hidden />}</span><div className="min-w-0"><span className={cn("inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-sm font-medium", item.movement === "moving" ? "border-signal-cyan/40 bg-signal-cyan/[0.1] text-signal-cyan" : "border-white/10 bg-white/[0.035] text-slate-300")}>{item.movement === "moving" ? <Eye className="h-3.5 w-3.5" aria-hidden /> : null}{item.movementLabel}</span><p className="mt-3 flex items-center gap-2 text-sm text-slate-400"><Clock3 className="h-4 w-4" aria-hidden />{item.lastSeen ? `Last seen ${relativeTime(item.lastSeen)}` : "Last seen unavailable"}</p>{item.riskLabel ? <p className="mt-3 inline-flex items-center gap-2 rounded-md border border-amber-300/40 bg-amber-300/[0.08] px-2.5 py-1.5 text-sm font-semibold text-amber-100"><AlertTriangle className="h-4 w-4" aria-hidden />{item.riskLabel}</p> : null}</div></div><TrackingTimeline item={item} id={historyId} /><TrackingActionBar cameraHref={cameraHref} hasHistory={item.timeline.length > 0} historyId={historyId} /><TrackingTechnicalDetails item={item} /></div></aside>;
}

export function TrackingTimeline({ item, id }: { item: LiveTrackingItem; id: string }) {
  return <section id={id} tabIndex={-1} className="rounded-xl border border-white/[0.09] bg-black/15 p-4 focus:outline-none focus:ring-2 focus:ring-signal-cyan"><h3 className="text-base font-semibold text-white">Activity timeline</h3>{item.timeline.length ? <ol className="mt-5 grid gap-4 sm:grid-cols-2">{item.timeline.map((entry, index) => <li key={`${entry.label}-${entry.timestamp}`} className="relative flex items-start gap-3"><span className={cn("mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border", index === item.timeline.length - 1 ? "border-signal-cyan bg-signal-cyan/[0.1] text-signal-cyan" : "border-slate-400/35 text-slate-300")}><Clock3 className="h-4 w-4" aria-hidden /></span><span><span className="block text-sm font-medium text-slate-200">{entry.label}</span><span className="mt-1 block text-xs text-slate-500">{formatTimestamp(entry.timestamp)}</span></span></li>)}</ol> : <p className="mt-3 text-sm text-slate-400">No tracking history available.</p>}</section>;
}

export function TrackingStatusBadge({ state }: { state: CameraPreviewState }) {
  const copy = state === "live" ? "Monitoring" : state === "delayed" ? "Live image delayed" : state === "offline" ? "Camera offline" : "Information unavailable";
  return <span className={cn("inline-flex items-center gap-2 rounded-full px-2.5 py-1 text-sm font-medium", state === "live" ? "text-emerald-200" : state === "delayed" ? "text-amber-100" : "text-slate-300")}><span className={cn("h-2.5 w-2.5 rounded-full", state === "live" ? "bg-emerald-400" : state === "delayed" ? "bg-amber-300" : "bg-slate-400")} aria-hidden />{copy}</span>;
}

function TrackingActionBar({ cameraHref, hasHistory, historyId }: { cameraHref: string | null; hasHistory: boolean; historyId: string }) {
  return <div className="flex flex-wrap gap-3">{cameraHref ? <Link href={cameraHref} className="inline-flex min-h-11 items-center gap-2 rounded-md bg-signal-cyan px-4 text-sm font-semibold text-command-950 transition hover:bg-cyan-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan"><Video className="h-4 w-4" aria-hidden />Open camera<ExternalLink className="h-3.5 w-3.5" aria-hidden /></Link> : null}{hasHistory ? <button type="button" onClick={() => document.getElementById(historyId)?.focus()} className="inline-flex min-h-11 items-center gap-2 rounded-md border border-white/15 px-4 text-sm font-semibold text-slate-100 transition hover:border-signal-cyan/50 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan"><Eye className="h-4 w-4" aria-hidden />View activity</button> : null}</div>;
}

function TrackingTechnicalDetails({ item }: { item: LiveTrackingItem }) {
  const [open, setOpen] = useState(false);
  const details = diagnosticRows(item);
  if (!details.length) return null;
  return <details open={open} onToggle={(event) => setOpen((event.currentTarget as HTMLDetailsElement).open)} className="rounded-xl border border-white/[0.09] bg-black/15 p-4"><summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-sm font-semibold text-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan">Details<ChevronDown className={cn("h-4 w-4 transition", open && "rotate-180")} aria-hidden /></summary>{open ? <dl className="mt-4 grid gap-3 sm:grid-cols-2">{details.map((detail) => <div key={detail.label} className="rounded-lg border border-white/[0.07] bg-white/[0.025] p-3"><dt className="text-xs text-slate-500">{detail.label}</dt><dd className="mt-1 break-words text-sm font-medium text-slate-200">{detail.value}</dd></div>)}</dl> : null}</details>;
}

function TrackingEmptyState() {
  return <section className="glass-panel flex min-h-[500px] flex-col items-center justify-center rounded-xl p-8 text-center"><CheckCircle2 className="h-8 w-8 text-slate-600" aria-hidden /><h2 className="mt-4 text-xl font-semibold text-white">No tracked activity matches this view.</h2><p className="mt-2 max-w-sm text-sm leading-6 text-slate-400">New tracked activity will appear when movement is detected.</p></section>;
}

function TrackingUnavailableState({ onRetry }: { onRetry: () => void }) {
  return <div className="mt-6 rounded-xl border border-eose-400/25 bg-rose-500/[0.06] p-6"><div className="flex items-start gap-3"><WifiOff className="mt-0.5 h-5 w-5 text-rose-300" aria-hidden /><div><h2 className="text-lg font-semibold text-rose-100">Live tracking is temporarily unavailable.</h2><p className="mt-1 text-sm text-rose-100/75">Current tracking activity could not be loaded. Try again.</p><button type="button" onClick={onRetry} className="mt-4 inline-flex min-h-9 items-center rounded-md border border-eose-300/35 px-3 text-sm font-semibold text-rose-100 transition hover:bg-rose-400/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-200">Retry</button></div></div></div>;
}

function CameraDataUnavailableNotice() {
  return <div className="mt-4 flex items-start gap-3 rounded-xl border border-amber-300/25 bg-amber-300/[0.05] px-4 py-3 text-sm text-amber-100"><CircleAlert className="mt-0.5 h-4.5 w-4.5 shrink-0" aria-hidden /><p>Camera details are temporarily unavailable. Tracked activity is shown without camera previews where a camera cannot be verified.</p></div>;
}

function TrackingLoadingState() {
  return <section className="mx-auto w-full max-w-[1800px] px-4 py-6 sm:px-6 lg:px-8" aria-busy="true" aria-label="Loading live tracking"><div className="h-10 w-64 animate-pulse rounded bg-white/[0.07]" /><div className="mt-3 h-5 w-96 max-w-full animate-pulse rounded bg-white/[0.04]" /><div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{Array.from({ length: 4 }).map((_, index) => <div key={index} className="h-[82px] animate-pulse rounded-xl border border-white/10 bg-white/[0.035]" />)}</div><div className="mt-5 grid gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(360px,0.94fr)]"><div className="h-[620px] animate-pulse rounded-xl border border-white/10 bg-white/[0.035]" /><div className="h-[620px] animate-pulse rounded-xl border border-white/10 bg-white/[0.035]" /></div></section>;
}

function uniqueCameraItems(items: LiveTrackingItem[]) {
  const seen = new Set<string>();
  return items.filter((item) => {
    const cameraId = item.camera?.camera_id;
    if (!cameraId || seen.has(cameraId)) return false;
    seen.add(cameraId);
    return true;
  });
}

function previewMessage(state: CameraPreviewState) {
  if (state === "offline") return "Camera offline";
  if (state === "delayed") return "Live image delayed";
  return "No preview available";
}

function snapshotUrl(cameraId: string, generation: string | number) {
  return `${appConfig.apiUrl}/cameras/${encodeURIComponent(cameraId)}/snapshot?tracking=${encodeURIComponent(String(generation))}`;
}

function relativeTime(value: string) {
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) return "time unavailable";
  const delta = Math.max(0, Date.now() - timestamp);
  if (delta < 60_000) return "just now";
  if (delta < 3_600_000) return `${Math.floor(delta / 60_000)} min ago`;
  if (delta < 86_400_000) return `${Math.floor(delta / 3_600_000)} hr ago`;
  return new Date(timestamp).toLocaleString();
}

function formatTimestamp(value: string) {
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) ? new Date(timestamp).toLocaleString() : "Time unavailable";
}

function diagnosticRows(item: LiveTrackingItem) {
  const rows: Array<{ label: string; value: string }> = [];
  const add = (label: string, value: unknown) => {
    if (typeof value === "string" && value.trim()) rows.push({ label, value });
    if (typeof value === "number" && Number.isFinite(value)) rows.push({ label, value: String(value) });
  };
  add("Track reference", item.track.track_id);
  add("Camera reference", item.cameraId);
  add("Activity type", item.track.class_name);
  add("Risk level", item.track.risk_level);
  add("Risk score", item.track.risk_score);
  add("First seen", item.firstSeen);
  add("Last seen", item.lastSeen);
  add("Camera runtime", item.camera?.runtime.status);
  if (item.camera?.runtime.error_message) add("Camera status", "Needs attention");
  return rows;
}

export const liveTrackingWorkspaceInternals = { previewMessage, relativeTime, diagnosticRows };
