"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2, MonitorX, Radio } from "lucide-react";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { CameraStatusBadge } from "@/components/cameras/camera-status-badge";
import { resolveCameraWebSocketUrl } from "@/lib/config";
import { cameraWebSocketMessageSchema } from "@/lib/schemas";
import type { Camera } from "@/types";

type SocketState = "idle" | "connecting" | "connected" | "reconnecting" | "error" | "unavailable";

export function CameraPreview({ camera }: { camera?: Camera }) {
  const [socketState, setSocketState] = useState<SocketState>("idle");
  const [frame, setFrame] = useState<string>("");
  const [message, setMessage] = useState<string>("");
  const closedRef = useRef(false);
  const retryRef = useRef(0);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    setFrame("");
    setMessage("");
    if (!camera) {
      setSocketState("idle");
      return undefined;
    }

    const url = resolveCameraWebSocketUrl(camera.camera_id, "frames");
    if (!url) {
      setSocketState("unavailable");
      setMessage("live stream endpoint unavailable");
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
        setMessage("live stream endpoint unavailable");
        return;
      }

      socket.onopen = () => {
        retryRef.current = 0;
        setSocketState("connected");
      };

      socket.onmessage = (event) => {
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

        if (parsed.data.message) {
          setMessage(parsed.data.message);
        } else if (parsed.data.error_message) {
          setMessage(parsed.data.error_message);
        }
      };

      socket.onerror = () => {
        setSocketState("unavailable");
        setMessage("live stream endpoint unavailable");
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

  return (
    <Card className="overflow-hidden p-0">
      <CardHeader className="p-5 pb-3">
        <div>
          <CardTitle>Live Preview</CardTitle>
          <CardDescription>{camera ? camera.camera_id : "Select a registered camera"}</CardDescription>
        </div>
        {camera ? <CameraStatusBadge status={camera.runtime.status} /> : null}
      </CardHeader>

      <div className="relative aspect-video min-h-72 border-t border-white/10 bg-black">
        {frame ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={frame} alt={`${camera?.camera_id} camera frame`} className="h-full w-full object-contain" />
        ) : (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-center text-slate-400">
            {socketState === "connecting" || socketState === "reconnecting" ? (
              <Loader2 className="h-6 w-6 animate-spin text-signal-cyan" aria-hidden />
            ) : socketState === "connected" ? (
              <Radio className="h-6 w-6 text-signal-cyan" aria-hidden />
            ) : (
              <MonitorX className="h-6 w-6 text-slate-500" aria-hidden />
            )}
            <div>
              <p className="text-sm font-medium text-slate-200">
                {camera ? message || "Waiting for a real frame from the backend." : "No camera selected"}
              </p>
              {camera ? <p className="mt-1 text-xs uppercase tracking-[0.16em] text-slate-500">{socketState}</p> : null}
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}
