"use client";

import type { ReactNode } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import {
  ChevronLeft,
  ChevronRight,
  Grid2X2,
  MapPin,
  Maximize2,
  Search,
  ScanLine,
  ArrowUpRight,
  Activity,
  WifiOff,
  Video,
} from "lucide-react";

import { CameraCommandCenter } from "@/components/cameras/camera-command-center";
import { appConfig } from "@/lib/config";
import { cn, formatTime } from "@/lib/utils";
import type { Camera, RiskEvent } from "@/types";

export type CameraWallView = "grid" | "focus" | "map";
export type CameraWallFilter = "all" | "live" | "attention" | "offline";

type CameraWallStatus = "live" | "attention" | "offline" | "unavailable";

type ReviewItem = {
  camera: Camera;
  summary: string;
  timestamp?: string | number;
  status: "attention" | "offline";
};

const CAMERAS_PER_PAGE = 9;

function cameraDisplayName(camera: Camera) {
  const configuredName = camera.name?.trim();
  const sourceNames = new Set(["http stream", "rtsp stream", "local device", "browser webcam", "uploaded video"]);
  if (configuredName && !sourceNames.has(configuredName.toLowerCase())) return configuredName;
  const cleanReference = camera.camera_id
    .replace(/^(?:http|rtsp)[-_]?stream[-_]?/i, "")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/[-_]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .split(" ")
    .map((part) => part ? `${part[0]?.toUpperCase()}${part.slice(1)}` : part)
    .join(" ");
  return cleanReference ? `Camera ${cleanReference}` : "Camera unavailable";
}

function isAttentionEvent(event: RiskEvent) {
  const level = String(event.risk_level ?? event.severity ?? event.level ?? "").toUpperCase();
  return ["CANDIDATE_MEDIUM", "MEDIUM", "HIGH", "CRITICAL", "WARNING"].includes(level);
}

function cameraStatus(camera: Camera, attentionCameraIds: Set<string>): CameraWallStatus {
  const runtime = camera.runtime;
  if (["offline", "error", "stopped"].includes(runtime.status)) return "offline";
  if (attentionCameraIds.has(camera.camera_id) || ["connecting", "reconnecting"].includes(runtime.status)) return "attention";
  if (runtime.status === "online" && runtime.running) return "live";
  return "unavailable";
}

function hasDelayedLiveImage(camera: Camera) {
  return ["connecting", "reconnecting"].includes(camera.runtime.status);
}

function statusCopy(status: CameraWallStatus, t: ReturnType<typeof useTranslations>) {
  if (status === "live") return t("live");
  if (status === "attention") return t("needsAttention");
  if (status === "offline") return t("offline");
  return t("unavailable");
}

function eventSummary(event: RiskEvent) {
  const level = String(event.risk_level ?? event.severity ?? event.level ?? "").toUpperCase();
  if (["HIGH", "CRITICAL"].includes(level)) return "High-priority activity needs review";
  return "Movement noticed";
}

function buildReviewItems(cameras: Camera[], events: RiskEvent[]) {
  const byId = new Map(cameras.map((camera) => [camera.camera_id, camera]));
  const items: ReviewItem[] = cameras
    .filter((camera) => ["offline", "error", "stopped"].includes(camera.runtime.status))
    .map((camera) => ({ camera, summary: "Camera offline", timestamp: camera.runtime.last_frame_time ?? undefined, status: "offline" }));

  for (const event of events) {
    if (!isAttentionEvent(event) || !event.camera_id) continue;
    const camera = byId.get(event.camera_id);
    if (!camera || items.some((item) => item.camera.camera_id === camera.camera_id && item.status === "attention")) continue;
    items.push({ camera, summary: eventSummary(event), timestamp: event.timestamp, status: "attention" });
  }
  return items;
}

function cameraCoordinates(camera: Camera) {
  const metadata = camera.metadata ?? {};
  const latitude = metadata.latitude ?? metadata.lat;
  const longitude = metadata.longitude ?? metadata.lng ?? metadata.lon;
  return typeof latitude === "number" && typeof longitude === "number" ? { latitude, longitude } : null;
}

function snapshotUrl(camera: Camera, generation: number) {
  return `${appConfig.apiUrl}/cameras/${encodeURIComponent(camera.camera_id)}/snapshot?preview=${generation}`;
}

