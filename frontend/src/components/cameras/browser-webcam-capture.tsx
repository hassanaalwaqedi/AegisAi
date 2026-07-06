"use client";

import { useEffect, useRef, useState } from "react";
import { Camera as CameraIcon, Loader2, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getErrorMessage } from "@/lib/errors";
import { useBrowserFrameMutation } from "@/hooks/use-aegis-api";
import type { Camera, Track } from "@/types";

export function BrowserWebcamCapture({ camera }: { camera?: Camera }) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const overlayCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const processingRef = useRef(false);
  const [capturing, setCapturing] = useState(false);
  const [permissionError, setPermissionError] = useState("");
  const [overlayMessage, setOverlayMessage] = useState("");
  const browserFrame = useBrowserFrameMutation();

  useEffect(() => {
    return () => stop();
  }, []);

  async function start() {
    if (!camera) return;
    setPermissionError("");

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: 1280 },
          height: { ideal: 720 }
        },
        audio: false
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setCapturing(true);
    } catch (error) {
      setPermissionError(error instanceof Error ? error.message : "Browser camera permission was denied.");
    }
  }

  function stop() {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    setCapturing(false);
  }

  useEffect(() => {
    if (!capturing || !camera) return undefined;

    const timer = window.setInterval(() => {
      const video = videoRef.current;
      const canvas = canvasRef.current;
      if (!video || !canvas || video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA || processingRef.current) return;

      const width = video.videoWidth;
      const height = video.videoHeight;
      if (!width || !height) return;

      canvas.width = width;
      canvas.height = height;
      const context = canvas.getContext("2d");
      if (!context) return;

      context.drawImage(video, 0, 0, width, height);
      const frame = canvas.toDataURL("image/jpeg", 0.82);
      processingRef.current = true;
      browserFrame.mutate(
        { cameraId: camera.camera_id, frame },
        {
          onSettled: () => {
            processingRef.current = false;
          }
        }
      );
    }, 900);

    return () => window.clearInterval(timer);
  }, [browserFrame, camera, capturing]);

  useEffect(() => {
    drawOverlay();

    const video = videoRef.current;
    if (!video) return undefined;

    const observer = new ResizeObserver(() => drawOverlay());
    observer.observe(video);
    return () => observer.disconnect();
  }, [browserFrame.data?.detections, capturing]);

  function drawOverlay() {
    const video = videoRef.current;
    const canvas = overlayCanvasRef.current;
    const detections = browserFrame.data?.detections ?? [];
    if (!video || !canvas) return;

    const rect = video.getBoundingClientRect();
    const pixelRatio = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.round(rect.width * pixelRatio));
    canvas.height = Math.max(1, Math.round(rect.height * pixelRatio));
    canvas.style.width = `${rect.width}px`;
    canvas.style.height = `${rect.height}px`;

    const context = canvas.getContext("2d");
    if (!context) return;
    context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
    context.clearRect(0, 0, rect.width, rect.height);

    if (!capturing || detections.length === 0) {
      setOverlayMessage("");
      return;
    }

    const drawable = overlayGeometry(video, rect.width, rect.height);
    if (!drawable) {
      setOverlayMessage("");
      return;
    }

    const drawableDetections = detections.filter((detection) => Array.isArray(detection.bbox));
    if (detections.length > 0 && drawableDetections.length === 0) {
      setOverlayMessage("Backend does not return bbox for overlay yet.");
      return;
    }
    setOverlayMessage("");

    for (const detection of drawableDetections) {
      drawDetection(context, detection, drawable);
    }
  }

  if (!camera || camera.source_type !== "BROWSER_WEBCAM") {
    return null;
  }

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Browser Webcam Ingestion</CardTitle>
          <CardDescription>Frames are sent to `/camera/browser-frame` for the backend detection pipeline.</CardDescription>
        </div>
      </CardHeader>

      <div className="grid gap-4 lg:grid-cols-[1fr_220px]">
        <div className="relative overflow-hidden rounded-lg border border-white/10 bg-black">
          <video ref={videoRef} className="aspect-video h-full w-full object-contain" muted playsInline />
          <canvas ref={overlayCanvasRef} className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden />
          <canvas ref={canvasRef} className="hidden" />
          {overlayMessage ? (
            <p className="absolute bottom-3 left-3 right-3 rounded-md border border-amber-300/25 bg-command-950/85 p-2 text-xs text-amber-100">
              {overlayMessage}
            </p>
          ) : null}
        </div>

        <div className="space-y-3">
          <Button type="button" onClick={capturing ? stop : start} className="w-full" variant={capturing ? "secondary" : "primary"}>
            {capturing ? <Square className="h-4 w-4" aria-hidden /> : <CameraIcon className="h-4 w-4" aria-hidden />}
            {capturing ? "Stop capture" : "Start capture"}
          </Button>

          <div className="rounded-md border border-white/10 bg-white/[0.035] p-3 text-sm text-slate-300">
            <p>Backend frames sent: {camera.runtime.frames_received ?? 0}</p>
            <p className="mt-1">Last detection count: {browserFrame.data?.detections.length ?? 0}</p>
            {browserFrame.isPending ? (
              <p className="mt-2 inline-flex items-center gap-2 text-signal-cyan">
                <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
                Processing frame
              </p>
            ) : null}
          </div>
        </div>
      </div>

      {permissionError ? <p className="mt-4 rounded-md border border-rose-400/25 bg-rose-500/[0.08] p-3 text-sm text-rose-100">{permissionError}</p> : null}
      {browserFrame.error ? <p className="mt-4 rounded-md border border-rose-400/25 bg-rose-500/[0.08] p-3 text-sm text-rose-100">{getErrorMessage(browserFrame.error)}</p> : null}
    </Card>
  );
}

