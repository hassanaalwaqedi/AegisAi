"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Aperture,
  Boxes,
  Car,
  Crosshair,
  Download,
  Expand,
  Flame,
  Focus,
  Gauge,
  Map,
  Play,
  Radio,
  ScanLine,
  ShieldAlert,
  Square,
  Users,
  Video
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CameraStatusBadge } from "@/components/cameras/camera-status-badge";
import { EmptyState, ErrorState, LoadingState } from "@/components/layout/states";
import { RiskBadge } from "@/components/dashboard/risk-badge";
import { appConfig, resolveCameraWebSocketUrl } from "@/lib/config";
import { cameraWebSocketMessageSchema } from "@/lib/schemas";
import { formatDecimal, formatPercent } from "@/lib/data-format";
import { cn, formatTime } from "@/lib/utils";
import {
  useCameraDetectionsQuery,
  useCameraEventsQuery,
  useStartCameraMutation,
  useStopCameraMutation
} from "@/hooks/use-aegis-api";
import type { Camera, RiskEvent, RiskLevel, Track } from "@/types";

type SocketState = "idle" | "connecting" | "connected" | "reconnecting" | "error" | "unavailable";

type OverlayGeometry = {
  offsetX: number;
  offsetY: number;
  scale: number;
  sourceWidth: number;
  sourceHeight: number;
};

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
  const closedRef = useRef(false);
  const retryRef = useRef(0);
  const timerRef = useRef<number | null>(null);
  const [frame, setFrame] = useState("");
  const [socketState, setSocketState] = useState<SocketState>("idle");
  const [message, setMessage] = useState("");
  const [overlayMessage, setOverlayMessage] = useState("");
  const [showDetections, setShowDetections] = useState(true);
  const [showTracking, setShowTracking] = useState(true);
  const [showZones, setShowZones] = useState(false);
  const [showHeatmap, setShowHeatmap] = useState(false);

  const detectionsQuery = useCameraDetectionsQuery(camera?.camera_id);
  const eventsQuery = useCameraEventsQuery(camera?.camera_id);
  const startCamera = useStartCameraMutation();
  const stopCamera = useStopCameraMutation();

  const detections = useMemo(() => filterCurrentDetections(detectionsQuery.data?.detections ?? []), [detectionsQuery.data?.detections]);
  const events = eventsQuery.data?.events ?? [];
  const summary = useMemo(() => buildSummary(detections, events), [detections, events]);

  useEffect(() => {
    setFrame("");
    setMessage("");
    setOverlayMessage("");
    if (!camera) {
      setSocketState("idle");
      return undefined;
    }

    const url = resolveCameraWebSocketUrl(camera.camera_id, "frames");
    if (!url) {
      setSocketState("unavailable");
      setMessage("Live stream endpoint unavailable.");
      return undefined;
    }

    let socket: WebSocket | undefined;
    closedRef.current = false;
    retryRef.current = 0;

    function connect() {
      if (closedRef.current) return;
      setSocketState(retryRef.current > 0 ? "reconnecting" : "connecting");

      try {
        socket = new WebSocket(url);
      } catch {
        setSocketState("unavailable");
        setMessage("Live stream endpoint unavailable.");
        return;
      }

      socket.onopen = () => {
        retryRef.current = 0;
        setSocketState("connected");
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
        setSocketState("unavailable");
        setMessage("Live stream endpoint unavailable.");
      };

      socket.onclose = () => {
        if (closedRef.current) return;
        setSocketState("reconnecting");
        retryRef.current += 1;
        timerRef.current = window.setTimeout(connect, Math.min(15000, 1000 * 2 ** retryRef.current));
      };
    }

    connect();

    return () => {
      closedRef.current = true;
      if (timerRef.current) window.clearTimeout(timerRef.current);
      socket?.close();
    };
  }, [camera]);

  useEffect(() => {
    drawOverlay();
    const image = imageRef.current;
    if (!image) return undefined;
    const observer = new ResizeObserver(() => drawOverlay());
    observer.observe(image);
    return () => observer.disconnect();
  }, [detections, frame, showDetections, showTracking]);

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

    if (!showDetections || !frame || detections.length === 0) {
      setOverlayMessage("");
      return;
    }

    const geometry = overlayGeometry(image, rect.width, rect.height);
    if (!geometry) {
      setOverlayMessage("");
      return;
    }

    const drawable = detections.filter((detection) => Array.isArray(detection.bbox));
    if (detections.length > 0 && drawable.length === 0) {
      setOverlayMessage("Detection boxes unavailable: backend did not return bbox.");
      return;
    }

    setOverlayMessage("");
    for (const detection of drawable) {
      drawDetection(context, detection, geometry, showTracking);
    }
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

  if (!camera) {
    return (
      <div className="glass-panel flex min-h-[560px] items-center justify-center rounded-lg p-6">
        <EmptyState title="Select a camera" description="Choose a registered source to open the live command view." />
      </div>
    );
  }

  const resolution = camera.runtime.width && camera.runtime.height ? `${camera.runtime.width}x${camera.runtime.height}` : "No frame";
  const currentRisk = summary.riskLevel ?? "LOW";
  const busy = startCamera.isPending || stopCamera.isPending;

  return (
    <div className="grid min-h-[720px] gap-4 xl:grid-cols-[260px_minmax(0,1fr)_330px]">
      <aside className="glass-panel rounded-lg p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-[0.14em] text-slate-500">Live Summary</p>
            <h2 className="mt-1 text-lg font-semibold text-white">Detection Load</h2>
          </div>
          <ScanLine className="h-5 w-5 text-signal-cyan" aria-hidden />
        </div>

        <div className="mt-5 grid gap-3">
          <SummaryMetric icon={Users} label="People" value={summary.people} />
          <SummaryMetric icon={Car} label="Vehicles" value={summary.vehicles} />
          <SummaryMetric icon={ShieldAlert} label="Weapons" value={summary.weapons} tone={summary.weapons > 0 ? "warning" : "normal"} />
          <SummaryMetric icon={Boxes} label="Active tracks" value={summary.activeTracks} />
          <SummaryMetric icon={Radio} label="Events" value={summary.events} tone={summary.events > 0 ? "warning" : "normal"} />
        </div>

        <div className="mt-5 rounded-md border border-white/10 bg-black/20 p-3">
          <p className="text-xs uppercase tracking-[0.14em] text-slate-500">Current risk</p>
          <div className="mt-2 flex items-center justify-between gap-3">
            <RiskBadge level={currentRisk} />
            <span className="text-sm text-slate-400">{formatDecimal(summary.riskScore, 2, "0.00")}</span>
          </div>
        </div>

        <div className="mt-5 rounded-md border border-white/10 bg-black/20 p-3">
          <p className="text-xs uppercase tracking-[0.14em] text-slate-500">Selected camera</p>
          <p className="mt-2 break-words text-sm font-medium text-white">{camera.name || camera.camera_id}</p>
          <p className="mt-1 break-words text-xs text-slate-500">{camera.camera_id}</p>
        </div>
      </aside>

      <section ref={panelRef} className="glass-panel min-w-0 overflow-hidden rounded-lg">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-4 py-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="truncate text-lg font-semibold text-white">{camera.name || camera.camera_id}</h2>
              <CameraStatusBadge status={camera.runtime.status} />
              <Badge variant={socketState === "connected" ? "success" : "outline"}>{socketState}</Badge>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-400">
              <span>{sourceLabel(camera.source_type)}</span>
              <span>{resolution}</span>
              <span>{formatDecimal(camera.runtime.fps, 1, "0.0")} FPS</span>
              <span>{camera.runtime.running ? "Processing active" : "Processing stopped"}</span>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <RiskBadge level={currentRisk} />
            <Badge variant="outline">Backend {camera.runtime.status}</Badge>
          </div>
        </div>

        <div className="relative aspect-video min-h-[420px] bg-black">
          {frame ? (
            <>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                ref={imageRef}
                src={frame}
                alt={`${camera.camera_id} live frame`}
                className="h-full w-full object-contain"
                onLoad={drawOverlay}
              />
              <canvas ref={canvasRef} className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden />
            </>
          ) : (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-center text-slate-400">
              <Video className="h-9 w-9 text-slate-600" aria-hidden />
              <div>
                <p className="text-sm font-medium text-slate-200">{message || previewMessage(camera)}</p>
                <p className="mt-1 text-xs uppercase tracking-[0.16em] text-slate-500">{socketState}</p>
              </div>
            </div>
          )}

          {overlayMessage ? (
            <p className="absolute left-4 top-4 rounded-md border border-amber-300/25 bg-command-950/88 px-3 py-2 text-xs text-amber-100">
              {overlayMessage}
            </p>
          ) : null}

          {showZones || showHeatmap ? (
            <div className="absolute right-4 top-4 max-w-xs space-y-2">
              {showZones ? (
                <p className="rounded-md border border-amber-300/25 bg-command-950/88 px-3 py-2 text-xs text-amber-100">
                  Zone overlay unavailable: backend did not return zones.
                </p>
              ) : null}
              {showHeatmap ? (
                <p className="rounded-md border border-amber-300/25 bg-command-950/88 px-3 py-2 text-xs text-amber-100">
                  Heatmap unavailable: backend did not return heatmap data.
                </p>
              ) : null}
            </div>
          ) : null}

          <div className="absolute inset-x-4 bottom-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-white/10 bg-command-950/82 p-2 backdrop-blur-xl">
            <div className="flex flex-wrap gap-2">
              <ToggleButton pressed={showDetections} onClick={() => setShowDetections((value) => !value)} icon={Crosshair} label="Detections" />
              <ToggleButton pressed={showTracking} onClick={() => setShowTracking((value) => !value)} icon={Focus} label="Tracking" />
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

      <aside className="glass-panel min-w-0 rounded-lg p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-[0.14em] text-slate-500">Evidence</p>
            <h2 className="mt-1 text-lg font-semibold text-white">Recent Events</h2>
          </div>
          <Aperture className="h-5 w-5 text-signal-cyan" aria-hidden />
        </div>

        <div className="mt-4">
          {eventsQuery.isLoading ? <LoadingState label="Loading events" /> : null}
          {eventsQuery.isError ? <ErrorState error={eventsQuery.error} title="Camera events unavailable" /> : null}
          {!eventsQuery.isLoading && !eventsQuery.isError && events.length === 0 ? (
            <EmptyState title="No risk events detected yet." description="Only backend-generated events will appear here." />
          ) : null}
          <div className="space-y-3">
            {events.slice().reverse().slice(0, 8).map((event, index) => (
              <EventEvidenceCard key={eventKey(event, index)} event={event} />
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

function EventEvidenceCard({ event }: { event: RiskEvent }) {
  const level = event.risk_level ?? event.severity ?? event.level;
  const objectClass = event.object_class ?? event.object_type ?? event.class_name ?? "Not returned";
  const confidence = formatPercent(event.confidence);
  const title = event.explanation ?? event.description ?? event.reason ?? "Backend risk event";

  return (
    <article className="rounded-md border border-white/10 bg-black/20 p-3">
      <div className="flex items-start justify-between gap-2">
        <Badge variant={severityVariant(level)}>{String(level ?? "event")}</Badge>
        <span className="text-xs text-slate-500">{formatTime(String(event.timestamp ?? ""))}</span>
      </div>
      <p className="mt-2 text-sm font-medium text-white">{title}</p>
      <div className="mt-3 grid gap-1 text-xs text-slate-400">
        <span>Object: {objectClass}</span>
        <span>Confidence: {confidence}</span>
        <span>Verification: {event.verification_status ?? "Not returned"}</span>
        <span>Model: {event.model_source?.length ? event.model_source.join(", ") : "Not returned"}</span>
        <span>Reasons: {event.reason_codes?.length ? event.reason_codes.join(", ") : "Not returned"}</span>
      </div>
    </article>
  );
}

function filterCurrentDetections(detections: Track[]) {
  const latestFrame = Math.max(...detections.map((detection) => detection.frame_number ?? detection.frame_id ?? 0), 0);
  if (!latestFrame) return detections.slice(0, 60);
  return detections.filter((detection) => (detection.frame_number ?? detection.frame_id ?? latestFrame) >= latestFrame - 1).slice(0, 80);
}

function buildSummary(detections: Track[], events: RiskEvent[]) {
  const people = detections.filter((detection) => detection.is_person || className(detection) === "person").length;
  const vehicles = detections.filter((detection) => vehicleClasses.has(className(detection))).length;
  const weapons = detections.filter((detection) => detection.is_weapon || weaponClasses.has(className(detection))).length;
  const activeTracks = new Set(detections.map((detection) => String(detection.track_id))).size;
  const riskLevel = detections.reduce<RiskLevel | undefined>((current, detection) => {
    if (!detection.risk_level) return current;
    if (!current) return detection.risk_level;
    return riskOrder[detection.risk_level] > riskOrder[current] ? detection.risk_level : current;
  }, undefined);
  const riskScore = detections.reduce((max, detection) => Math.max(max, detection.risk_score ?? 0), 0);
  return {
    people,
    vehicles,
    weapons,
    activeTracks,
    events: events.length,
    riskLevel,
    riskScore
  };
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

function drawDetection(context: CanvasRenderingContext2D, detection: Track, geometry: OverlayGeometry, showTracking: boolean) {
  if (!detection.bbox) return;
  const [x1, y1, x2, y2] = detection.bbox;
  const left = geometry.offsetX + clamp(x1, 0, geometry.sourceWidth) * geometry.scale;
  const top = geometry.offsetY + clamp(y1, 0, geometry.sourceHeight) * geometry.scale;
  const right = geometry.offsetX + clamp(x2, 0, geometry.sourceWidth) * geometry.scale;
  const bottom = geometry.offsetY + clamp(y2, 0, geometry.sourceHeight) * geometry.scale;
  const width = Math.max(1, right - left);
  const height = Math.max(1, bottom - top);
  const style = overlayStyle(detection);
  const label = `${className(detection)} ${formatPercent(detection.confidence, "n/a")}`;

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
  const labelY = top > labelHeight + 6 ? top - labelHeight - 5 : top + 5;
  context.fillStyle = style.labelBackground;
  roundedRect(context, left, labelY, labelWidth, labelHeight, 6);
  context.fill();
  context.fillStyle = style.labelText;
  context.fillText(label, left + 8, labelY + 16);

  if (showTracking) {
    context.fillStyle = style.stroke;
    context.font = "11px Inter, system-ui, sans-serif";
    context.fillText(String(detection.track_id), left + 2, Math.min(top + height + 14, geometry.offsetY + geometry.sourceHeight * geometry.scale - 4));
  }
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

function severityVariant(level?: string) {
  const normalized = level?.toUpperCase();
  if (normalized === "CRITICAL") return "critical";
  if (normalized === "HIGH") return "danger";
  if (normalized === "MEDIUM" || normalized === "CANDIDATE_MEDIUM") return "warning";
  if (normalized === "LOW") return "success";
  return "outline";
}

function sourceLabel(source: Camera["source_type"]) {
  const labels: Record<Camera["source_type"], string> = {
    LOCAL_DEVICE: "Local device",
    RTSP_STREAM: "RTSP stream",
    HTTP_STREAM: "HTTP/YouTube stream",
    BROWSER_WEBCAM: "Browser webcam",
    UPLOADED_VIDEO: "Uploaded video"
  };
  return labels[source];
}

function previewMessage(camera: Camera) {
  if (camera.source_type === "HTTP_STREAM" && !camera.runtime.running) return "Start processing to preview this external stream.";
  if (camera.source_type === "HTTP_STREAM" && camera.runtime.error_message) return camera.runtime.error_message;
  if (camera.source_type === "HTTP_STREAM") return "Waiting for backend frame extraction from this source.";
  if (camera.source_type === "BROWSER_WEBCAM") return "Start browser capture below to send frames to the backend.";
  return "Waiting for a real frame from the backend.";
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}
