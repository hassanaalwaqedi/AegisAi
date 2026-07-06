"use client";

import { FormEvent, useMemo, useState } from "react";
import { CheckCircle2, Loader2, Plus, TestTube2, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { getErrorMessage } from "@/lib/errors";
import {
  useCameraConnectionTestMutation,
  useCreateCameraMutation,
  useProcessVideoMutation,
  useUploadVideoMutation
} from "@/hooks/use-aegis-api";
import type { CameraSourceType } from "@/types";

const sourceTypeLabels: Record<CameraSourceType, string> = {
  LOCAL_DEVICE: "Local Device",
  RTSP_STREAM: "RTSP Stream",
  HTTP_STREAM: "HTTP Stream",
  BROWSER_WEBCAM: "Browser Webcam",
  UPLOADED_VIDEO: "Uploaded Video"
};

function defaultCameraId(type: CameraSourceType) {
  const suffix = Math.round(Date.now() / 1000).toString(36);
  return `${type.toLowerCase().replaceAll("_", "-")}-${suffix}`;
}

export function CameraForm() {
  const [sourceType, setSourceType] = useState<CameraSourceType>("BROWSER_WEBCAM");
  const [cameraId, setCameraId] = useState(defaultCameraId("BROWSER_WEBCAM"));
  const [name, setName] = useState("Browser Webcam");
  const [location, setLocation] = useState("");
  const [url, setUrl] = useState("");
  const [deviceIndex, setDeviceIndex] = useState(0);
  const [autoStart, setAutoStart] = useState(true);
  const [videoFile, setVideoFile] = useState<File | null>(null);

  const createCamera = useCreateCameraMutation();
  const testConnection = useCameraConnectionTestMutation();
  const uploadVideo = useUploadVideoMutation();
  const processVideo = useProcessVideoMutation();

  const payload = useMemo(
    () => ({
      camera_id: cameraId.trim(),
      source_type: sourceType,
      name: name.trim() || undefined,
      location: location.trim() || undefined,
      enabled: true,
      url: sourceType === "RTSP_STREAM" || sourceType === "HTTP_STREAM" ? url.trim() : undefined,
      device_index: sourceType === "LOCAL_DEVICE" ? deviceIndex : undefined,
      auto_start: autoStart,
      connection_timeout: 5,
      max_retries: 10
    }),
    [autoStart, cameraId, deviceIndex, location, name, sourceType, url]
  );

  function handleSourceTypeChange(nextType: CameraSourceType) {
    setSourceType(nextType);
    setCameraId(defaultCameraId(nextType));
    setName(sourceTypeLabels[nextType]);
    setUrl("");
    setVideoFile(null);
    setAutoStart(nextType !== "UPLOADED_VIDEO");
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (sourceType === "UPLOADED_VIDEO") {
      if (!videoFile) return;
      const uploaded = await uploadVideo.mutateAsync(videoFile);
      await processVideo.mutateAsync({
        videoId: uploaded.video_id,
        cameraId: cameraId.trim() || undefined
      });
      return;
    }

    await createCamera.mutateAsync(payload);
  }

  async function runConnectionTest() {
    if (sourceType === "UPLOADED_VIDEO") return;
    await testConnection.mutateAsync(payload);
  }

  const busy = createCamera.isPending || testConnection.isPending || uploadVideo.isPending || processVideo.isPending;
  const error = createCamera.error || testConnection.error || uploadVideo.error || processVideo.error;
  const canTest = sourceType !== "UPLOADED_VIDEO";

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Register Camera Source</CardTitle>
          <CardDescription>Sources are persisted by the backend and connected to the detection pipeline.</CardDescription>
        </div>
      </CardHeader>

      <form className="grid gap-4 lg:grid-cols-2" onSubmit={submit}>
        <label className="space-y-2">
          <span className="text-xs font-medium uppercase tracking-[0.14em] text-slate-400">Source type</span>
          <Select value={sourceType} onChange={(event) => handleSourceTypeChange(event.target.value as CameraSourceType)}>
            {Object.entries(sourceTypeLabels).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
        </label>

        <label className="space-y-2">
          <span className="text-xs font-medium uppercase tracking-[0.14em] text-slate-400">Camera ID</span>
          <Input value={cameraId} onChange={(event) => setCameraId(event.target.value)} required />
        </label>

        <label className="space-y-2">
          <span className="text-xs font-medium uppercase tracking-[0.14em] text-slate-400">Name</span>
          <Input value={name} onChange={(event) => setName(event.target.value)} />
        </label>

        <label className="space-y-2">
          <span className="text-xs font-medium uppercase tracking-[0.14em] text-slate-400">Location</span>
          <Input value={location} onChange={(event) => setLocation(event.target.value)} />
        </label>

        {sourceType === "LOCAL_DEVICE" ? (
          <label className="space-y-2">
            <span className="text-xs font-medium uppercase tracking-[0.14em] text-slate-400">OpenCV device index</span>
            <Input type="number" min={0} value={deviceIndex} onChange={(event) => setDeviceIndex(Number(event.target.value))} />
          </label>
        ) : null}

        {sourceType === "RTSP_STREAM" || sourceType === "HTTP_STREAM" ? (
          <label className="space-y-2 lg:col-span-2">
            <span className="text-xs font-medium uppercase tracking-[0.14em] text-slate-400">Stream URL</span>
            <Input
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              placeholder={sourceType === "RTSP_STREAM" ? "rtsp://user:password@host:554/path" : "https://host/video.mjpg"}
              required
            />
          </label>
        ) : null}

        {sourceType === "UPLOADED_VIDEO" ? (
          <label className="space-y-2 lg:col-span-2">
            <span className="text-xs font-medium uppercase tracking-[0.14em] text-slate-400">Video file</span>
            <Input
              type="file"
              accept=".mp4,.avi,.mov,.mkv,.webm,video/*"
              onChange={(event) => setVideoFile(event.target.files?.[0] ?? null)}
              required
            />
          </label>
        ) : null}

        <label className="flex min-h-10 items-center gap-3 text-sm text-slate-300">
          <input
            type="checkbox"
            className="h-4 w-4 accent-cyan-300"
            checked={autoStart}
            onChange={(event) => setAutoStart(event.target.checked)}
            disabled={sourceType === "UPLOADED_VIDEO"}
          />
          Start processing after save
        </label>

        <div className="flex flex-wrap items-center justify-end gap-2 lg:col-span-2">
          {canTest ? (
            <Button type="button" variant="secondary" onClick={runConnectionTest} disabled={busy}>
              {testConnection.isPending ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <TestTube2 className="h-4 w-4" aria-hidden />}
              Test connection
            </Button>
          ) : null}
          <Button type="submit" disabled={busy || !cameraId.trim() || (sourceType === "UPLOADED_VIDEO" && !videoFile)}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : sourceType === "UPLOADED_VIDEO" ? <Upload className="h-4 w-4" aria-hidden /> : <Plus className="h-4 w-4" aria-hidden />}
            {sourceType === "UPLOADED_VIDEO" ? "Upload and process" : "Save camera"}
          </Button>
        </div>
      </form>

      {testConnection.data ? (
        <div className="mt-4 flex items-start gap-2 rounded-md border border-emerald-400/20 bg-emerald-400/10 p-3 text-sm text-emerald-100">
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          <span>{testConnection.data.ok ? "Backend connection test succeeded." : testConnection.data.error_message || "Backend connection test failed."}</span>
        </div>
      ) : null}

      {error ? (
        <div className="mt-4 rounded-md border border-rose-400/25 bg-rose-500/[0.08] p-3 text-sm text-rose-100">
          {getErrorMessage(error)}
        </div>
      ) : null}
    </Card>
  );
}
