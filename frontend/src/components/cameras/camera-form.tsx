"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { CheckCircle2, CircleAlert, Loader2, Plus, TestTube2, Upload } from "lucide-react";
import { useTranslations } from "next-intl";
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
  LOCAL_DEVICE: "sourceType_LOCAL_DEVICE",
  RTSP_STREAM: "sourceType_RTSP_STREAM",
  HTTP_STREAM: "sourceType_HTTP_STREAM",
  BROWSER_WEBCAM: "sourceType_BROWSER_WEBCAM",
  UPLOADED_VIDEO: "sourceType_UPLOADED_VIDEO"
};

function defaultCameraId(type: CameraSourceType) {
  const suffix = Math.round(Date.now() / 1000).toString(36);
  return `${type.toLowerCase().replaceAll("_", "-")}-${suffix}`;
}

type RtspMode = "guided" | "advanced";
type SaveMode = "active" | "disabled";

export function CameraForm() {
  const [sourceType, setSourceType] = useState<CameraSourceType>("BROWSER_WEBCAM");
  const [cameraId, setCameraId] = useState(defaultCameraId("BROWSER_WEBCAM"));
  const [name, setName] = useState("Browser Webcam");
  const [location, setLocation] = useState("");
  const [url, setUrl] = useState("");
  const [deviceIndex, setDeviceIndex] = useState(0);
  const [autoStart, setAutoStart] = useState(true);
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [rtspMode, setRtspMode] = useState<RtspMode>("guided");
  const [rtspProtocol, setRtspProtocol] = useState<"rtsp" | "rtsps">("rtsp");
  const [rtspHost, setRtspHost] = useState("");
  const [rtspPort, setRtspPort] = useState(554);
  const [rtspPath, setRtspPath] = useState("");
  const [rtspUsername, setRtspUsername] = useState("");
  const [rtspPassword, setRtspPassword] = useState("");
  const [saveMode, setSaveMode] = useState<SaveMode>("active");

  const createCamera = useCreateCameraMutation();
  const testConnection = useCameraConnectionTestMutation();
  const uploadVideo = useUploadVideoMutation();
  const processVideo = useProcessVideoMutation();
  const isRtsp = sourceType === "RTSP_STREAM";
  const resetConnectionTestRef = useRef(testConnection.reset);
  const t = useTranslations("cameras");

  const connectionFingerprint = useMemo(
    () => [sourceType, rtspMode, url, rtspProtocol, rtspHost, rtspPort, rtspPath, rtspUsername, rtspPassword].join("\u0000"),
    [rtspHost, rtspMode, rtspPassword, rtspPath, rtspPort, rtspProtocol, rtspUsername, sourceType, url]
  );

  // A successful result is proof only for the exact source configuration that
  // was tested.  Never let an old result authorize a changed stream.
  useEffect(() => {
    resetConnectionTestRef.current = testConnection.reset;
  }, [testConnection.reset]);

  useEffect(() => {
    resetConnectionTestRef.current();
  }, [connectionFingerprint]);

  const testPassed = Boolean(testConnection.data?.ok && testConnection.data.test_id);
  const activeSave = !isRtsp || saveMode === "active";
  const needsVerifiedTest = isRtsp && activeSave;
  const canSubmit = !needsVerifiedTest || testPassed;

  const payload = useMemo(
    () => ({
      camera_id: cameraId.trim(),
      source_type: sourceType,
      name: name.trim() || undefined,
      location: location.trim() || undefined,
      enabled: isRtsp ? activeSave : true,
      url: sourceType === "HTTP_STREAM" || (isRtsp && rtspMode === "advanced") ? url.trim() : undefined,
      device_index: sourceType === "LOCAL_DEVICE" ? deviceIndex : undefined,
      auto_start: isRtsp ? activeSave && autoStart : autoStart,
      rtsp_protocol: isRtsp && rtspMode === "guided" ? rtspProtocol : undefined,
      rtsp_host: isRtsp && rtspMode === "guided" ? rtspHost.trim() : undefined,
      rtsp_port: isRtsp && rtspMode === "guided" ? rtspPort : undefined,
      rtsp_path: isRtsp && rtspMode === "guided" ? rtspPath.trim() : undefined,
      rtsp_username: isRtsp && rtspMode === "guided" ? rtspUsername : undefined,
      rtsp_password: isRtsp && rtspMode === "guided" ? rtspPassword : undefined,
      connection_test_id: isRtsp ? testConnection.data?.test_id : undefined,
      allow_unverified_save: isRtsp && !activeSave,
      connection_timeout: 5,
      max_retries: 10
    }),
    [activeSave, autoStart, cameraId, deviceIndex, isRtsp, location, name, rtspHost, rtspMode, rtspPassword, rtspPath, rtspPort, rtspProtocol, rtspUsername, sourceType, testConnection.data?.test_id, url]
  );

  function handleSourceTypeChange(nextType: CameraSourceType) {
    setSourceType(nextType);
    setCameraId(defaultCameraId(nextType));
    setName(t(sourceTypeLabels[nextType]));
    setUrl("");
    setVideoFile(null);
    setAutoStart(nextType !== "UPLOADED_VIDEO");
    setSaveMode("active");
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (sourceType === "UPLOADED_VIDEO") {
      if (!videoFile) return;
      const uploaded = await uploadVideo.mutateAsync(videoFile);
      await processVideo.mutateAsync({ videoId: uploaded.video_id, cameraId: cameraId.trim() || undefined });
      return;
    }
    await createCamera.mutateAsync(payload);
  }

  async function runConnectionTest() {
    if (sourceType === "UPLOADED_VIDEO") return;
    try {
      await testConnection.mutateAsync(payload);
    } catch {
      // The mutation error is rendered below with the backend's safe message.
    }
  }

  const busy = createCamera.isPending || testConnection.isPending || uploadVideo.isPending || processVideo.isPending;
  const error = createCamera.error || testConnection.error || uploadVideo.error || processVideo.error;
  const canTest = sourceType !== "UPLOADED_VIDEO";
  const hasRtspEndpoint = rtspMode === "guided" ? Boolean(rtspHost.trim()) : Boolean(url.trim());
  const result = testConnection.data;

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{t("addCameraFormTitle")}</CardTitle>
          <CardDescription>{t("addCameraFormDesc")}</CardDescription>
        </div>
      </CardHeader>

      <form className="grid gap-4 lg:grid-cols-2" onSubmit={submit}>
        <label className="space-y-2">
          <span className="text-xs font-medium uppercase tracking-[0.14em] text-slate-400">{t("sourceType")}</span>
          <Select value={sourceType} onChange={(event) => handleSourceTypeChange(event.target.value as CameraSourceType)}>
            {Object.entries(sourceTypeLabels).map(([value, label]) => <option key={value} value={value}>{t(label)}</option>)}
          </Select>
        </label>

        <label className="space-y-2">
          <span className="text-xs font-medium uppercase tracking-[0.14em] text-slate-400">{t("cameraReference")}</span>
          <Input value={cameraId} onChange={(event) => setCameraId(event.target.value)} required />
        </label>

        <label className="space-y-2">
          <span className="text-xs font-medium uppercase tracking-[0.14em] text-slate-400">{t("cameraName")}</span>
          <Input value={name} onChange={(event) => setName(event.target.value)} />
        </label>

        <label className="space-y-2">
          <span className="text-xs font-medium uppercase tracking-[0.14em] text-slate-400">{t("locationZone")}</span>
          <Input value={location} onChange={(event) => setLocation(event.target.value)} />
        </label>

        {sourceType === "LOCAL_DEVICE" ? (
          <label className="space-y-2">
          <span className="text-xs font-medium uppercase tracking-[0.14em] text-slate-400">{t("cameraDeviceNumber")}</span>
            <Input type="number" min={0} value={deviceIndex} onChange={(event) => setDeviceIndex(Number(event.target.value))} />
          </label>
        ) : null}

        {isRtsp ? (
          <fieldset className="space-y-4 lg:col-span-2">
            <legend className="text-xs font-medium uppercase tracking-[0.14em] text-slate-400">{t("rtspSetup")}</legend>
            <div className="flex flex-wrap gap-4 text-sm text-slate-300">
              <label className="flex items-center gap-2"><input type="radio" checked={rtspMode === "guided"} onChange={() => setRtspMode("guided")} /> {t("guidedSetup")}</label>
              <label className="flex items-center gap-2"><input type="radio" checked={rtspMode === "advanced"} onChange={() => setRtspMode("advanced")} /> {t("advancedUrl")}</label>
            </div>

            {rtspMode === "guided" ? (
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="space-y-2">
                  <span className="text-xs font-medium uppercase tracking-[0.14em] text-slate-400">{t("protocol")}</span>
                  <Select value={rtspProtocol} onChange={(event) => setRtspProtocol(event.target.value as "rtsp" | "rtsps")}>
                    <option value="rtsp">rtsp</option><option value="rtsps">rtsps</option>
                  </Select>
                </label>
                <label className="space-y-2">
                  <span className="text-xs font-medium uppercase tracking-[0.14em] text-slate-400">{t("hostIp")}</span>
                  <Input value={rtspHost} onChange={(event) => setRtspHost(event.target.value)} placeholder="192.168.1.20" required />
                </label>
                <label className="space-y-2">
                  <span className="text-xs font-medium uppercase tracking-[0.14em] text-slate-400">{t("port")}</span>
                  <Input type="number" min={1} max={65535} value={rtspPort} onChange={(event) => setRtspPort(Number(event.target.value) || 554)} />
                </label>
                <label className="space-y-2">
                  <span className="text-xs font-medium uppercase tracking-[0.14em] text-slate-400">{t("streamPath")}</span>
                  <Input value={rtspPath} onChange={(event) => setRtspPath(event.target.value)} placeholder="stream1" />
                </label>
                <label className="space-y-2">
                  <span className="text-xs font-medium uppercase tracking-[0.14em] text-slate-400">{t("username")}</span>
                  <Input autoComplete="username" value={rtspUsername} onChange={(event) => setRtspUsername(event.target.value)} />
                </label>
                <label className="space-y-2">
                  <span className="text-xs font-medium uppercase tracking-[0.14em] text-slate-400">{t("password")}</span>
                  <Input type="password" autoComplete="new-password" value={rtspPassword} onChange={(event) => setRtspPassword(event.target.value)} />
                </label>
              </div>
            ) : (
              <label className="block space-y-2">
                <span className="text-xs font-medium uppercase tracking-[0.14em] text-slate-400">{t("fullRtspUrl")}</span>
                <Input type="password" autoComplete="off" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="rtsp://username:password@host:554/stream" required />
                <span className="block text-xs text-slate-500">{t("advancedUrlDesc")}</span>
              </label>
            )}
          </fieldset>
        ) : null}

        {sourceType === "HTTP_STREAM" ? (
          <label className="space-y-2 lg:col-span-2">
            <span className="text-xs font-medium uppercase tracking-[0.14em] text-slate-400">{t("streamUrl")}</span>
            <Input value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://host/video.mjpg" required />
          </label>
        ) : null}

        {sourceType === "UPLOADED_VIDEO" ? (
          <label className="space-y-2 lg:col-span-2">
            <span className="text-xs font-medium uppercase tracking-[0.14em] text-slate-400">{t("videoFile")}</span>
            <Input type="file" accept=".mp4,.avi,.mov,.mkv,.webm,video/*" onChange={(event) => setVideoFile(event.target.files?.[0] ?? null)} required />
          </label>
        ) : null}

        {isRtsp ? (
          <fieldset className="space-y-3 lg:col-span-2">
            <legend className="text-xs font-medium uppercase tracking-[0.14em] text-slate-400">{t("saveModeLabel")}</legend>
            <div className="flex flex-wrap gap-4 text-sm text-slate-300">
              <label className="flex items-center gap-2"><input type="radio" checked={saveMode === "active"} onChange={() => setSaveMode("active")} /> {t("saveAsActive")}</label>
              <label className="flex items-center gap-2"><input type="radio" checked={saveMode === "disabled"} onChange={() => setSaveMode("disabled")} /> {t("saveAsDisabled")}</label>
            </div>
            {saveMode === "active" ? (
              <label className="flex min-h-10 items-center gap-3 text-sm text-slate-300">
                <input type="checkbox" className="h-4 w-4 accent-cyan-300" checked={autoStart} onChange={(event) => setAutoStart(event.target.checked)} />
                {t("startProcessing")}
              </label>
            ) : <p className="text-xs text-amber-100">{t("saveDisabledDesc")}</p>}
          </fieldset>
        ) : (
          <label className="flex min-h-10 items-center gap-3 text-sm text-slate-300">
            <input type="checkbox" className="h-4 w-4 accent-cyan-300" checked={autoStart} onChange={(event) => setAutoStart(event.target.checked)} disabled={sourceType === "UPLOADED_VIDEO"} />
            {t("startProcessing")}
          </label>
        )}

        {isRtsp && !testPassed && saveMode === "active" ? <p className="text-sm text-amber-100 lg:col-span-2">{t("runTestBeforeSave")}</p> : null}

        <div className="flex flex-wrap items-center justify-end gap-2 lg:col-span-2">
          {canTest ? <Button type="button" variant="secondary" onClick={runConnectionTest} disabled={busy || (isRtsp && !hasRtspEndpoint)}>
            {testConnection.isPending ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <TestTube2 className="h-4 w-4" aria-hidden />}
            {t("testConnection")}
          </Button> : null}
          <Button type="submit" disabled={busy || !cameraId.trim() || !canSubmit || (sourceType === "UPLOADED_VIDEO" && !videoFile)}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : sourceType === "UPLOADED_VIDEO" ? <Upload className="h-4 w-4" aria-hidden /> : <Plus className="h-4 w-4" aria-hidden />}
            {sourceType === "UPLOADED_VIDEO" ? t("uploadAndProcess") : saveMode === "disabled" ? t("saveDisabledCamera") : t("saveCameraBtn")}
          </Button>
        </div>
      </form>

      {result ? (
        <section className={`mt-4 rounded-md border p-3 text-sm ${result.ok ? "border-emerald-400/25 bg-emerald-400/10 text-emerald-100" : "border-eose-400/25 bg-rose-500/[0.08] text-rose-100"}`} aria-live="polite">
          <div className="flex items-start gap-2"><span className="mt-0.5">{result.ok ? <CheckCircle2 className="h-4 w-4" aria-hidden /> : <CircleAlert className="h-4 w-4" aria-hidden />}</span><div><p className="font-medium">{result.ok ? t("connectionVerified") : t("connectionTestFailed")}</p><p className="mt-1">{connectionTestMessage(result, t)}</p></div></div>
          <dl className="mt-3 grid gap-x-4 gap-y-1 text-xs sm:grid-cols-2">
            {result.masked_url ? <><dt className="text-slate-400">{t("streamInfo")}</dt><dd className="break-all">{result.masked_url}</dd></> : null}
            {result.error_category ? <><dt className="text-slate-400">{t("connectionStatus")}</dt><dd>{connectionTestResultLabel(result, t)}</dd></> : null}
            {result.dns_resolved !== undefined && result.dns_resolved !== null ? <><dt className="text-slate-400">{t("cameraAddressFound")}</dt><dd>{result.dns_resolved ? t("yes") : t("no")}</dd></> : null}
            {result.host_reachable !== undefined && result.host_reachable !== null ? <><dt className="text-slate-400">{t("cameraReachable")}</dt><dd>{result.host_reachable ? t("yes") : t("no")}</dd></> : null}
            {result.time_to_first_frame_ms !== undefined && result.time_to_first_frame_ms !== null ? <><dt className="text-slate-400">{t("firstImage")}</dt><dd>{result.time_to_first_frame_ms} ms</dd></> : null}
            {result.width && result.height ? <><dt className="text-slate-400">{t("imageSize")}</dt><dd>{result.width} × {result.height}</dd></> : null}
          </dl>
          {result.ok && result.snapshot_data_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={result.snapshot_data_url} alt="Verified camera test snapshot" className="mt-3 max-h-48 w-full rounded border border-white/10 object-contain" />
          ) : null}
        </section>
      ) : null}

      {error ? <div className="mt-4 rounded-md border border-eose-400/25 bg-rose-500/[0.08] p-3 text-sm text-rose-100">{getErrorMessage(error)}</div> : null}
    </Card>
  );
}