export function CameraWall({
  cameras,
  events,
  initialView,
  initialCameraId,
  onViewChange,
  onCameraChange,
  eventsUnavailable = false,
}: {
  cameras: Camera[];
  events: RiskEvent[];
  initialView: CameraWallView;
  initialCameraId?: string;
  onViewChange: (view: CameraWallView) => void;
  onCameraChange: (cameraId: string) => void;
  systemStatus?: "connected" | "degraded" | "unavailable" | "loading";
  eventsUnavailable?: boolean;
}) {
  const t = useTranslations("cameras");
  const [view, setView] = useState<CameraWallView>(initialView);
  const [filter, setFilter] = useState<CameraWallFilter>("all");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const [selectedCameraId, setSelectedCameraId] = useState(initialCameraId);

  const reviewItems = useMemo(() => buildReviewItems(cameras, events), [cameras, events]);
  const attentionCameraIds = useMemo(() => new Set(reviewItems.filter((item) => item.status === "attention").map((item) => item.camera.camera_id)), [reviewItems]);
  const selectedCamera = cameras.find((camera) => camera.camera_id === selectedCameraId) ?? cameras[0];
  const counts = useMemo(() => {
    const statuses = cameras.map((camera) => cameraStatus(camera, attentionCameraIds));
    return {
      total: cameras.length,
      live: statuses.filter((status) => status === "live").length,
      attention: statuses.filter((status) => status === "attention").length,
      offline: statuses.filter((status) => status === "offline").length,
    };
  }, [attentionCameraIds, cameras]);
  const filteredCameras = useMemo(() => cameras.filter((camera) => {
    const status = cameraStatus(camera, attentionCameraIds);
    const matchesFilter = filter === "all" || (filter === "live" && status === "live") || (filter === "attention" && status === "attention") || (filter === "offline" && status === "offline");
    return matchesFilter && cameraDisplayName(camera).toLowerCase().includes(query.trim().toLowerCase());
  }), [attentionCameraIds, cameras, filter, query]);
  const pageCount = Math.max(1, Math.ceil(filteredCameras.length / CAMERAS_PER_PAGE));
  const safePage = Math.min(page, pageCount - 1);
  const visibleCameras = filteredCameras.slice(safePage * CAMERAS_PER_PAGE, safePage * CAMERAS_PER_PAGE + CAMERAS_PER_PAGE);
  const focusCameras = selectedCamera && !visibleCameras.some((camera) => camera.camera_id === selectedCamera.camera_id)
    ? [selectedCamera, ...visibleCameras].slice(0, CAMERAS_PER_PAGE)
    : visibleCameras;
  const mappedCameras = useMemo(() => cameras.flatMap((camera) => {
    const coordinates = cameraCoordinates(camera);
    return coordinates ? [{ camera, coordinates }] : [];
  }), [cameras]);

  const changeView = (nextView: CameraWallView) => {
    setView(nextView);
    onViewChange(nextView);
  };
  const focusCamera = (camera: Camera) => {
    setSelectedCameraId(camera.camera_id);
    onCameraChange(camera.camera_id);
    changeView("focus");
  };

  return (
    <div className="space-y-4">
      {view !== "focus" ? (
        <CameraWallToolbar
          counts={counts}
          filter={filter}
          view={view}
          query={query}
          mapAvailable={mappedCameras.length > 0}
          onFilterChange={(nextFilter) => {
            setFilter(nextFilter);
            setPage(0);
          }}
          onViewChange={changeView}
          onQueryChange={(nextQuery) => {
            setQuery(nextQuery);
            setPage(0);
          }}
          t={t}
        />
      ) : null}

      {view === "grid" ? (
        <div className="camera-monitor-layout"><div className="min-w-0">
          {filteredCameras.length ? <CameraGrid cameras={visibleCameras} selectedCameraId={selectedCamera?.camera_id} attentionCameraIds={attentionCameraIds} onFocus={focusCamera} t={t} /> : <NoCameraResults t={t} />}
          {filteredCameras.length > CAMERAS_PER_PAGE ? <CameraWallPagination page={safePage} pageCount={pageCount} total={filteredCameras.length} onChange={setPage} /> : null}
        </div>
        <aside className="camera-review-panel">
          <div className="camera-review-heading"><span className="camera-review-icon"><Activity aria-hidden /></span><div><p className="camera-eyebrow">{t("workspace.operations")}</p><h2>{t("workspace.review")}</h2></div><span className="camera-review-count">{reviewItems.length}</span></div>
          <p className="camera-review-description">{t("workspace.reviewDescription")}</p>
          {eventsUnavailable ? <p className="camera-review-notice">{t("workspace.eventsUnavailable")}</p> : null}
          <div className="camera-review-list">{reviewItems.length ? reviewItems.map((item) => <button key={`${item.camera.camera_id}-${item.status}`} type="button" onClick={() => focusCamera(item.camera)} className="camera-review-item">
            <span className={cn("camera-review-marker", item.status === "attention" && "is-attention")}>{item.status === "offline" ? <WifiOff aria-hidden /> : <ScanLine aria-hidden />}</span>
            <span className="min-w-0 flex-1"><strong>{cameraDisplayName(item.camera)}</strong><span>{item.status === "offline" ? t("workspace.connectionOffline") : t("workspace.activityReview")}</span></span><ArrowUpRight className="h-4 w-4 shrink-0 text-slate-500" aria-hidden />
          </button>) : <p className="camera-review-empty">{t("workspace.noReview")}</p>}</div>
          <div className="camera-review-note"><ScanLine aria-hidden /><span>{t("workspace.focusHint")}</span></div>
        </aside></div>
      ) : null}

      {view === "focus" && selectedCamera ? <CameraFocusWorkspace camera={selectedCamera} cameras={focusCameras.length ? focusCameras : cameras.slice(0, CAMERAS_PER_PAGE)} attentionCameraIds={attentionCameraIds} onSelect={focusCamera} onBack={() => changeView("grid")} /> : null}

      {view === "map" ? <CameraMapView cameras={mappedCameras} attentionCameraIds={attentionCameraIds} onFocus={focusCamera} /> : null}
    </div>
  );
}

