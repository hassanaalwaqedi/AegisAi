"use client";

import { AppShell } from "@/components/layout/app-shell";
import { LiveTrackingWorkspace } from "@/components/tracks/live-tracking-workspace";
import { useCamerasQuery, useTracksQuery } from "@/hooks/use-aegis-api";

export default function TracksPage() {
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
        onRetry={() => {
          void tracksQuery.refetch();
          void camerasQuery.refetch();
        }}
      />
    </AppShell>
  );
}
