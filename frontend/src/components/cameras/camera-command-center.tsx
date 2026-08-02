"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Aperture,
  Car,
  CheckCircle2,
  Crosshair,
  Download,
  Expand,
  Flame,
  Info,
  Map,
  Plus,
  Play,
  ScanLine,
  ShieldAlert,
  Square,
  Trash2,
  Users,
  Video,
  WifiOff
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { EmptyState, LoadingState } from "@/components/layout/states";
import { appConfig, resolveCameraWebSocketUrl } from "@/lib/config";
import { cameraWebSocketMessageSchema } from "@/lib/schemas";
import { formatPercent } from "@/lib/data-format";
import { cn, formatTime } from "@/lib/utils";
import { getErrorMessage } from "@/lib/errors";
import {
  useCameraDetectionsQuery,
  useCameraEventsQuery,
  useCameraOverlaysQuery,
  useStartCameraMutation,
  useStopCameraMutation,
  useUpdateCameraMutation
} from "@/hooks/use-aegis-api";
import type { Camera, CameraHeatmapCell, CameraZoneOverlay, RiskEvent, RiskLevel, Track } from "@/types";

type SocketState = "idle" | "connecting" | "connected" | "reconnecting" | "error" | "unavailable";

type OverlayGeometry = {
  offsetX: number;
  offsetY: number;
  scale: number;
  sourceWidth: number;
  sourceHeight: number;
};

type ZoneType = "NORMAL" | "ELEVATED" | "HIGH_RISK" | "RESTRICTED";
type ZonePoint = { x: number; y: number };

const vehicleClasses = new Set(["car", "truck", "bus", "motorcycle", "bicycle"]);
const weaponClasses = new Set(["knife", "pistol", "gun", "weapon"]);
const riskOrder: Record<RiskLevel, number> = {
  LOW: 0,
  CANDIDATE_MEDIUM: 1,
  MEDIUM: 2,
  HIGH: 3,
  CRITICAL: 4
};