export function CameraWallToolbar({
  counts,
  filter,
  view,
  query,
  mapAvailable,
  onFilterChange,
  onViewChange,
  onQueryChange,
  t,
}: {
  counts: { total: number; live: number; attention: number; offline: number };
  filter: CameraWallFilter;
  view: CameraWallView;
  query: string;
  mapAvailable: boolean;
  onFilterChange: (filter: CameraWallFilter) => void;
  onViewChange: (view: CameraWallView) => void;
  onQueryChange: (query: string) => void;
  t: ReturnType<typeof useTranslations>;
}) {
  const filters: Array<{ id: CameraWallFilter; label: string; count?: number }> = [
    { id: "all", label: t("allCameras"), count: counts.total },
    { id: "live", label: t("live"), count: counts.live },
    { id: "attention", label: t("needsAttention"), count: counts.attention },
    { id: "offline", label: t("offline"), count: counts.offline },
  ];
  return (
    <div className="camera-wall-toolbar">
      <div className="camera-filter-tabs" role="group" aria-label="Camera filters">
        {filters.map((item) => <button key={item.id} type="button" onClick={() => onFilterChange(item.id)} aria-pressed={filter === item.id} className={cn("camera-filter-tab", filter === item.id && "is-active")}>
          {item.id !== "all" ? <span aria-hidden className={cn("h-1.5 w-1.5 shrink-0 rounded-full", item.id === "live" ? "bg-emerald-400" : item.id === "attention" ? "bg-amber-300" : "bg-slate-500")} /> : null}
          {item.label}{" "}<span className="camera-filter-count">{item.count}</span>
        </button>)}
      </div>
      <label className="camera-toolbar-search relative block min-w-0">
        <Search className="pointer-events-none absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" aria-hidden />
        <input value={query} onChange={(event) => onQueryChange(event.target.value)} placeholder={t("searchPlaceholder")} className="h-9 w-full rounded-lg border border-white/10 bg-black/20 ps-9 pe-3 text-sm text-white outline-none placeholder:text-slate-500 focus:border-signal-cyan/55" aria-label="Search cameras" />
      </label>
      <div className="camera-view-switch flex rounded-lg border border-white/10 bg-black/15 p-0.5" role="group" aria-label="Camera wall view">
        <ViewButton active={view === "grid"} onClick={() => onViewChange("grid")} icon={Grid2X2} label={t("grid")} />
        <ViewButton active={view === "focus"} onClick={() => onViewChange("focus")} icon={Maximize2} label={t("focus")} />
        <ViewButton active={view === "map"} onClick={() => onViewChange("map")} icon={MapPin} label={t("map")} disabled={!mapAvailable} title={mapAvailable ? "Show configured camera locations" : "Camera locations are not configured yet."} />
      </div>
    </div>
  );
}

