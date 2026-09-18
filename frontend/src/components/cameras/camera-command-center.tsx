"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
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
import { EmptyState } from "@/components/layout/states";
import { appConfig, createAuthenticatedWebSocket, resolveCameraWebSocketUrl } from "@/lib/config";
import { cameraWebSocketMessageSchema } from "@/lib/schemas";
import { formatPercent } from "@/lib/data-format";
import { cn, formatTime } from "@/lib/utils";
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

// A snapshot is a complete JPEG response, not a video frame. Refreshing it
// faster than the backend can produce and decode it cancels the image load and
// leaves the canvas black. The WebSocket path supplies faster updates when it
// is configured; this is the reliable local fallback.
const SNAPSHOT_PREVIEW_INTERVAL_MS = 500;

export function CameraCommandCenter({ camera, cameraSwitcher }: { camera?: Camera; cameraSwitcher?: React.ReactNode }) {
  const panelRef = useRef<HTMLDivElement | null>(null);
  const imageRef = useRef<HTMLImageElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const activeBitmapRef = useRef<ImageBitmap | null>(null);
  const drawOverlayRef = useRef<() => void>(() => {});
  const [wsDetections, setWsDetections] = useState<Track[] | null>(null);
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

  const detections = useMemo(
    () => {
      if (wsDetections) return wsDetections;
      return camera?.runtime.status === "online"
        ? filterCurrentDetections(detectionsQuery.data?.detections ?? [], Date.now())
        : [];
    },
    [camera?.runtime.status, detectionsQuery.data?.detections, wsDetections]
  );
  const events = useMemo(() => eventsQuery.data?.events ?? [], [eventsQuery.data?.events]);
  const zones = overlaysQuery.data?.zones ?? [];
  const heatmap = overlaysQuery.data?.heatmap ?? [];
  const summary = useMemo(() => buildSummary(detections), [detections]);
  const recentActivity = useMemo(() => buildRecentActivity(events), [events]);

  useEffect(() => {
    const canRefreshSnapshot = camera?.runtime.status === "online" && camera.runtime.running;
    if (!canRefreshSnapshot) return undefined;
    const timer = window.setInterval(
      () => setSnapshotGeneration((value) => value + 1),
      SNAPSHOT_PREVIEW_INTERVAL_MS,
    );
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
        setMessage("Live stream is not configured.");
      }, 0);
      return () => window.clearTimeout(unavailableTimer);
    }

    let socket: WebSocket | undefined;
    let disposed = false;
    let opened = false;
    let retryCount = 0;
    let connectTimer: number | undefined;
    let retryTimer: number | undefined;

    async function connect() {
      if (disposed) return;
      setSocketState(retryCount > 0 ? "reconnecting" : "connecting");
      opened = false;

      try {
        socket = await createAuthenticatedWebSocket(url);
        if (disposed) {
          socket.close();
          return;
        }
      } catch {
        setSocketState("unavailable");
        setMessage("Live stream is temporarily unavailable.");
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
            setMessage("A live image update could not be read.");
            return;
          }

          if (parsed.data.type === "frame" && parsed.data.frame) {
            setFrame(parsed.data.frame);
            if (parsed.data.detections) {
              setWsDetections(parsed.data.detections);
            }

            // Async decode frame for precise canvas rendering
            fetch(parsed.data.frame)
              .then((res) => res.blob())
              .then(createImageBitmap)
              .then((bitmap) => {
                if (activeBitmapRef.current) activeBitmapRef.current.close();
                activeBitmapRef.current = bitmap;
                requestAnimationFrame(() => drawOverlayRef.current());
              })
              .catch(() => {});

            setMessage("");
            return;
          }

          setMessage(parsed.data.message || parsed.data.error_message ? "Live stream needs attention." : "");
        } catch {
          setSocketState("error");
          setMessage("Camera frame message was not valid JSON.");
        }
      };

      socket.onerror = () => {
        if (disposed) return;
        setSocketState("unavailable");
        setMessage("Live stream is temporarily unavailable.");
      };

      socket.onclose = () => {
        if (disposed) return;
        // A socket that never completed its handshake is an endpoint failure,
        // not a live camera reconnect. Do not create a noisy retry loop.
        if (!opened) {
          setSocketState("unavailable");
          setMessage("Live stream is temporarily unavailable.");
          return;
        }
        retryCount += 1;
        setSocketState("reconnecting");
        retryTimer = window.setTimeout(() => void connect(), Math.min(15_000, 1_000 * 2 ** retryCount));
      };
    }

    // Let React development-mode cleanup cancel before construction. This
    // prevents a browser warning for a deliberately closed connecting socket.
    connectTimer = window.setTimeout(() => void connect(), 0);

    return () => {
      disposed = true;
      if (connectTimer !== undefined) window.clearTimeout(connectTimer);
      if (retryTimer !== undefined) window.clearTimeout(retryTimer);
      if (socket?.readyState === WebSocket.OPEN) socket.close();
    };
  }, [camera?.camera_id, camera?.runtime.running, camera?.runtime.status]);

  useEffect(() => {
    drawOverlay();
    const canvas = canvasRef.current;
    if (!canvas || typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(() => drawOverlay());
    observer.observe(canvas.parentElement || canvas);
    return () => observer.disconnect();
    // drawOverlay deliberately redraws only when visual inputs change; making
    // its render-scoped helper a dependency would redraw after every state
    // update, including the overlay-message state it sets.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detections, frame, heatmap, showDetections, showHeatmap, showZones, snapshotGeneration, zoneDraft, zones]);

  drawOverlayRef.current = drawOverlay;
  function drawOverlay() {
    const canvas = canvasRef.current;
    const container = canvas?.parentElement;
    if (!container || !canvas) return;

    const rect = container.getBoundingClientRect();
    const pixelRatio = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.round(rect.width * pixelRatio));
    canvas.height = Math.max(1, Math.round(rect.height * pixelRatio));
    canvas.style.width = `${rect.width}px`;
    canvas.style.height = `${rect.height}px`;

    const context = canvas.getContext("2d");
    if (!context) return;
    context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
    context.clearRect(0, 0, rect.width, rect.height);

    if (!activeBitmapRef.current && !previewSource) {
      setOverlayMessage("");
      return;
    }

    const imageToMeasure = activeBitmapRef.current ? { naturalWidth: activeBitmapRef.current.width, naturalHeight: activeBitmapRef.current.height } : imageRef.current;
    if (!imageToMeasure) return;
    const geometry = overlayGeometry(imageToMeasure, rect.width, rect.height);
    if (!geometry) {
      setOverlayMessage("");
      return;
    }

    // The source <img> remains hidden so the canvas can carry the image and
    // its overlays as one surface. Draw it before any zones or detections.
    if (activeBitmapRef.current) {
      const bitmap = activeBitmapRef.current;
      context.drawImage(
        bitmap,
        geometry.offsetX,
        geometry.offsetY,
        bitmap.width * geometry.scale,
        bitmap.height * geometry.scale,
      );
    } else if (imageRef.current) {
      const image = imageRef.current;
      context.drawImage(
        image,
        geometry.offsetX,
        geometry.offsetY,
        image.naturalWidth * geometry.scale,
        image.naturalHeight * geometry.scale,
      );
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
        messages.push("Detection outlines are unavailable for this image.");
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

    const imageToMeasure = activeBitmapRef.current ? { naturalWidth: activeBitmapRef.current.width, naturalHeight: activeBitmapRef.current.height } : imageRef.current;
    if (!imageToMeasure) return null;
    const geometry = overlayGeometry(imageToMeasure, rect.width, rect.height);
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
  const connectionSignal = cameraConnectionSignal(camera, socketState, hasLivePreview);
  const riskSignal = cameraRiskSignal(summary.riskLevel);
  const latestSignal = recentActivity[0] ? activityStatus(recentActivity[0]) : null;
  const displayName = cameraOperatorName(camera);

  return (
    <div className="grid gap-4 xl:grid-cols-[220px_minmax(0,1fr)] xl:items-stretch 2xl:grid-cols-[250px_minmax(0,1fr)]">
      <aside className="order-3 overflow-hidden rounded-xl border border-white/10 bg-command-950/72 shadow-xl xl:order-1" aria-labelledby="live-signals-title">
        <div className="flex items-center justify-between gap-3 border-b border-white/10 px-4 py-3.5">
          <h2 id="live-signals-title" className="text-sm font-semibold text-white">Live Signals</h2>
          <ScanLine className="h-4 w-4 text-signal-cyan" aria-hidden />
        </div>
        <dl className="grid grid-cols-2 xl:block">
          <LiveSignalRow icon={Users} label="People" value={summary.people} tone="cyan" />
          <LiveSignalRow icon={Car} label="Vehicles" value={summary.vehicles} tone="cyan" />
          <LiveSignalRow icon={connectionSignal.tone === "offline" ? WifiOff : Video} label="Camera status" value={connectionSignal.label} tone={connectionSignal.tone} />
          <LiveSignalRow icon={riskSignal.tone === "danger" || riskSignal.tone === "attention" ? ShieldAlert : CheckCircle2} label="Current risk" value={riskSignal.label} tone={riskSignal.tone} />
          {latestSignal ? (
            <LiveSignalRow
              className="col-span-2"
              icon={Crosshair}
              label="Latest signal"
              value={latestSignal.summary}
              tone={latestSignal.tone === "high" ? "danger" : latestSignal.tone === "attention" ? "attention" : "cyan"}
              compact
            />
          ) : null}
        </dl>
      </aside>

      <section ref={panelRef} className="relative order-1 min-w-0 overflow-hidden rounded-xl border border-white/10 bg-black shadow-2xl xl:order-2 xl:h-[clamp(520px,68vh,720px)]" aria-labelledby="selected-camera-title">
        <div className="pointer-events-none absolute inset-x-0 top-0 z-30 flex items-start justify-between gap-3 bg-gradient-to-b from-black/90 via-black/55 to-transparent px-4 pb-12 pt-4 sm:px-5">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 id="selected-camera-title" className="truncate text-base font-semibold text-white sm:text-lg">{displayName}</h2>
              <span className={cn("rounded-md border px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.08em]", signalBadgeClass(connectionSignal.tone))}>{connectionSignal.label}</span>
              <span className={cn("rounded-md border px-2 py-1 text-[10px] font-semibold", signalBadgeClass(riskSignal.tone))}>{riskSignal.label}</span>
            </div>
            <p className="mt-1 text-xs text-slate-300">{connectionSignal.tone === "offline" ? "Monitoring unavailable" : "AI monitoring active"}</p>
          </div>

          <div className="pointer-events-auto flex shrink-0 items-start gap-2">
            <span className="hidden pt-2 text-xs text-slate-300 md:inline">{formatTime(camera.runtime.last_frame_time ?? undefined)}</span>
            <details className="group relative">
            <summary className="cursor-pointer list-none rounded-md border border-white/15 bg-black/45 px-2.5 py-2 text-xs font-medium text-slate-200 backdrop-blur-md transition hover:border-signal-cyan/45 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan">
              <span className="inline-flex items-center gap-1.5"><Info className="h-3.5 w-3.5" aria-hidden /><span className="hidden sm:inline">Details</span></span>
            </summary>
            <div className="absolute end-0 z-40 mt-2 w-72 rounded-lg border border-white/10 bg-command-950 p-3 text-xs shadow-2xl">
              <p className="font-semibold text-white">Camera diagnostics</p>
              <dl className="mt-3 grid gap-2 text-slate-300">
                <div className="flex justify-between gap-3"><dt>Source</dt><dd className="text-end text-white">{sourceLabel(camera.source_type)}</dd></div>
                <div className="flex justify-between gap-3"><dt>Resolution</dt><dd className="text-end text-white">{camera.runtime.width && camera.runtime.height ? `${camera.runtime.width} × ${camera.runtime.height}` : "Unavailable"}</dd></div>
                <div className="flex justify-between gap-3"><dt>Frame rate</dt><dd className="text-end text-white">{camera.runtime.fps == null ? "Unavailable" : `${camera.runtime.fps.toFixed(1)} FPS`}</dd></div>
                <div className="flex justify-between gap-3"><dt>Last frame</dt><dd className="text-end text-white">{formatTime(camera.runtime.last_frame_time ?? undefined)}</dd></div>
                <div className="flex justify-between gap-3"><dt>Pipeline</dt><dd className="text-end text-white">{camera.runtime.running ? "Running" : "Stopped"}</dd></div>
                <div className="flex justify-between gap-3"><dt>Camera reference</dt><dd className="max-w-36 break-all text-end text-white">{camera.camera_id}</dd></div>
              </dl>
              {camera.runtime.error_message ? <p className="mt-3 rounded border border-eose-300/25 bg-rose-400/[0.06] p-2 text-rose-100">Camera needs attention. Check the camera connection and setup.</p> : null}
            </div>
          </details>
          </div>
        </div>

        <div className="relative aspect-video min-h-[280px] bg-black sm:min-h-[380px] lg:min-h-[480px] xl:h-full xl:min-h-0 xl:aspect-auto">
          {previewSource ? (
            <>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                ref={imageRef}
                src={previewSource}
                alt={`${displayName} live preview`}
                className="hidden"
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
            <p className="absolute start-4 top-20 z-20 rounded-md border border-amber-300/25 bg-command-950/88 px-3 py-2 text-xs text-amber-100">
              {overlayMessage}
            </p>
          ) : null}

          {showZones ? (
            <div className="absolute inset-x-3 top-20 z-20 max-h-[calc(100%-7rem)] overflow-y-auto rounded-md border border-white/10 bg-command-950/94 p-3 text-xs shadow-xl backdrop-blur-xl sm:start-auto sm:end-4 sm:w-64">
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
                <div className="mt-3 max-h-28 space-y-1 overflow-y-auto pe-1">
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

        </div>

        <div className="relative z-30 border-t border-white/10 bg-command-950/96 p-2 backdrop-blur-xl lg:absolute lg:bottom-4 lg:start-1/2 lg:w-[min(calc(100%-2rem),760px)] lg:-translate-x-1/2 lg:rounded-xl lg:border">
          <div className="grid grid-cols-3 gap-1 sm:grid-cols-6">
            <ToggleButton pressed={showDetections} onClick={() => setShowDetections((value) => !value)} icon={Crosshair} label="Detections" ariaLabel="View detections" />
            <ToggleButton pressed={showZones} onClick={() => setShowZones((value) => !value)} icon={Map} label="Zones" />
            <ToggleButton pressed={showHeatmap} onClick={() => setShowHeatmap((value) => !value)} icon={Flame} label="Heatmap" />
            <ToolbarButton onClick={openSnapshot} icon={Download} label="Snapshot" />
            <ToolbarButton onClick={openFullscreen} icon={Expand} label="Fullscreen" />
            <button
              type="button"
              className={cn("inline-flex min-h-14 flex-col items-center justify-center gap-1 rounded-lg px-2 py-2 text-[11px] font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan disabled:opacity-45", camera.runtime.running ? "text-rose-300 hover:bg-rose-400/10" : "text-signal-cyan hover:bg-signal-cyan/10")}
              disabled={busy}
              onClick={toggleProcessing}
            >
              {camera.runtime.running ? <Square className="h-5 w-5" aria-hidden /> : <Play className="h-5 w-5" aria-hidden />}
              {camera.runtime.running ? "Stop" : "Start"}
            </button>
          </div>
        </div>
      </section>

      {cameraSwitcher ? <div className="order-2 min-w-0 xl:order-3 xl:col-start-2">{cameraSwitcher}</div> : null}

    </div>
  );
}

type LiveSignalTone = "cyan" | "live" | "attention" | "danger" | "offline";

function LiveSignalRow({
  icon: Icon,
  label,
  value,
  tone,
  compact = false,
  className
}: {
  icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  label: string;
  value: React.ReactNode;
  tone: LiveSignalTone;
  compact?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("flex min-h-[76px] items-center gap-3 border-t border-white/8 px-4 py-3 first:border-t-0 xl:min-h-[88px]", className)}>
      <span className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-full border bg-black/25", signalIconClass(tone))}>
        <Icon className="h-4 w-4" aria-hidden />
      </span>
      <div className="min-w-0">
        <dt className="text-xs text-slate-400">{label}</dt>
        <dd className={cn("mt-1 font-semibold", compact ? "line-clamp-2 text-xs leading-relaxed" : "truncate text-base", signalTextClass(tone))}>{value}</dd>
      </div>
    </div>
  );
}

function ToggleButton({
  pressed,
  onClick,
  icon: Icon,
  label,
  ariaLabel
}: {
  pressed: boolean;
  onClick: () => void;
  icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  label: string;
  ariaLabel?: string;
}) {
  return (
    <button
      type="button"
      className={cn(
        "inline-flex min-h-14 flex-col items-center justify-center gap-1 rounded-lg px-2 py-2 text-[11px] font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan",
        pressed ? "bg-signal-cyan/12 text-signal-cyan" : "text-slate-300 hover:bg-white/[0.07] hover:text-white"
      )}
      onClick={onClick}
      aria-pressed={pressed}
      aria-label={ariaLabel}
      title={label}
    >
      <Icon className="h-5 w-5" aria-hidden />
      <span>{label}</span>
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
      className="inline-flex min-h-14 flex-col items-center justify-center gap-1 rounded-lg px-2 py-2 text-[11px] font-medium text-slate-300 transition hover:bg-white/[0.07] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan"
      onClick={onClick}
      title={label}
    >
      <Icon className="h-5 w-5" aria-hidden />
      <span>{label}</span>
    </button>
  );
}

function signalIconClass(tone: LiveSignalTone) {
  if (tone === "live") return "border-emerald-300/30 text-emerald-300";
  if (tone === "attention") return "border-amber-300/35 text-amber-200";
  if (tone === "danger") return "border-eose-300/40 text-rose-300";
  if (tone === "offline") return "border-slate-400/25 text-slate-400";
  return "border-signal-cyan/30 text-signal-cyan";
}

function signalTextClass(tone: LiveSignalTone) {
  if (tone === "live") return "text-emerald-300";
  if (tone === "attention") return "text-amber-200";
  if (tone === "danger") return "text-rose-300";
  if (tone === "offline") return "text-slate-300";
  return "text-signal-cyan";
}

function signalBadgeClass(tone: LiveSignalTone) {
  if (tone === "live") return "border-emerald-300/35 bg-emerald-400/10 text-emerald-200";
  if (tone === "attention") return "border-amber-300/35 bg-amber-300/10 text-amber-100";
  if (tone === "danger") return "border-eose-300/40 bg-rose-400/12 text-rose-200";
  if (tone === "offline") return "border-slate-300/25 bg-slate-300/8 text-slate-300";
  return "border-signal-cyan/35 bg-signal-cyan/10 text-signal-cyan";
}

function observedAtMilliseconds(detection: Track) {
  const rawValue = detection.last_seen;
  if (!rawValue) return undefined;
  const normalized = /(?:Z|[+-]\d\d:\d\d)$/.test(rawValue) ? rawValue : `${rawValue}Z`;
  const parsed = Date.parse(normalized);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function filterCurrentDetections(detections: Track[], now = Date.now(), maxAgeMs = 5_000) {
  const freshDetections = detections.filter((detection) => {
    const observedAt = observedAtMilliseconds(detection);
    return observedAt === undefined || now - observedAt <= maxAgeMs;
  });
  const latestFrame = Math.max(...freshDetections.map((detection) => detection.frame_number ?? detection.frame_id ?? 0), 0);
  const currentFrame = latestFrame
    ? freshDetections.filter((detection) => (detection.frame_number ?? detection.frame_id ?? latestFrame) === latestFrame)
    : freshDetections;
  const uniqueTracks = new globalThis.Map<string, Track>();

  currentFrame.forEach((detection, index) => {
    const bbox = Array.isArray(detection.bbox) ? detection.bbox.join(",") : "no-bbox";
    const identity = detection.track_id
      ? `track:${detection.track_id}`
      : `detection:${className(detection)}:${bbox}:${index}`;
    uniqueTracks.set(identity, detection);
  });

  return Array.from(uniqueTracks.values()).slice(0, 80);
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

function cameraConnectionSignal(camera: Camera, socketState: SocketState, hasLivePreview: boolean): { label: string; tone: LiveSignalTone } {
  if (["offline", "error", "stopped"].includes(camera.runtime.status)) return { label: "Offline", tone: "offline" };
  if (camera.runtime.status === "reconnecting" || socketState === "reconnecting") return { label: "Reconnecting", tone: "attention" };
  if (hasLivePreview || (camera.runtime.status === "online" && camera.runtime.running)) return { label: "Online", tone: "live" };
  if (!camera.runtime.running) return { label: "Stopped", tone: "offline" };
  return { label: "Connecting", tone: "attention" };
}

function cameraRiskSignal(riskLevel?: RiskLevel): { label: string; tone: LiveSignalTone } {
  if (riskLevel === "CRITICAL" || riskLevel === "HIGH") return { label: "High risk", tone: "danger" };
  if (riskLevel === "MEDIUM" || riskLevel === "CANDIDATE_MEDIUM") return { label: "Needs attention", tone: "attention" };
  if (riskLevel === "LOW") return { label: "Low risk", tone: "live" };
  return { label: "Clear", tone: "cyan" };
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

function overlayGeometry(image: { naturalWidth: number; naturalHeight: number }, renderedWidth: number, renderedHeight: number): OverlayGeometry | null {
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
  context.lineWidth = Math.max(2, style.lineWidth * 1.5);
  context.strokeStyle = style.stroke;

  // Draw tactical corner brackets instead of full box
  const cornerLength = Math.min(width * 0.2, height * 0.2, 20);
  context.beginPath();
  // Top-left
  context.moveTo(left, top + cornerLength);
  context.lineTo(left, top);
  context.lineTo(left + cornerLength, top);
  // Top-right
  context.moveTo(right - cornerLength, top);
  context.lineTo(right, top);
  context.lineTo(right, top + cornerLength);
  // Bottom-right
  context.moveTo(right, bottom - cornerLength);
  context.lineTo(right, bottom);
  context.lineTo(right - cornerLength, bottom);
  // Bottom-left
  context.moveTo(left + cornerLength, bottom);
  context.lineTo(left, bottom);
  context.lineTo(left, bottom - cornerLength);

  context.stroke();

  // Pulse effect for high risk
  if (style.stroke === "#f0abfc" || style.stroke === "#f59e0b") {
     const pulse = (Date.now() % 2000) / 2000;
     context.globalAlpha = (1 - pulse) * 0.5;
     context.lineWidth = context.lineWidth * (1 + pulse * 2);
     context.stroke();
  }
  context.globalAlpha = 1.0;


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

/** Keep the latest camera signal concise while retaining high-priority evidence. */
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

export const cameraCommandCenterInternals = { buildRecentActivity, filterCurrentDetections };