type OverlayGeometry = {
  offsetX: number;
  offsetY: number;
  scale: number;
  sourceWidth: number;
  sourceHeight: number;
};

function overlayGeometry(video: HTMLVideoElement, renderedWidth: number, renderedHeight: number): OverlayGeometry | null {
  const sourceWidth = video.videoWidth;
  const sourceHeight = video.videoHeight;
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

function drawDetection(context: CanvasRenderingContext2D, detection: Track, geometry: OverlayGeometry) {
  if (!detection.bbox) return;
  const [x1, y1, x2, y2] = detection.bbox;
  const left = geometry.offsetX + clamp(x1, 0, geometry.sourceWidth) * geometry.scale;
  const top = geometry.offsetY + clamp(y1, 0, geometry.sourceHeight) * geometry.scale;
  const right = geometry.offsetX + clamp(x2, 0, geometry.sourceWidth) * geometry.scale;
  const bottom = geometry.offsetY + clamp(y2, 0, geometry.sourceHeight) * geometry.scale;
  const width = Math.max(1, right - left);
  const height = Math.max(1, bottom - top);
  const style = overlayStyle(detection);
  const className = String(detection.class_name ?? "unknown").toLowerCase();
  const confidence = typeof detection.confidence === "number" ? detection.confidence.toFixed(2) : "n/a";
  const label = `${className} ${confidence}`;

  context.save();
  context.lineWidth = style.lineWidth;
  context.strokeStyle = style.stroke;
  context.fillStyle = style.fill;
  context.strokeRect(left, top, width, height);
  context.fillRect(left, top, width, height);

  context.font = "12px sans-serif";
  const labelWidth = context.measureText(label).width + 12;
  const labelHeight = 22;
  const labelY = Math.max(0, top - labelHeight);
  context.fillStyle = style.labelBackground;
  context.fillRect(left, labelY, Math.min(labelWidth, geometry.sourceWidth * geometry.scale), labelHeight);
  context.fillStyle = style.labelText;
  context.fillText(label, left + 6, labelY + 15);
  context.restore();
}

function overlayStyle(detection: Track) {
  const className = String(detection.class_name ?? "").toLowerCase();
  const isWeapon = detection.is_weapon || className === "knife" || className === "pistol";
  const isCritical = isWeapon && detection.risk_level === "CRITICAL" && detection.verification_status === "confirmed";
  if (isCritical) {
    return {
      stroke: "#f0abfc",
      fill: "rgba(217, 70, 239, 0.12)",
      labelBackground: "rgba(112, 26, 117, 0.92)",
      labelText: "#fff7ff",
      lineWidth: 3
    };
  }
  if (isWeapon) {
    return {
      stroke: "#f59e0b",
      fill: "rgba(245, 158, 11, 0.12)",
      labelBackground: "rgba(120, 53, 15, 0.92)",
      labelText: "#fffbeb",
      lineWidth: 3
    };
  }
  return {
    stroke: "#22d3ee",
    fill: "rgba(34, 211, 238, 0.08)",
    labelBackground: "rgba(8, 47, 73, 0.9)",
    labelText: "#ecfeff",
    lineWidth: 2
  };
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}