function ViewButton({ active, onClick, icon: Icon, label, disabled, title }: { active: boolean; onClick: () => void; icon: typeof Grid2X2; label: string; disabled?: boolean; title?: string }) {
  return <button type="button" onClick={onClick} aria-pressed={active} disabled={disabled} title={title} className={cn("inline-flex min-h-9 items-center gap-2 rounded-md px-3 text-sm font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan disabled:cursor-not-allowed disabled:opacity-40", active ? "bg-signal-cyan/15 text-signal-cyan" : "text-slate-300 hover:bg-white/[0.06]")}><Icon className="h-4 w-4" aria-hidden />{label}</button>;
}

export function CameraGrid({ cameras, selectedCameraId, attentionCameraIds, onFocus, t }: { cameras: Camera[]; selectedCameraId?: string; attentionCameraIds: Set<string>; onFocus: (camera: Camera) => void, t: ReturnType<typeof useTranslations> }) {
  const gridRef = useRef<HTMLDivElement>(null);
  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (!["ArrowRight", "ArrowLeft", "ArrowDown", "ArrowUp"].includes(event.key)) return;
    const tiles = Array.from(gridRef.current?.querySelectorAll<HTMLButtonElement>("[data-camera-tile]") ?? []);
    const current = tiles.indexOf(document.activeElement as HTMLButtonElement);
    if (current < 0) return;
    const columns = gridRef.current ? getComputedStyle(gridRef.current).gridTemplateColumns.split(" ").length : 1;
    const delta = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : event.key === "ArrowDown" ? columns : -columns;
    const next = Math.min(tiles.length - 1, Math.max(0, current + delta));
    if (next !== current) {
      event.preventDefault();
      tiles[next]?.focus();
    }
  };
  return <div ref={gridRef} onKeyDown={onKeyDown} className="camera-feed-grid" aria-label="Camera grid">{cameras.map((camera) => <CameraTile key={camera.camera_id} camera={camera} selected={selectedCameraId === camera.camera_id} status={cameraStatus(camera, attentionCameraIds)} onFocus={onFocus} t={t} />)}</div>;
}

export function CameraTile({ camera, status, selected, onFocus, t }: { camera: Camera; status: CameraWallStatus; selected: boolean; onFocus: (camera: Camera) => void, t: ReturnType<typeof useTranslations> }) {
  return (
    <button data-camera-tile type="button" onClick={() => onFocus(camera)} className={cn("camera-feed-card group", selected && "is-selected border-signal-cyan")} aria-label={`Open ${cameraDisplayName(camera)} in Focus mode`}>
      <div className="camera-feed-image">
        <CameraPreview camera={camera} status={status} />
        <span className={cn("camera-feed-status", statusPillClass(status))}><StatusDot status={status} t={t} />{statusCopy(status, t)}</span>
        <span className="camera-feed-expand"><Maximize2 className="h-4 w-4" aria-hidden /></span>
        <div className="camera-feed-time"><span>{camera.runtime.last_frame_time ? formatTime(camera.runtime.last_frame_time) : t("noLiveFrame")}</span>{selected ? <span>{t("selected")}</span> : null}</div>
      </div>
      <div className="camera-feed-caption"><span className="camera-feed-symbol"><Video aria-hidden /></span><span className="min-w-0 flex-1"><strong>{cameraDisplayName(camera)}</strong><span>{t("workspace.openFeed")}</span></span><ArrowUpRight className="h-4 w-4 text-slate-500 transition group-hover:text-cyan-300" aria-hidden /></div>
    </button>
  );
}

