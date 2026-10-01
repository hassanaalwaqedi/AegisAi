"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

import { AppShell } from "@/components/layout/app-shell";
import { LiveTrackingWorkspace } from "@/components/tracks/live-tracking-workspace";
import { useCamerasQuery, useTracksQuery } from "@/hooks/use-aegis-api";

export default function TracksPage() {
  return <Suspense fallback={<div className="min-h-[40vh]" aria-busy="true" />}><TracksPageContent /></Suspense>;
}

function TracksPageContent() {
  const searchParams = useSearchParams();
  const tracksQuery = useTracksQuery();
  const camerasQuery = useCamerasQuery();

  return (
    <AppShell>
      <LiveTrackingWorkspace
        tracks={tracksQuery.data?.tracks ?? []}
        cameras={camerasQuery.data?.cameras ?? []}
        isLoading={tracksQuery.isLoading}
        isUnavailable={tracksQuery.isError}
        camerasUnavailable={camerasQuery.isError}
        trackId={searchParams.get("track") ?? undefined}
        cameraId={searchParams.get("camera") ?? undefined}
        onRetry={() => {
          void tracksQuery.refetch();
          void camerasQuery.refetch();
        }}
      />
    </AppShell>
  );
}