function connectionTestMessage(result: { ok: boolean; error_category?: string | null; error_message?: string | null }, t: any) {
  if (result.ok) return t("conn_msg_ok");
  const category = result.error_category?.toLowerCase() ?? "";
  if (category === "youtube_media_unavailable") return t("conn_msg_youtube_media");
  if (category.includes("youtube")) return t("conn_msg_youtube_resolve");
  if (category.includes("auth")) return t("conn_msg_auth");
  if (category.includes("dns") || category.includes("host")) return t("conn_msg_dns");
  if (category.includes("timeout")) return t("conn_msg_timeout");
  if (category.includes("frame")) return t("conn_msg_frame");
  if (category.includes("url") || category.includes("address")) return t("conn_msg_url");
  return t("conn_msg_default");
}

function connectionTestResultLabel(result: { ok: boolean; error_category?: string | null }, t: any) {
  if (result.ok) return t("conn_lbl_ok");
  const category = result.error_category?.toLowerCase() ?? "";
  if (category.includes("youtube")) return t("conn_lbl_youtube");
  if (category.includes("auth")) return t("conn_lbl_auth");
  if (category.includes("dns") || category.includes("host")) return t("conn_lbl_dns");
  if (category.includes("timeout")) return t("conn_lbl_timeout");
  if (category.includes("frame")) return t("conn_lbl_frame");
  if (category.includes("url") || category.includes("address")) return t("conn_lbl_url");
  return t("conn_lbl_default");
}

export const cameraFormInternals = { connectionTestMessage, connectionTestResultLabel };