export function CameraPreview({ camera, status }: { camera: Camera; status: CameraWallStatus }) {
  const t = useTranslations("cameras");
  const elementRef = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [generation, setGeneration] = useState(0);
  const [failedGeneration, setFailedGeneration] = useState<number | null>(null);
  const delayed = hasDelayedLiveImage(camera);
  const canPreview = camera.runtime.status === "online" && camera.runtime.running && !delayed;

  useEffect(() => {
    const element = elementRef.current;
    if (!element || !canPreview) return undefined;
    const observer = new IntersectionObserver(([entry]) => setVisible(Boolean(entry?.isIntersecting)), { rootMargin: "160px" });
    observer.observe(element);
    return () => observer.disconnect();
  }, [canPreview]);

  useEffect(() => {
    if (!visible || !canPreview) return undefined;
    const timer = window.setInterval(() => setGeneration((value) => value + 1), 250);
    return () => window.clearInterval(timer);
  }, [canPreview, visible]);

  const previewFailed = failedGeneration === generation;
  const message = status === "offline" ? t("workspace.cameraOffline") : status === "unavailable" || previewFailed ? t("workspace.previewUnavailable") : delayed ? t("workspace.delayed") : t("workspace.waitingFrame");
  return (
    <div ref={elementRef} className="absolute inset-0 bg-black">
      {visible && canPreview && !previewFailed ? <>
        {/* eslint-disable-next-line @next/next/no-img-element -- authenticated Aegis snapshot endpoint refreshes at a controlled cadence. */}
        <img src={snapshotUrl(camera, generation)} alt="" className="h-full w-full object-cover" loading="lazy" onError={() => setFailedGeneration(generation)} />
      </> : null}
      {(!visible || !canPreview || previewFailed) ? <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 camera-preview-empty text-center text-xs text-slate-400"><Video className="h-6 w-6 text-slate-600" aria-hidden />{message}</div> : null}
    </div>
  );
}

export function CameraFocusWorkspace({ camera, cameras, attentionCameraIds, onSelect, onBack }: { camera: Camera; cameras: Camera[]; attentionCameraIds: Set<string>; onSelect: (camera: Camera) => void; onBack: () => void }) {
  return <div className="space-y-3"><button type="button" onClick={onBack} className="inline-flex min-h-9 items-center gap-2 rounded-md border border-white/10 px-3 text-sm font-medium text-slate-200 hover:bg-white/[0.06] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan"><ChevronLeft className="h-4 w-4" aria-hidden />Back to grid</button><div className="min-w-0"><CameraCommandCenter key={camera.camera_id} camera={camera} cameraSwitcher={<CameraThumbnailRail cameras={cameras} selectedCameraId={camera.camera_id} attentionCameraIds={attentionCameraIds} onSelect={onSelect} />} /></div></div>;
}

export function CameraThumbnailRail({ cameras, selectedCameraId, attentionCameraIds, onSelect }: { cameras: Camera[]; selectedCameraId: string; attentionCameraIds: Set<string>; onSelect: (camera: Camera) => void }) {
  return <div className="flex gap-3 overflow-x-auto pb-1" aria-label="Focus camera thumbnails">{cameras.map((camera) => <button key={camera.camera_id} type="button" onClick={() => onSelect(camera)} className={cn("w-44 shrink-0 overflow-hidden rounded-lg border bg-command-900 text-start transition hover:border-signal-cyan/55 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan sm:w-52 lg:w-56", camera.camera_id === selectedCameraId ? "border-signal-cyan ring-1 ring-signal-cyan/55" : "border-white/10")}><div className="relative aspect-video"><CameraPreview camera={camera} status={cameraStatus(camera, attentionCameraIds)} /></div><p className="truncate px-2.5 py-2 text-xs font-medium text-white">{cameraDisplayName(camera)}</p></button>)}</div>;
}

export function CameraMapView({ cameras, attentionCameraIds, onFocus }: { cameras: Array<{ camera: Camera; coordinates: { latitude: number; longitude: number } }>; attentionCameraIds: Set<string>; onFocus: (camera: Camera) => void }) {
  if (!cameras.length) return <div className="glass-panel rounded-xl p-10 text-center"><MapPin className="mx-auto h-8 w-8 text-slate-500" aria-hidden /><h2 className="mt-3 text-lg font-semibold text-white">Camera locations are not configured yet.</h2><p className="mt-2 text-sm text-slate-400">Add a camera location to use Map view.</p></div>;
  const latitudes = cameras.map(({ coordinates }) => coordinates.latitude);
  const longitudes = cameras.map(({ coordinates }) => coordinates.longitude);
  const minLat = Math.min(...latitudes); const maxLat = Math.max(...latitudes); const minLng = Math.min(...longitudes); const maxLng = Math.max(...longitudes);
  return <div className="glass-panel relative min-h-[520px] overflow-hidden rounded-xl bg-[radial-gradient(circle_at_center,rgba(34,211,238,0.1),transparent_54%),linear-gradient(135deg,#0d1728,#050b15)] p-5"><p className="text-sm text-slate-300">Configured camera locations</p>{cameras.map(({ camera, coordinates }) => { const x = maxLng === minLng ? 50 : 10 + ((coordinates.longitude - minLng) / (maxLng - minLng)) * 80; const y = maxLat === minLat ? 50 : 10 + ((maxLat - coordinates.latitude) / (maxLat - minLat)) * 80; const status = cameraStatus(camera, attentionCameraIds); return <button key={camera.camera_id} type="button" style={{ left: `${x}%`, top: `${y}%` }} onClick={() => onFocus(camera)} className="absolute -translate-x-1/2 -translate-y-1/2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan"><span className={cn("flex h-9 w-9 items-center justify-center rounded-full border-2 bg-command-950 shadow-xl", status === "live" ? "border-emerald-300 text-emerald-200" : status === "attention" ? "border-amber-300 text-amber-200" : "border-slate-300 text-slate-200")}><Video className="h-4 w-4" aria-hidden /></span><span className="mt-1 block max-w-28 truncate rounded bg-command-950/90 px-1.5 py-0.5 text-[11px] text-white">{cameraDisplayName(camera)}</span></button>; })}</div>;
}

export function CameraWallPagination({ page, pageCount, total, onChange }: { page: number; pageCount: number; total: number; onChange: (page: number) => void }) {
  const start = page * CAMERAS_PER_PAGE + 1; const end = Math.min(total, (page + 1) * CAMERAS_PER_PAGE);
  return <div className="mt-4 flex items-center justify-center gap-3"><button type="button" aria-label="Previous" disabled={page === 0} onClick={() => onChange(page - 1)} className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-white/10 text-slate-200 disabled:opacity-35"><ChevronLeft className="h-4 w-4" aria-hidden /></button><span className="text-sm text-slate-300">{start}–{end} of {total}</span><button type="button" aria-label="Next" disabled={page >= pageCount - 1} onClick={() => onChange(page + 1)} className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-white/10 text-slate-200 disabled:opacity-35"><ChevronRight className="h-4 w-4" aria-hidden /></button></div>;
}

export function CameraDetailsDrawer({ children }: { children: ReactNode }) {
  return (
    <details className="glass-panel mt-5 rounded-xl p-4">
      <summary className="cursor-pointer text-sm font-semibold text-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan">Manage cameras and source diagnostics</summary>
      <div className="mt-4">{children}</div>
    </details>
  );
}

function NoCameraResults({ t }: { t: ReturnType<typeof useTranslations> }) { return <div className="glass-panel rounded-xl p-10 text-center"><Search className="mx-auto h-7 w-7 text-slate-500" aria-hidden /><p className="mt-3 text-base font-semibold text-white">{t("workspace.noResults")}</p></div>; }
function StatusDot({ status, t }: { status: CameraWallStatus, t: ReturnType<typeof useTranslations> }) { return <span className={cn("h-3 w-3 rounded-full border border-white/30", status === "live" ? "bg-emerald-400" : status === "attention" ? "bg-amber-400" : status === "offline" ? "bg-slate-400" : "bg-rose-400")} aria-label={statusCopy(status, t)} />; }
function statusPillClass(status: CameraWallStatus) { return cn("mt-1 inline-flex rounded-full px-2 py-0.5 text-[11px] font-semibold", status === "live" ? "bg-emerald-400/15 text-emerald-200" : status === "attention" ? "bg-amber-300/15 text-amber-100" : status === "offline" ? "bg-slate-300/15 text-slate-200" : "bg-rose-400/15 text-rose-100"); }


export const cameraWallInternals = { cameraDisplayName, cameraStatus, buildReviewItems, cameraCoordinates, CAMERAS_PER_PAGE };
