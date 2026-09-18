"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2, MonitorX, Radio } from "lucide-react";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { CameraStatusBadge } from "@/components/cameras/camera-status-badge";
import { createAuthenticatedWebSocket, resolveCameraWebSocketUrl } from "@/lib/config";
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
    const resetTimer = window.setTimeout(() => {
      setFrame("");
      setMessage("");
    }, 0);
    if (!camera) {
      const idleTimer = window.setTimeout(() => setSocketState("idle"), 0);
      return () => {
        window.clearTimeout(resetTimer);
        window.clearTimeout(idleTimer);
      };
    }

    const url = resolveCameraWebSocketUrl(camera.camera_id, "frames");
    if (!url) {
      const unavailableTimer = window.setTimeout(() => {
        setSocketState("unavailable");
        setMessage("Live stream is temporarily unavailable.");
      }, 0);
      return () => {
        window.clearTimeout(resetTimer);
        window.clearTimeout(unavailableTimer);
      };
    }

    let socket: WebSocket | undefined;
    closedRef.current = false;
    retryRef.current = 0;

    async function connect() {
      if (closedRef.current) return;
      setSocketState(retryRef.current > 0 ? "reconnecting" : "connecting");

      try {
        socket = await createAuthenticatedWebSocket(url);
        if (closedRef.current) {
          socket.close();
          return;
        }
      } catch {
        setSocketState("unavailable");
        setMessage("Live stream is temporarily unavailable.");
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
          setMessage("A live image update could not be read.");
          return;
        }

        if (parsed.data.type === "frame" && parsed.data.frame) {
          setFrame(parsed.data.frame);
          setMessage("");
          return;
        }

        if (parsed.data.message || parsed.data.error_message) setMessage("Live stream needs attention.");
      };

      socket.onerror = () => {
        setSocketState("unavailable");
        setMessage("Live stream is temporarily unavailable.");
      };

      socket.onclose = () => {
        if (closedRef.current) return;
        setSocketState("reconnecting");
        retryRef.current += 1;
        timerRef.current = window.setTimeout(() => void connect(), Math.min(15000, 1000 * 2 ** retryRef.current));
      };
    }

    void connect();

    return () => {
      closedRef.current = true;
      window.clearTimeout(resetTimer);
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
                {camera ? message || "Waiting for a live image." : "No camera selected"}
              </p>
              {camera ? <p className="mt-1 text-xs uppercase tracking-[0.16em] text-slate-500">{streamStateLabel(socketState)}</p> : null}
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}

function streamStateLabel(state: SocketState) {
  if (state === "connected") return "Live";
  if (state === "connecting" || state === "reconnecting") return "Connecting";
  if (state === "unavailable" || state === "error") return "Unavailable";
  return "Waiting";
}
