"use client";

import { useEffect, useState } from "react";
import { Camera } from "lucide-react";
import { appConfig } from "@/lib/config";

// Focus Mode receives a 15 FPS WebSocket stream. Grid thumbnails are context,
// so refresh them less often and leave bandwidth/CPU to the selected camera.
const THUMBNAIL_PREVIEW_INTERVAL_MS = 2_000;

// Fetch serially so slow sources never accumulate requests or cancel every frame.
export function CameraProjection({ cameraId, label }: { cameraId: string; label: string }) {
  const [frame, setFrame] = useState<string | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    let previousUrl: string | null = null;
    const refresh = async () => {
      try {
        const response = await fetch(`${appConfig.apiUrl}/cameras/${encodeURIComponent(cameraId)}/snapshot`, { signal: controller.signal, cache: "no-store" });
        if (!response.ok) throw new Error("Frame unavailable");
        const blob = await response.blob();
        if (controller.signal.aborted) return;
        const url = URL.createObjectURL(blob);
        if (previousUrl) URL.revokeObjectURL(previousUrl);
        previousUrl = url;
        setFrame(url);
        setUnavailable(false);
      } catch {
        if (!controller.signal.aborted) setUnavailable(true);
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(refresh, THUMBNAIL_PREVIEW_INTERVAL_MS);
      }
    };
    void refresh();
    return () => { controller.abort(); clearTimeout(timer); if (previousUrl) URL.revokeObjectURL(previousUrl); };
  }, [cameraId]);
  return <div className="operator-camera-media">
    {/* eslint-disable-next-line @next/next/no-img-element -- authenticated frame blobs cannot use the public optimizer. */}
    {frame ? <img src={frame} alt={label} /> : <Camera aria-hidden />}
    <span role="status">{unavailable ? "Current frame unavailable" : frame ? "Latest frame · refreshing" : "Waiting for a frame"}</span>
  </div>;
}
