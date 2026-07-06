"use client";

import { Trash2, Play, Square, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorState, LoadingState } from "@/components/layout/states";
import { CameraStatusBadge } from "@/components/cameras/camera-status-badge";
import { getErrorMessage } from "@/lib/errors";
import { cn, formatTime } from "@/lib/utils";
import {
  useCamerasQuery,
  useDeleteCameraMutation,
  useStartCameraMutation,
  useStopCameraMutation
} from "@/hooks/use-aegis-api";
import type { Camera } from "@/types";

const sourceLabels: Record<Camera["source_type"], string> = {
  LOCAL_DEVICE: "Local",
  RTSP_STREAM: "RTSP",
  HTTP_STREAM: "HTTP",
  BROWSER_WEBCAM: "Browser",
  UPLOADED_VIDEO: "Video"
};

export function CameraInventory({
  selectedCameraId,
  onSelect
}: {
  selectedCameraId?: string;
  onSelect: (camera: Camera) => void;
}) {
  const query = useCamerasQuery();
  const startCamera = useStartCameraMutation();
  const stopCamera = useStopCameraMutation();
  const deleteCamera = useDeleteCameraMutation();
  const actionError = startCamera.error || stopCamera.error || deleteCamera.error;

  if (query.isLoading) return <LoadingState label="Loading cameras" />;
  if (query.isError) return <ErrorState error={query.error} title="/cameras unavailable" />;

  const cameras = query.data?.cameras ?? [];

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Camera Inventory</CardTitle>
          <CardDescription>All rows are returned by the backend camera registry.</CardDescription>
        </div>
        <ShieldCheck className="h-5 w-5 text-signal-cyan" aria-hidden />
      </CardHeader>

      {actionError ? <p className="mb-3 rounded-md border border-rose-400/25 bg-rose-500/[0.08] p-3 text-sm text-rose-100">{getErrorMessage(actionError)}</p> : null}

      {cameras.length === 0 ? (
        <EmptyState title="No cameras registered" description="Add a real camera source or upload a test video to begin processing." />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-left text-sm">
            <thead className="border-b border-white/10 text-xs uppercase tracking-[0.14em] text-slate-500">
              <tr>
                <th className="pb-3 font-medium">Camera</th>
                <th className="pb-3 font-medium">Type</th>
                <th className="pb-3 font-medium">Status</th>
                <th className="pb-3 font-medium">Frames</th>
                <th className="pb-3 font-medium">Last frame</th>
                <th className="pb-3 text-right font-medium">Controls</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/10">
              {cameras.map((camera) => {
                const selected = selectedCameraId === camera.camera_id;
                const isBusy = startCamera.isPending || stopCamera.isPending || deleteCamera.isPending;
                return (
                  <tr
                    key={camera.camera_id}
                    className={cn("cursor-pointer transition hover:bg-white/[0.035]", selected && "bg-signal-cyan/10")}
                    onClick={() => onSelect(camera)}
                  >
                    <td className="py-3 pr-4 align-top">
                      <p className="font-medium text-white">{camera.name || camera.camera_id}</p>
                      <p className="mt-1 text-xs text-slate-500">{camera.camera_id}</p>
                      {camera.url ? <p className="mt-1 max-w-[260px] truncate text-xs text-slate-500">{camera.url}</p> : null}
                      {camera.runtime.error_message ? <p className="mt-1 max-w-[320px] text-xs text-rose-200">{camera.runtime.error_message}</p> : null}
                    </td>
                    <td className="py-3 pr-4 align-top text-slate-300">{sourceLabels[camera.source_type]}</td>
                    <td className="py-3 pr-4 align-top">
                      <CameraStatusBadge status={camera.runtime.status} />
                    </td>
                    <td className="py-3 pr-4 align-top text-slate-300">
                      <p>{camera.runtime.frames_received ?? 0}</p>
                      <p className="text-xs text-slate-500">{camera.runtime.fps ?? 0} FPS</p>
                    </td>
                    <td className="py-3 pr-4 align-top text-slate-400">{formatTime(camera.runtime.last_frame_time ?? undefined)}</td>
                    <td className="py-3 align-top">
                      <div className="flex justify-end gap-2">
                        {camera.runtime.running ? (
                          <Button
                            type="button"
                            variant="secondary"
                            className="min-h-9 px-3"
                            disabled={isBusy}
                            onClick={(event) => {
                              event.stopPropagation();
                              stopCamera.mutate(camera.camera_id);
                            }}
                          >
                            <Square className="h-4 w-4" aria-hidden />
                          </Button>
                        ) : (
                          <Button
                            type="button"
                            variant="secondary"
                            className="min-h-9 px-3"
                            disabled={isBusy}
                            onClick={(event) => {
                              event.stopPropagation();
                              startCamera.mutate(camera.camera_id);
                            }}
                          >
                            <Play className="h-4 w-4" aria-hidden />
                          </Button>
                        )}
                        <Button
                          type="button"
                          variant="ghost"
                          className="min-h-9 px-3 text-rose-200 hover:bg-rose-500/10 hover:text-rose-100"
                          disabled={isBusy}
                          onClick={(event) => {
                            event.stopPropagation();
                            deleteCamera.mutate(camera.camera_id);
                          }}
                        >
                          <Trash2 className="h-4 w-4" aria-hidden />
                        </Button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
