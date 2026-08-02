"use client";

import { Suspense, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { CheckCircle2, CircleAlert, LoaderCircle, Plus, X } from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { BrowserWebcamCapture } from "@/components/cameras/browser-webcam-capture";
import { CameraForm } from "@/components/cameras/camera-form";
import { CameraInventory } from "@/components/cameras/camera-inventory";
import { CameraDetailsDrawer, CameraWall, type CameraWallView } from "@/components/cameras/camera-wall";
import { Button } from "@/components/ui/button";
import { useCamerasQuery, useEventsQuery, useStatusQuery } from "@/hooks/use-aegis-api";
import type { Camera } from "@/types";

export default function CamerasPage() {
  return (
    <Suspense fallback={<CameraPageLoading />}>
      <CamerasPageContent />
    </Suspense>
  );
}

function CamerasPageContent() {
  const statusQuery = useStatusQuery();
  const camerasQuery = useCamerasQuery();
  const eventsQuery = useEventsQuery();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [registerOpen, setRegisterOpen] = useState(false);
  const selectedCameraId = searchParams.get("camera") ?? "";
  const requestedView = searchParams.get("view");
  const view: CameraWallView = requestedView === "focus" || requestedView === "map" ? requestedView : "grid";

  const selectedCamera = useMemo<Camera | undefined>(
    () => {
      const cameras = camerasQuery.data?.cameras ?? [];
      const cameraId = selectedCameraId || cameras[0]?.camera_id;
      return cameras.find((camera) => camera.camera_id === cameraId);
    },
    [camerasQuery.data?.cameras, selectedCameraId]
  );

  const connection = statusQuery.isLoading
    ? { label: "Checking system", tone: "loading" as const, status: "loading" as const }
    : statusQuery.isError
      ? { label: "System unavailable", tone: "offline" as const, status: "unavailable" as const }
      : statusQuery.data?.system?.running === false
        ? { label: "System degraded", tone: "offline" as const, status: "degraded" as const }
        : { label: "System connected", tone: "connected" as const, status: "connected" as const };
  const cameras = camerasQuery.data?.cameras ?? [];
  const activeCameraId = selectedCameraId || cameras[0]?.camera_id || "";

  const updateWorkspace = (next: { cameraId?: string; view?: CameraWallView }) => {
    const params = new URLSearchParams(searchParams.toString());
    const cameraId = next.cameraId ?? activeCameraId;
    const nextView = next.view ?? view;
    if (cameraId) params.set("camera", cameraId); else params.delete("camera");
    if (nextView === "grid") params.delete("view"); else params.set("view", nextView);
    router.replace(`/cameras${params.size ? `?${params.toString()}` : ""}`, { scroll: false });
  };

  return (
    <AppShell>
      <section className="mx-auto w-full max-w-[1800px] px-4 py-7 sm:px-6 lg:px-8">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight text-white sm:text-4xl">Live Cameras</h1>
            <p className="mt-2 text-base text-slate-400">Monitor cameras and review activity.</p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <SystemConnectionIndicator tone={connection.tone} label={connection.label} />
            <Button type="button" className="min-h-11 self-start px-4" onClick={() => setRegisterOpen(true)}>
            <Plus className="h-4 w-4" aria-hidden />
            Add camera
          </Button>
          </div>
        </div>

        <div className="mt-5">
          {camerasQuery.isLoading ? <CameraWallLoading /> : null}
          {camerasQuery.isError ? <div className="glass-panel rounded-xl border-rose-300/25 p-6 text-sm text-rose-100"><p>Live camera data is temporarily unavailable.</p><Button type="button" variant="ghost" className="mt-3 min-h-9 border border-rose-300/30 px-3 text-rose-100" onClick={() => void camerasQuery.refetch()}>Retry</Button></div> : null}
          {!camerasQuery.isLoading && !camerasQuery.isError && cameras.length === 0 ? (
            <div className="glass-panel rounded-xl p-8 text-center">
              <h2 className="text-xl font-semibold text-white">No cameras connected yet</h2>
              <p className="mt-2 text-sm text-slate-400">Add a camera to begin monitoring live activity.</p>
              <Button type="button" className="mt-5" onClick={() => setRegisterOpen(true)}><Plus className="h-4 w-4" aria-hidden />Add camera</Button>
            </div>
          ) : null}
          {!camerasQuery.isLoading && !camerasQuery.isError && cameras.length > 0 ? <CameraWall key={`${view}-${activeCameraId}`} cameras={cameras} events={eventsQuery.data?.events ?? []} initialView={view} initialCameraId={activeCameraId} systemStatus={connection.status} onViewChange={(nextView) => updateWorkspace({ view: nextView })} onCameraChange={(cameraId) => updateWorkspace({ cameraId, view: "focus" })} /> : null}
        </div>

        {cameras.length > 0 ? (
          <CameraDetailsDrawer>
            <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(320px,0.42fr)]">
              <CameraInventory selectedCameraId={activeCameraId} onSelect={(camera) => updateWorkspace({ cameraId: camera.camera_id, view: "focus" })} />
              <BrowserWebcamCapture camera={selectedCamera} />
            </div>
          </CameraDetailsDrawer>
        ) : null}

        {registerOpen ? (
          <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm" role="dialog" aria-modal="true" aria-label="Register camera source">
            <button className="absolute inset-0 cursor-default" type="button" aria-label="Close registration drawer" onClick={() => setRegisterOpen(false)} />
            <aside className="glass-panel absolute right-0 top-0 h-full w-full max-w-xl overflow-y-auto border-y-0 border-r-0 p-5 shadow-2xl">
              <div className="mb-4 flex items-center justify-between gap-3">
                <div>
                  <p className="text-xs uppercase tracking-[0.14em] text-slate-500">Source Registry</p>
                  <h2 className="mt-1 text-xl font-semibold text-white">Register Camera Source</h2>
                </div>
                <Button type="button" variant="ghost" className="min-h-9 px-3" onClick={() => setRegisterOpen(false)}>
                  <X className="h-4 w-4" aria-hidden />
                </Button>
              </div>
              <CameraForm />
            </aside>
          </div>
        ) : null}
      </section>
    </AppShell>
  );
}

function SystemConnectionIndicator({ tone, label }: { tone: "loading" | "offline" | "connected"; label: string }) {
  const Icon = tone === "connected" ? CheckCircle2 : tone === "offline" ? CircleAlert : LoaderCircle;
  return (
    <span className={`inline-flex min-h-10 items-center gap-2 rounded-md px-3 text-sm ${tone === "connected" ? "text-emerald-200" : tone === "offline" ? "text-rose-100" : "text-amber-100"}`} role="status">
      <Icon className={`h-4 w-4 ${tone === "loading" ? "animate-spin" : ""}`} aria-hidden />
      {label}
    </span>
  );
}

function CameraWallLoading() {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" aria-label="Loading camera wall" aria-busy="true">
      {Array.from({ length: 9 }, (_, index) => <div key={index} className="aspect-video animate-pulse rounded-xl border border-white/10 bg-white/[0.035]" />)}
    </div>
  );
}

function CameraPageLoading() {
  return (
    <AppShell>
      <section className="mx-auto w-full max-w-[1800px] px-4 py-7 sm:px-6 lg:px-8">
        <CameraWallLoading />
      </section>
    </AppShell>
  );
}
