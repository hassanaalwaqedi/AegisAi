"use client";

import { useEffect, useMemo, useState } from "react";
import { Plus, X } from "lucide-react";
import { ApiStatusBanner } from "@/components/layout/api-status-banner";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { BrowserWebcamCapture } from "@/components/cameras/browser-webcam-capture";
import { CameraCommandCenter } from "@/components/cameras/camera-command-center";
import { CameraForm } from "@/components/cameras/camera-form";
import { CameraInventory } from "@/components/cameras/camera-inventory";
import { ModelCapabilityBanner } from "@/components/dashboard/model-capability-banner";
import { Button } from "@/components/ui/button";
import { useCamerasQuery, useStatusQuery } from "@/hooks/use-aegis-api";
import type { Camera } from "@/types";

export default function CamerasPage() {
  const statusQuery = useStatusQuery();
  const camerasQuery = useCamerasQuery();
  const [selectedCameraId, setSelectedCameraId] = useState<string>("");
  const [registerOpen, setRegisterOpen] = useState(false);

  const selectedCamera = useMemo<Camera | undefined>(
    () => camerasQuery.data?.cameras.find((camera) => camera.camera_id === selectedCameraId),
    [camerasQuery.data?.cameras, selectedCameraId]
  );

  useEffect(() => {
    if (!selectedCameraId && camerasQuery.data?.cameras.length) {
      setSelectedCameraId(camerasQuery.data.cameras[0].camera_id);
    }
  }, [camerasQuery.data?.cameras, selectedCameraId]);

  return (
    <AppShell>
      <section className="mx-auto w-full max-w-[1800px] px-4 py-6 sm:px-6 lg:px-8">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <PageHeader
            eyebrow="Command Center"
            title="Camera Operations"
            description="Live source monitoring with backend detections, tracks, evidence, and controls."
            badge="No synthetic streams"
          />
          <Button type="button" className="self-start" onClick={() => setRegisterOpen(true)}>
            <Plus className="h-4 w-4" aria-hidden />
            Register source
          </Button>
        </div>

        <ApiStatusBanner
          endpoints={[
            { name: "/status", query: statusQuery },
            { name: "/cameras", query: camerasQuery }
          ]}
        />

        <ModelCapabilityBanner status={statusQuery.data} />

        <div className="mt-5 space-y-4">
          <CameraCommandCenter camera={selectedCamera} />
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(320px,0.42fr)]">
            <CameraInventory
              selectedCameraId={selectedCameraId}
              onSelect={(camera) => setSelectedCameraId(camera.camera_id)}
            />
            <BrowserWebcamCapture camera={selectedCamera} />
          </div>
        </div>

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