export function CameraCommandCenter({ camera }: { camera?: Camera }) {
  const panelRef = useRef<HTMLDivElement | null>(null);
  const imageRef = useRef<HTMLImageElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const zoneStartRef = useRef<ZonePoint | null>(null);
  const [frame, setFrame] = useState("");
  const [snapshotGeneration, setSnapshotGeneration] = useState(0);
  const [loadedSnapshotCameraId, setLoadedSnapshotCameraId] = useState<string | null>(null);
  const [failedSnapshotGeneration, setFailedSnapshotGeneration] = useState<number | null>(null);
  const [socketState, setSocketState] = useState<SocketState>("idle");
  const [message, setMessage] = useState("");
  const [overlayMessage, setOverlayMessage] = useState("");
  const [showDetections, setShowDetections] = useState(true);
  const [showZones, setShowZones] = useState(false);
  const [showHeatmap, setShowHeatmap] = useState(false);
  const [drawingZone, setDrawingZone] = useState(false);
  const [zoneDraft, setZoneDraft] = useState<[number, number, number, number] | null>(null);
  const [zoneName, setZoneName] = useState("");
  const [zoneType, setZoneType] = useState<ZoneType>("RESTRICTED");

  const detectionsQuery = useCameraDetectionsQuery(camera?.camera_id);
  const eventsQuery = useCameraEventsQuery(camera?.camera_id);
  const overlaysQuery = useCameraOverlaysQuery(camera?.camera_id);
  const startCamera = useStartCameraMutation();
  const stopCamera = useStopCameraMutation();
  const updateCamera = useUpdateCameraMutation();

  const detections = useMemo(() => filterCurrentDetections(detectionsQuery.data?.detections ?? []), [detectionsQuery.data?.detections]);
  const events = useMemo(() => eventsQuery.data?.events ?? [], [eventsQuery.data?.events]);
  const zones = overlaysQuery.data?.zones ?? [];
  const heatmap = overlaysQuery.data?.heatmap ?? [];
  const summary = useMemo(() => buildSummary(detections), [detections]);
  const recentActivity = useMemo(() => buildRecentActivity(events), [events]);

  useEffect(() => {
    const canRefreshSnapshot = camera?.runtime.status === "online" && camera.runtime.running;
    if (!canRefreshSnapshot) return undefined;
    const timer = window.setInterval(() => setSnapshotGeneration((value) => value + 1), 1_000);
    return () => window.clearInterval(timer);
  }, [camera?.camera_id, camera?.runtime.running, camera?.runtime.status]);

  useEffect(() => {
    const cameraId = camera?.camera_id;
    const canConnect = camera?.runtime.status === "online" && camera.runtime.running;
    if (!cameraId || !canConnect) return undefined;
    const url = resolveCameraWebSocketUrl(cameraId, "frames");
    if (!url) {
      const unavailableTimer = window.setTimeout(() => {
        setSocketState("unavailable");
        setMessage("Live stream endpoint is not configured.");
      }, 0);
      return () => window.clearTimeout(unavailableTimer);
    }

    let socket: WebSocket | undefined;
    let disposed = false;
    let opened = false;
    let retryCount = 0;
    let connectTimer: number | undefined;
    let retryTimer: number | undefined;

    function connect() {
      if (disposed) return;
      setSocketState(retryCount > 0 ? "reconnecting" : "connecting");

      try {
        socket = new WebSocket(url);
      } catch {
        setSocketState("unavailable");
        setMessage("Live stream endpoint unavailable.");
        return;
      }

      socket.onopen = () => {
        if (disposed) {
          socket?.close();
          return;
        }
        opened = true;
        retryCount = 0;
        setSocketState("connected");
        setMessage("");
      };

      socket.onmessage = (event) => {
        try {
          const parsed = cameraWebSocketMessageSchema.safeParse(JSON.parse(event.data));
          if (!parsed.success) {
            setSocketState("error");
            setMessage("Camera frame message failed frontend validation.");
            return;
          }

          if (parsed.data.type === "frame" && parsed.data.frame) {
            setFrame(parsed.data.frame);
            setMessage("");
            return;
          }

          setMessage(parsed.data.message ?? parsed.data.error_message ?? "");
        } catch {
          setSocketState("error");
          setMessage("Camera frame message was not valid JSON.");
        }
      };

      socket.onerror = () => {
        if (disposed) return;
        setSocketState("unavailable");
        setMessage("Live stream endpoint unavailable.");
      };

      socket.onclose = () => {
        if (disposed) return;
        // A socket that never completed its handshake is an endpoint failure,
        // not a live camera reconnect. Do not create a noisy retry loop.
        if (!opened) {
          setSocketState("unavailable");
          setMessage("Live stream endpoint unavailable.");
          return;
        }
        retryCount += 1;
        setSocketState("reconnecting");
        retryTimer = window.setTimeout(connect, Math.min(15_000, 1_000 * 2 ** retryCount));
      };
    }

    // Let React development-mode cleanup cancel before construction. This
    // prevents a browser warning for a deliberately closed connecting socket.
    connectTimer = window.setTimeout(connect, 0);

    return () => {
      disposed = true;
      if (connectTimer !== undefined) window.clearTimeout(connectTimer);
      if (retryTimer !== undefined) window.clearTimeout(retryTimer);
      if (socket?.readyState === WebSocket.OPEN) socket.close();
    };
  }, [camera?.camera_id, camera?.runtime.running, camera?.runtime.status]);

  useEffect(() => {
    drawOverlay();
    const image = imageRef.current;
    if (!image || typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(() => drawOverlay());
    observer.observe(image);
    return () => observer.disconnect();
    // drawOverlay deliberately redraws only when visual inputs change; making
    // its render-scoped helper a dependency would redraw after every state
    // update, including the overlay-message state it sets.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detections, frame, heatmap, showDetections, showHeatmap, showZones, snapshotGeneration, zoneDraft, zones]);

  function drawOverlay() {
    const image = imageRef.current;
    const canvas = canvasRef.current;
    if (!image || !canvas) return;

    const rect = image.getBoundingClientRect();
    const pixelRatio = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.round(rect.width * pixelRatio));
    canvas.height = Math.max(1, Math.round(rect.height * pixelRatio));
    canvas.style.width = `${rect.width}px`;
    canvas.style.height = `${rect.height}px`;

    const context = canvas.getContext("2d");
    if (!context) return;
    context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
    context.clearRect(0, 0, rect.width, rect.height);

    if (!previewSource) {
      setOverlayMessage("");
      return;
    }

    const geometry = overlayGeometry(image, rect.width, rect.height);
    if (!geometry) {
      setOverlayMessage("");
      return;
    }

    const messages: string[] = [];
    if (showHeatmap) {
      if (heatmap.length) {
        drawHeatmap(context, heatmap, geometry);
      } else {
        messages.push("Heatmap is waiting for real tracked positions.");
      }
    }

    if (showZones) {
      if (zones.length) {
        for (const zone of zones) drawZone(context, zone, geometry);
      } else {
        messages.push("No zones configured. Use Draw zone to create one on this camera.");
      }
      if (zoneDraft) drawZoneDraft(context, zoneDraft, geometry, zoneType);
    }

    if (showDetections) {
      const drawable = detections.filter((detection) => Array.isArray(detection.bbox));
      if (detections.length > 0 && drawable.length === 0) {
        messages.push("Detection boxes unavailable: backend did not return bbox.");
      }
      const occupiedLabels: Array<{ left: number; top: number; width: number; height: number }> = [];
      for (const detection of drawable) {
        drawDetection(context, detection, geometry, occupiedLabels);
      }
    }

    setOverlayMessage(messages.join(" "));
  }

  async function toggleProcessing() {
    if (!camera) return;
    if (camera.runtime.running) {
      await stopCamera.mutateAsync(camera.camera_id);
    } else {
      await startCamera.mutateAsync(camera.camera_id);
    }
  }

function openSnapshot() {
    if (!camera) return;
    window.open(`${appConfig.apiUrl}/cameras/${encodeURIComponent(camera.camera_id)}/snapshot`, "_blank", "noopener,noreferrer");
  }

  function openFullscreen() {
    void panelRef.current?.requestFullscreen?.();
  }

  async function saveZones(nextZones: CameraZoneOverlay[]) {
    if (!camera) return;
    await updateCamera.mutateAsync({
      cameraId: camera.camera_id,
      input: {
        metadata: {
          ...(camera.metadata ?? {}),
          zones: nextZones
        }
      }
    });
  }

  function beginZoneDrawing() {
    setShowZones(true);
    setDrawingZone((active) => !active);
    setZoneDraft(null);
    zoneStartRef.current = null;
  }

  function pointerToSource(event: React.PointerEvent<HTMLDivElement>): ZonePoint | null {
    const image = imageRef.current;
    if (!image) return null;
    const rect = image.getBoundingClientRect();
    const geometry = overlayGeometry(image, rect.width, rect.height);
    if (!geometry) return null;
    const x = (event.clientX - rect.left - geometry.offsetX) / geometry.scale;
    const y = (event.clientY - rect.top - geometry.offsetY) / geometry.scale;
    if (x < 0 || y < 0 || x > geometry.sourceWidth || y > geometry.sourceHeight) return null;
    return { x: clamp(x, 0, geometry.sourceWidth), y: clamp(y, 0, geometry.sourceHeight) };
  }

  function onZonePointerDown(event: React.PointerEvent<HTMLDivElement>) {
    const point = pointerToSource(event);
    if (!point) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    zoneStartRef.current = point;
    setZoneDraft([point.x, point.y, point.x, point.y]);
  }

  function onZonePointerMove(event: React.PointerEvent<HTMLDivElement>) {
    const start = zoneStartRef.current;
    const point = pointerToSource(event);
    if (!start || !point) return;
    setZoneDraft([start.x, start.y, point.x, point.y]);
  }

  function onZonePointerUp(event: React.PointerEvent<HTMLDivElement>) {
    const start = zoneStartRef.current;
    const end = pointerToSource(event);
    zoneStartRef.current = null;
    setDrawingZone(false);
    setZoneDraft(null);
    if (!start || !end) return;

    const bounds = normaliseBounds([start.x, start.y, end.x, end.y]);
    if (bounds[2] - bounds[0] < 12 || bounds[3] - bounds[1] < 12) return;
    const nextZone: CameraZoneOverlay = {
      zone_id: `zone-${Date.now().toString(36)}`,
      name: zoneName.trim() || `${zoneType.replaceAll("_", " ")} zone ${zones.length + 1}`,
      type: zoneType,
      bounds,
      active: true
    };
    void saveZones([...zones, nextZone]);
    setZoneName("");
  }

  function removeZone(zoneId: string) {
    void saveZones(zones.filter((zone) => zone.zone_id !== zoneId));
  }

  if (!camera) {
    return (
      <div className="glass-panel flex min-h-[560px] items-center justify-center rounded-lg p-6">
        <EmptyState title="Select a camera" description="Choose a registered source to open the live command view." />
      </div>
    );
  }

  const busy = startCamera.isPending || stopCamera.isPending;
  const canUseSnapshot = camera.runtime.status === "online" && camera.runtime.running === true;
  const snapshotFailed = failedSnapshotGeneration === snapshotGeneration;
  const previewSource = canUseSnapshot && !snapshotFailed
    ? frame || snapshotPreviewUrl(camera, snapshotGeneration)
    : "";
  const usingSnapshotPreview = Boolean(previewSource && !frame);
  const hasLivePreview = Boolean(frame && canUseSnapshot) || (canUseSnapshot && loadedSnapshotCameraId === camera.camera_id);
  const cameraStatus = cameraOperatorStatus(camera, socketState, summary, eventsQuery.isLoading || detectionsQuery.isLoading, eventsQuery.isError || detectionsQuery.isError, hasLivePreview);
  const displayName = cameraOperatorName(camera);
  const cameraSubtitle = cameraOperatorSubtitle(camera, cameraStatus.badge);

  return (
    <div className="grid min-h-[640px] gap-4 xl:h-[min(70vh,720px)] xl:grid-cols-[minmax(220px,0.65fr)_minmax(0,1.8fr)_minmax(260px,0.78fr)]">
      <aside className="glass-panel rounded-xl p-4 sm:p-5 xl:h-full xl:overflow-y-auto" aria-labelledby="live-activity-title">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-signal-cyan">Live activity</p>
            <h2 id="live-activity-title" className="mt-1 text-xl font-semibold text-white">Happening now</h2>
          </div>
          <ScanLine className="h-5 w-5 text-signal-cyan" aria-hidden />
        </div>

        <div className="mt-5 grid gap-3">
          <SummaryMetric icon={Users} label="People" value={summary.people} />
          <SummaryMetric icon={Car} label="Vehicles" value={summary.vehicles} />
          <SummaryMetric icon={ShieldAlert} label="Recent activity" value={recentActivity.length} tone={recentActivity.length > 0 ? "warning" : "normal"} />
          {summary.weapons > 0 ? <SummaryMetric icon={ShieldAlert} label="High-priority items" value={summary.weapons} tone="warning" /> : null}
        </div>

        <div className={cn("mt-5 rounded-lg border p-3.5", cameraStatus.tone === "danger" ? "border-amber-300/35 bg-amber-300/[0.07]" : cameraStatus.tone === "offline" ? "border-rose-400/30 bg-rose-500/[0.06]" : "border-emerald-300/25 bg-emerald-400/[0.05]")}>
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-400">Status</p>
          <div className="mt-2 flex items-center gap-2">
            {cameraStatus.tone === "offline" ? <WifiOff className="h-4 w-4 text-rose-200" aria-hidden /> : cameraStatus.tone === "danger" ? <ShieldAlert className="h-4 w-4 text-amber-200" aria-hidden /> : <CheckCircle2 className="h-4 w-4 text-emerald-300" aria-hidden />}
            <span className={cn("text-base font-semibold", cameraStatus.tone === "offline" ? "text-rose-100" : cameraStatus.tone === "danger" ? "text-amber-100" : "text-emerald-100")}>{cameraStatus.label}</span>
          </div>
          <p className="mt-1 text-xs leading-relaxed text-slate-300">{cameraStatus.detail}</p>
        </div>
      </aside>

      <section ref={panelRef} className="glass-panel min-w-0 overflow-hidden rounded-xl xl:h-full" aria-labelledby="selected-camera-title">
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-white/10 px-4 py-4 sm:px-5">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2.5">
              <h2 id="selected-camera-title" className="truncate text-xl font-semibold text-white">{displayName}</h2>
              <span className={cn("rounded-full border px-2.5 py-1 text-xs font-semibold", cameraStatus.tone === "live" ? "border-emerald-300/40 bg-emerald-400/[0.10] text-emerald-200" : cameraStatus.tone === "offline" ? "border-rose-300/30 bg-rose-400/[0.08] text-rose-100" : "border-amber-300/35 bg-amber-300/[0.08] text-amber-100")}>{cameraStatus.badge}</span>
            </div>
            <p className="mt-1.5 text-sm text-slate-400">{cameraSubtitle}</p>
          </div>

          <details className="group relative shrink-0">
            <summary className="cursor-pointer list-none rounded-md border border-white/10 bg-white/[0.035] px-3 py-2 text-xs font-medium text-slate-200 transition hover:border-signal-cyan/35 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan">
              <span className="inline-flex items-center gap-1.5"><Info className="h-3.5 w-3.5" aria-hidden /> Details</span>
            </summary>
            <div className="absolute right-0 z-30 mt-2 w-72 rounded-lg border border-white/10 bg-command-950 p-3 text-xs shadow-2xl">
              <p className="font-semibold text-white">Camera diagnostics</p>
              <dl className="mt-3 grid gap-2 text-slate-300">
                <div className="flex justify-between gap-3"><dt>Source</dt><dd className="text-right text-white">{sourceLabel(camera.source_type)}</dd></div>
                <div className="flex justify-between gap-3"><dt>Resolution</dt><dd className="text-right text-white">{camera.runtime.width && camera.runtime.height ? `${camera.runtime.width} × ${camera.runtime.height}` : "Unavailable"}</dd></div>
                <div className="flex justify-between gap-3"><dt>Frame rate</dt><dd className="text-right text-white">{camera.runtime.fps == null ? "Unavailable" : `${camera.runtime.fps.toFixed(1)} FPS`}</dd></div>
                <div className="flex justify-between gap-3"><dt>Last frame</dt><dd className="text-right text-white">{formatTime(camera.runtime.last_frame_time ?? undefined)}</dd></div>
                <div className="flex justify-between gap-3"><dt>Pipeline</dt><dd className="text-right text-white">{camera.runtime.running ? "Running" : "Stopped"}</dd></div>
                <div className="flex justify-between gap-3"><dt>Camera reference</dt><dd className="max-w-36 break-all text-right text-white">{camera.camera_id}</dd></div>
              </dl>
              {camera.runtime.error_message ? <p className="mt-3 rounded border border-rose-300/25 bg-rose-400/[0.06] p-2 text-rose-100">{camera.runtime.error_message}</p> : null}
            </div>
          </details>
        </div>

        <div className="relative aspect-video min-h-[420px] bg-black">
          {previewSource ? (
            <>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                ref={imageRef}
                src={previewSource}
                alt={`${displayName} live preview`}
                className="h-full w-full object-contain"
                onLoad={() => {
                  if (usingSnapshotPreview) setLoadedSnapshotCameraId(camera.camera_id);
                  drawOverlay();
                }}
                onError={() => {
                  if (usingSnapshotPreview) setFailedSnapshotGeneration(snapshotGeneration);
                }}
              />
              <canvas ref={canvasRef} className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden />
            </>
          ) : (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-center text-slate-400">
              <Video className="h-9 w-9 text-slate-600" aria-hidden />
              <div>
                <p className="text-sm font-medium text-slate-200">{cameraStatus.tone === "offline" ? "Camera offline - check connection." : "Live data is temporarily unavailable."}</p>
                <p className="mt-1 text-xs text-slate-500">{message ? "Open Details for diagnostics." : previewMessage(camera)}</p>
              </div>
            </div>
          )}

          {overlayMessage ? (
            <p className="absolute left-4 top-4 rounded-md border border-amber-300/25 bg-command-950/88 px-3 py-2 text-xs text-amber-100">
              {overlayMessage}
            </p>
          ) : null}

          {showZones ? (
            <div className="absolute right-4 top-4 z-20 w-64 rounded-md border border-white/10 bg-command-950/90 p-3 text-xs shadow-xl backdrop-blur-xl">
              <div className="flex items-center justify-between gap-3">
                <p className="font-medium text-white">Camera zones</p>
                <span className="rounded border border-white/10 px-1.5 py-0.5 text-[10px] text-slate-300">{zones.length} saved</span>
              </div>
              <p className="mt-1 text-slate-400">Draw and review zones for this camera.</p>
              <div className="mt-3 grid gap-2">
                <input
                  value={zoneName}
                  onChange={(event) => setZoneName(event.target.value)}
                  className="h-8 rounded border border-white/10 bg-black/25 px-2 text-xs text-white outline-none placeholder:text-slate-500 focus:border-signal-cyan/50"
                  placeholder="Zone name (optional)"
                  disabled={drawingZone || updateCamera.isPending}
                />
                <select
                  value={zoneType}
                  onChange={(event) => setZoneType(event.target.value as ZoneType)}
                  className="h-8 rounded border border-white/10 bg-black/25 px-2 text-xs text-white outline-none focus:border-signal-cyan/50"
                  disabled={drawingZone || updateCamera.isPending}
                >
                  <option value="RESTRICTED">Restricted</option>
                  <option value="HIGH_RISK">High priority</option>
                  <option value="ELEVATED">Elevated attention</option>
                  <option value="NORMAL">Normal</option>
                </select>
                <Button type="button" variant={drawingZone ? "secondary" : "primary"} className="min-h-8 px-2 text-xs" onClick={beginZoneDrawing} disabled={updateCamera.isPending}>
                  <Plus className="h-3.5 w-3.5" aria-hidden />
                  {drawingZone ? "Cancel drawing" : "Draw zone"}
                </Button>
              </div>
              {zones.length ? (
                <div className="mt-3 max-h-28 space-y-1 overflow-y-auto pr-1">
                  {zones.map((zone) => (
                    <div key={zone.zone_id} className="flex items-center justify-between gap-2 rounded border border-white/8 bg-white/[0.035] px-2 py-1.5">
                      <span className="min-w-0 truncate text-slate-200">{zone.name}</span>
                      <button type="button" className="text-rose-200 hover:text-rose-100" onClick={() => removeZone(zone.zone_id)} title={`Remove ${zone.name}`}>
                        <Trash2 className="h-3.5 w-3.5" aria-hidden />
                      </button>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}

          {drawingZone ? (
            <div
              className="absolute inset-0 z-10 cursor-crosshair"
              onPointerDown={onZonePointerDown}
              onPointerMove={onZonePointerMove}
              onPointerUp={onZonePointerUp}
              onPointerCancel={() => {
                zoneStartRef.current = null;
                setDrawingZone(false);
                setZoneDraft(null);
              }}
            />
          ) : null}

          <div className="absolute inset-x-4 bottom-4 z-20 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-white/10 bg-command-950/82 p-2 backdrop-blur-xl">
            <div className="flex flex-wrap gap-2">
              <ToggleButton pressed={showDetections} onClick={() => setShowDetections((value) => !value)} icon={Crosshair} label="View detections" />
              <ToggleButton pressed={showZones} onClick={() => setShowZones((value) => !value)} icon={Map} label="Zones" />
              <ToggleButton pressed={showHeatmap} onClick={() => setShowHeatmap((value) => !value)} icon={Flame} label="Heatmap" />
            </div>
            <div className="flex flex-wrap gap-2">
              <ToolbarButton onClick={openSnapshot} icon={Download} label="Snapshot" />
              <ToolbarButton onClick={openFullscreen} icon={Expand} label="Fullscreen" />
              <Button type="button" variant={camera.runtime.running ? "secondary" : "primary"} className="min-h-9 px-3" disabled={busy} onClick={toggleProcessing}>
                {camera.runtime.running ? <Square className="h-4 w-4" aria-hidden /> : <Play className="h-4 w-4" aria-hidden />}
                {camera.runtime.running ? "Stop" : "Start"}
              </Button>
            </div>
          </div>
        </div>
      </section>

      <aside className="glass-panel min-w-0 rounded-xl p-4 sm:p-5 xl:h-full xl:overflow-y-auto" aria-labelledby="recent-activity-title">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-signal-cyan">Review queue</p>
            <h2 id="recent-activity-title" className="mt-1 text-xl font-semibold text-white">Recent activity</h2>
          </div>
          <Aperture className="h-5 w-5 text-signal-cyan" aria-hidden />
        </div>

        <div className="mt-4">
          {eventsQuery.isLoading ? <LoadingState label="Loading activity" /> : null}
          {eventsQuery.isError ? <ConciseDataError error={eventsQuery.error} /> : null}
          {!eventsQuery.isLoading && !eventsQuery.isError && events.length === 0 ? (
            <EmptyState title="No activity to review." description="" />
          ) : null}
          <div className="space-y-3">
            {recentActivity.map((event, index) => (
              <RecentActivityCard key={eventKey(event, index)} event={event} />
            ))}
          </div>
        </div>
      </aside>
    </div>
  );
}

function SummaryMetric({
  icon: Icon,
  label,
  value,
  tone = "normal"
}: {
  icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  label: string;
  value: number;
  tone?: "normal" | "warning";
}) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-md border border-white/10 bg-black/20 p-3">
      <div className="flex items-center gap-3">
        <span className={cn("flex h-9 w-9 items-center justify-center rounded-md border", tone === "warning" ? "border-amber-300/30 bg-amber-300/10 text-amber-200" : "border-signal-cyan/20 bg-signal-cyan/10 text-signal-cyan")}>
          <Icon className="h-4 w-4" aria-hidden />
        </span>
        <span className="text-sm text-slate-300">{label}</span>
      </div>
      <span className="font-mono text-lg text-white">{value}</span>
    </div>
  );
}

function ToggleButton({
  pressed,
  onClick,
  icon: Icon,
  label
}: {
  pressed: boolean;
  onClick: () => void;
  icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  label: string;
}) {
  return (
    <button
      type="button"
      className={cn(
        "inline-flex min-h-9 items-center gap-2 rounded-md border px-3 text-xs font-medium transition",
        pressed ? "border-signal-cyan/35 bg-signal-cyan/12 text-signal-cyan" : "border-white/10 bg-white/[0.04] text-slate-300 hover:bg-white/10"
      )}
      onClick={onClick}
      aria-pressed={pressed}
      title={label}
    >
      <Icon className="h-4 w-4" aria-hidden />
      <span className="hidden sm:inline">{label}</span>
    </button>
  );
}

function ToolbarButton({
  onClick,
  icon: Icon,
  label
}: {
  onClick: () => void;
  icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  label: string;
}) {
  return (
    <button
      type="button"
      className="inline-flex min-h-9 items-center gap-2 rounded-md border border-white/10 bg-white/[0.04] px-3 text-xs font-medium text-slate-300 transition hover:bg-white/10 hover:text-white"
      onClick={onClick}
      title={label}
    >
      <Icon className="h-4 w-4" aria-hidden />
      <span className="hidden sm:inline">{label}</span>
    </button>
  );
}

function RecentActivityCard({ event }: { event: RiskEvent }) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const status = activityStatus(event);

  return (
    <article className={cn("rounded-lg border p-3.5", status.tone === "high" ? "border-amber-300/45 bg-amber-300/[0.07]" : status.tone === "attention" ? "border-signal-cyan/35 bg-signal-cyan/[0.05]" : "border-emerald-300/30 bg-emerald-400/[0.045]")}>
      <div className="flex items-start gap-3">
        <span className={cn("mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border", status.tone === "high" ? "border-amber-300/55 text-amber-200" : status.tone === "attention" ? "border-signal-cyan/45 text-signal-cyan" : "border-emerald-300/45 text-emerald-200")}>
          {status.tone === "high" ? <ShieldAlert className="h-4 w-4" aria-hidden /> : status.tone === "attention" ? <Aperture className="h-4 w-4" aria-hidden /> : <CheckCircle2 className="h-4 w-4" aria-hidden />}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold leading-snug text-white">{status.summary}</p>
          <p className="mt-1 text-xs text-slate-400">{formatTime(String(event.timestamp ?? ""))}</p>
          <button type="button" onClick={() => setDetailsOpen((open) => !open)} className="mt-3 inline-flex min-h-8 items-center text-xs font-semibold text-signal-cyan hover:text-cyan-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan">
            {detailsOpen ? "Hide details" : "View details"}
          </button>
        </div>
      </div>
      {detailsOpen ? <ActivityDetails event={event} /> : null}
    </article>
  );
}

function ActivityDetails({ event }: { event: RiskEvent }) {
  return (
    <details open className="mt-3 border-t border-white/10 pt-3">
      <summary className="cursor-pointer text-xs font-semibold text-slate-200">Why did Aegis flag this?</summary>
      <dl className="mt-3 grid gap-2 text-xs text-slate-400">
        <div className="flex justify-between gap-4"><dt>Object</dt><dd className="text-right text-white">{event.object_class ?? event.object_type ?? event.class_name ?? "Unavailable"}</dd></div>
        <div className="flex justify-between gap-4"><dt>Confidence</dt><dd className="text-right text-white">{formatPercent(event.confidence, "Unavailable")}</dd></div>
        <div className="flex justify-between gap-4"><dt>Track reference</dt><dd className="max-w-36 break-all text-right text-white">{event.track_id == null ? "Unavailable" : String(event.track_id)}</dd></div>
        <div className="flex justify-between gap-4"><dt>Reason codes</dt><dd className="max-w-40 break-words text-right text-white">{event.reason_codes?.join(", ") || "Unavailable"}</dd></div>
        <div className="flex justify-between gap-4"><dt>Model source</dt><dd className="max-w-40 break-words text-right text-white">{event.model_source?.join(", ") || "Unavailable"}</dd></div>
        <div className="flex justify-between gap-4"><dt>Evidence time</dt><dd className="text-right text-white">{formatTime(String(event.timestamp ?? ""))}</dd></div>
      </dl>
    </details>
  );
}

function ConciseDataError({ error }: { error: unknown }) {
  return (
    <div className="rounded-lg border border-rose-300/25 bg-rose-400/[0.06] p-3 text-sm text-rose-100" role="status">
      <p>Live data is temporarily unavailable.</p>
      <details className="mt-2 text-xs text-rose-100/85"><summary className="cursor-pointer font-semibold">Diagnostics</summary><p className="mt-2 break-words">{getErrorMessage(error)}</p></details>
    </div>
  );
}

function filterCurrentDetections(detections: Track[]) {
  const latestFrame = Math.max(...detections.map((detection) => detection.frame_number ?? detection.frame_id ?? 0), 0);
  if (!latestFrame) return detections.slice(0, 60);
  return detections.filter((detection) => (detection.frame_number ?? detection.frame_id ?? latestFrame) >= latestFrame - 1).slice(0, 80);
}

function buildSummary(detections: Track[]) {
  const people = detections.filter((detection) => detection.is_person || className(detection) === "person").length;
  const vehicles = detections.filter((detection) => vehicleClasses.has(className(detection))).length;
  const weapons = detections.filter((detection) => detection.is_weapon || weaponClasses.has(className(detection))).length;
  const riskLevel = detections.reduce<RiskLevel | undefined>((current, detection) => {
    if (!detection.risk_level) return current;
    if (!current) return detection.risk_level;
    return riskOrder[detection.risk_level] > riskOrder[current] ? detection.risk_level : current;
  }, undefined);
  return {
    people,
    vehicles,
    weapons,
    riskLevel
  };
}

function cameraOperatorStatus(
  camera: Camera,
  socketState: SocketState,
  summary: { riskLevel?: RiskLevel },
  isLoading: boolean,
  hasDataError: boolean,
  hasLivePreview: boolean,
) {
  const offline = ["offline", "error", "stopped"].includes(camera.runtime.status);
  if (offline) return { tone: "offline" as const, label: "Camera offline", badge: "Offline", detail: "Camera offline - check connection." };
  if (hasDataError) return { tone: "offline" as const, label: "Information unavailable", badge: "Unavailable", detail: "Live data is temporarily unavailable." };
  if (summary.riskLevel === "CRITICAL" || summary.riskLevel === "HIGH") return { tone: "danger" as const, label: "High priority", badge: "Review", detail: "High-priority activity needs review." };
  if (summary.riskLevel === "MEDIUM" || summary.riskLevel === "CANDIDATE_MEDIUM") return { tone: "danger" as const, label: "Needs attention", badge: "Monitoring", detail: "Review the recent activity queue." };
  if (hasLivePreview) return { tone: "live" as const, label: "Live monitoring", badge: "Live", detail: "Live camera data is available." };
  if (isLoading || socketState === "connecting" || socketState === "reconnecting" || !camera.runtime.running) return { tone: "danger" as const, label: "Monitoring", badge: "Connecting", detail: "Waiting for live camera activity." };
  if (socketState === "unavailable" || socketState === "error") return { tone: "offline" as const, label: "Information unavailable", badge: "Unavailable", detail: "Live preview is temporarily unavailable." };
  return { tone: "live" as const, label: "Live monitoring", badge: "Live", detail: "Live camera data is available." };
}

function activityStatus(event: RiskEvent) {
  const level = String(event.risk_level ?? event.severity ?? event.level ?? "").toUpperCase();
  const object = friendlyObjectName(event.object_class ?? event.object_type ?? event.class_name);
  const reason = `${event.explanation ?? ""} ${event.description ?? ""} ${event.reason ?? ""}`.toLowerCase();
  if (reason.includes("offline") || reason.includes("connection")) return { tone: "high" as const, summary: "Camera offline - check connection" };
  if (["CRITICAL", "HIGH"].includes(level)) return { tone: "high" as const, summary: "High-priority activity needs review" };
  if (["MEDIUM", "CANDIDATE_MEDIUM", "WARNING"].includes(level)) return { tone: "attention" as const, summary: `${object ?? "Activity"} needs attention` };
  if (object) return { tone: "normal" as const, summary: `${object} activity reported` };
  return { tone: "attention" as const, summary: "Activity reported" };
}

function friendlyObjectName(value?: string) {
  if (!value) return null;
  const normalized = value.trim().toLowerCase();
  if (normalized === "person") return "Person";
  if (vehicleClasses.has(normalized)) return `${normalized[0]?.toUpperCase()}${normalized.slice(1)}`;
  if (weaponClasses.has(normalized)) return "Potential weapon";
  return null;
}

function overlayGeometry(image: HTMLImageElement, renderedWidth: number, renderedHeight: number): OverlayGeometry | null {
  const sourceWidth = image.naturalWidth;
  const sourceHeight = image.naturalHeight;
  if (!sourceWidth || !sourceHeight || !renderedWidth || !renderedHeight) return null;
  const scale = Math.min(renderedWidth / sourceWidth, renderedHeight / sourceHeight);
  const drawWidth = sourceWidth * scale;
  const drawHeight = sourceHeight * scale;
  return {
    offsetX: (renderedWidth - drawWidth) / 2,
    offsetY: (renderedHeight - drawHeight) / 2,
    scale,
    sourceWidth,
    sourceHeight
  };
}

function drawHeatmap(context: CanvasRenderingContext2D, cells: CameraHeatmapCell[], geometry: OverlayGeometry) {
  context.save();
  context.globalCompositeOperation = "screen";
  for (const cell of cells) {
    const x = geometry.offsetX + clamp(cell.x, 0, geometry.sourceWidth) * geometry.scale;
    const y = geometry.offsetY + clamp(cell.y, 0, geometry.sourceHeight) * geometry.scale;
    const width = Math.max(1, Math.min(cell.width, geometry.sourceWidth - cell.x) * geometry.scale);
    const height = Math.max(1, Math.min(cell.height, geometry.sourceHeight - cell.y) * geometry.scale);
    const intensity = clamp(cell.intensity, 0, 1);
    const gradient = context.createRadialGradient(x + width / 2, y + height / 2, 0, x + width / 2, y + height / 2, Math.max(width, height) * 0.72);
    gradient.addColorStop(0, `rgba(251, 113, 133, ${0.15 + intensity * 0.48})`);
    gradient.addColorStop(0.52, `rgba(245, 158, 11, ${0.08 + intensity * 0.24})`);
    gradient.addColorStop(1, "rgba(245, 158, 11, 0)");
    context.fillStyle = gradient;
    context.fillRect(x, y, width, height);
  }
  context.restore();
}

function drawZone(context: CanvasRenderingContext2D, zone: CameraZoneOverlay, geometry: OverlayGeometry) {
  if (!zone.active) return;
  const [x1, y1, x2, y2] = zone.bounds;
  drawZoneBounds(context, [x1, y1, x2, y2], geometry, zone.type, zone.name);
}

function drawZoneDraft(context: CanvasRenderingContext2D, bounds: [number, number, number, number], geometry: OverlayGeometry, type: ZoneType) {
  drawZoneBounds(context, normaliseBounds(bounds), geometry, type, "New zone");
}

function drawZoneBounds(
  context: CanvasRenderingContext2D,
  bounds: [number, number, number, number],
  geometry: OverlayGeometry,
  type: string,
  label: string,
) {
  const [x1, y1, x2, y2] = bounds;
  const left = geometry.offsetX + clamp(x1, 0, geometry.sourceWidth) * geometry.scale;
  const top = geometry.offsetY + clamp(y1, 0, geometry.sourceHeight) * geometry.scale;
  const right = geometry.offsetX + clamp(x2, 0, geometry.sourceWidth) * geometry.scale;
  const bottom = geometry.offsetY + clamp(y2, 0, geometry.sourceHeight) * geometry.scale;
  const width = Math.max(1, right - left);
  const height = Math.max(1, bottom - top);
  const style = zoneStyle(type);

  context.save();
  context.fillStyle = style.fill;
  context.strokeStyle = style.stroke;
  context.lineWidth = 2;
  context.setLineDash([7, 5]);
  context.fillRect(left, top, width, height);
  context.strokeRect(left, top, width, height);
  context.setLineDash([]);
  context.font = "12px Inter, system-ui, sans-serif";
  const labelWidth = Math.min(context.measureText(label).width + 14, width);
  context.fillStyle = style.labelBackground;
  roundedRect(context, left + 4, top + 4, Math.max(40, labelWidth), 22, 5);
  context.fill();
  context.fillStyle = style.labelText;
  context.fillText(label, left + 10, top + 19);
  context.restore();
}

function zoneStyle(type: string) {
  if (type === "RESTRICTED") {
    return { stroke: "#fb7185", fill: "rgba(244, 63, 94, 0.13)", labelBackground: "rgba(136, 19, 55, 0.92)", labelText: "#fff1f2" };
  }
  if (type === "HIGH_RISK") {
    return { stroke: "#f59e0b", fill: "rgba(245, 158, 11, 0.13)", labelBackground: "rgba(120, 53, 15, 0.92)", labelText: "#fffbeb" };
  }
  if (type === "ELEVATED") {
    return { stroke: "#a78bfa", fill: "rgba(167, 139, 250, 0.12)", labelBackground: "rgba(76, 29, 149, 0.92)", labelText: "#f5f3ff" };
  }
  return { stroke: "#22d3ee", fill: "rgba(34, 211, 238, 0.09)", labelBackground: "rgba(8, 47, 73, 0.92)", labelText: "#ecfeff" };
}

function normaliseBounds([x1, y1, x2, y2]: [number, number, number, number]): [number, number, number, number] {
  return [Math.min(x1, x2), Math.min(y1, y2), Math.max(x1, x2), Math.max(y1, y2)];
}

export function overlayLabel(detection: Pick<Track, "class_name" | "confidence">) {
  const object = friendlyObjectName(detection.class_name) ?? "Object";
  const confidence = typeof detection.confidence === "number" && detection.confidence >= 0 && detection.confidence <= 1
    ? ` ${formatPercent(detection.confidence)}`
    : "";
  return `${object}${confidence}`;
}

function drawDetection(
  context: CanvasRenderingContext2D,
  detection: Track,
  geometry: OverlayGeometry,
  occupiedLabels: Array<{ left: number; top: number; width: number; height: number }>,
) {
  if (!detection.bbox) return;
  const [x1, y1, x2, y2] = detection.bbox;
  const left = geometry.offsetX + clamp(x1, 0, geometry.sourceWidth) * geometry.scale;
  const top = geometry.offsetY + clamp(y1, 0, geometry.sourceHeight) * geometry.scale;
  const right = geometry.offsetX + clamp(x2, 0, geometry.sourceWidth) * geometry.scale;
  const bottom = geometry.offsetY + clamp(y2, 0, geometry.sourceHeight) * geometry.scale;
  const width = Math.max(1, right - left);
  const height = Math.max(1, bottom - top);
  const style = overlayStyle(detection);
  const label = overlayLabel(detection);

  context.save();
  context.lineWidth = style.lineWidth;
  context.strokeStyle = style.stroke;
  context.fillStyle = style.fill;
  roundedRect(context, left, top, width, height, 7);
  context.fill();
  roundedRect(context, left, top, width, height, 7);
  context.stroke();

  context.font = "12px Inter, system-ui, sans-serif";
  const labelWidth = Math.min(context.measureText(label).width + 16, Math.max(width, 72));
  const labelHeight = 24;
  const labelCandidates = [
    top > labelHeight + 6 ? top - labelHeight - 5 : top + 5,
    top + height + 5,
    top + 5,
  ];
  const labelY = labelCandidates.find((candidate) => !occupiedLabels.some((occupied) =>
    left < occupied.left + occupied.width && left + labelWidth > occupied.left && candidate < occupied.top + occupied.height && candidate + labelHeight > occupied.top,
  )) ?? labelCandidates[0];
  occupiedLabels.push({ left, top: labelY, width: labelWidth, height: labelHeight });
  context.fillStyle = style.labelBackground;
  roundedRect(context, left, labelY, labelWidth, labelHeight, 6);
  context.fill();
  context.fillStyle = style.labelText;
  context.fillText(label, left + 8, labelY + 16);

  context.restore();
}

function overlayStyle(detection: Track) {
  const name = className(detection);
  const isWeapon = detection.is_weapon || weaponClasses.has(name);
  const critical = isWeapon && detection.risk_level === "CRITICAL" && detection.verification_status === "confirmed";
  if (critical) {
    return {
      stroke: "#f0abfc",
      fill: "rgba(217, 70, 239, 0.10)",
      labelBackground: "rgba(112, 26, 117, 0.9)",
      labelText: "#fff7ff",
      lineWidth: 2.5
    };
  }
  if (isWeapon) {
    return {
      stroke: "#f59e0b",
      fill: "rgba(245, 158, 11, 0.10)",
      labelBackground: "rgba(120, 53, 15, 0.9)",
      labelText: "#fffbeb",
      lineWidth: 2.25
    };
  }
  if (vehicleClasses.has(name)) {
    return {
      stroke: "#60a5fa",
      fill: "rgba(96, 165, 250, 0.08)",
      labelBackground: "rgba(30, 58, 138, 0.9)",
      labelText: "#eff6ff",
      lineWidth: 1.75
    };
  }
  return {
    stroke: "#22d3ee",
    fill: "rgba(34, 211, 238, 0.07)",
    labelBackground: "rgba(8, 47, 73, 0.9)",
    labelText: "#ecfeff",
    lineWidth: 1.75
  };
}

function roundedRect(context: CanvasRenderingContext2D, x: number, y: number, width: number, height: number, radius: number) {
  const safeRadius = Math.min(radius, width / 2, height / 2);
  context.beginPath();
  context.moveTo(x + safeRadius, y);
  context.lineTo(x + width - safeRadius, y);
  context.quadraticCurveTo(x + width, y, x + width, y + safeRadius);
  context.lineTo(x + width, y + height - safeRadius);
  context.quadraticCurveTo(x + width, y + height, x + width - safeRadius, y + height);
  context.lineTo(x + safeRadius, y + height);
  context.quadraticCurveTo(x, y + height, x, y + height - safeRadius);
  context.lineTo(x, y + safeRadius);
  context.quadraticCurveTo(x, y, x + safeRadius, y);
  context.closePath();
}

function className(detection: Track) {
  return String(detection.class_name ?? "unknown").toLowerCase();
}

function eventKey(event: RiskEvent, index: number) {
  return String(event.event_id ?? event.id ?? `${event.timestamp ?? "event"}-${event.track_id ?? index}`);
}

/** Keep the camera review queue readable without hiding high-priority evidence. */
function buildRecentActivity(events: RiskEvent[]) {
  const seenRoutineObject = new Set<string>();
  return events
    .slice()
    .sort((left, right) => eventTimestamp(right) - eventTimestamp(left))
    .filter((event) => {
      const level = String(event.risk_level ?? event.severity ?? event.level ?? "").toUpperCase();
      if (["CRITICAL", "HIGH", "MEDIUM", "CANDIDATE_MEDIUM", "WARNING"].includes(level)) return true;
      const object = friendlyObjectName(event.object_class ?? event.object_type ?? event.class_name) ?? "Activity";
      if (seenRoutineObject.has(object)) return false;
      seenRoutineObject.add(object);
      return true;
    })
    .slice(0, 5);
}

function eventTimestamp(event: RiskEvent) {
  if (typeof event.timestamp === "number") return event.timestamp * 1_000;
  return typeof event.timestamp === "string" ? Date.parse(event.timestamp) || 0 : 0;
}

function sourceLabel(source: Camera["source_type"]) {
  const labels: Record<Camera["source_type"], string> = {
    LOCAL_DEVICE: "Local camera",
    RTSP_STREAM: "Network camera",
    HTTP_STREAM: "HTTP stream",
    BROWSER_WEBCAM: "Browser camera",
    UPLOADED_VIDEO: "Uploaded video"
  };
  return labels[source];
}

function cameraOperatorName(camera: Camera) {
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

function cameraOperatorSubtitle(camera: Camera, badge: string) {
  if (badge === "Offline") return "Camera offline";
  if (badge === "Unavailable") return "Information unavailable";
  if (["connecting", "reconnecting"].includes(camera.runtime.status) || badge === "Connecting") return "Live image delayed";
  return "Live camera";
}

function previewMessage(camera: Camera) {
  if (!camera.runtime.running) return "Start this camera to view live activity.";
  return "Waiting for the first camera frame.";
}

function snapshotPreviewUrl(camera: Camera, generation: number) {
  return `${appConfig.apiUrl}/cameras/${encodeURIComponent(camera.camera_id)}/snapshot?preview=${generation}`;
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

export const cameraCommandCenterInternals = { buildRecentActivity };
