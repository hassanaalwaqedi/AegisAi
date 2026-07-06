"use client";

import { ApiStatusBanner } from "@/components/layout/api-status-banner";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { ErrorState, LoadingState } from "@/components/layout/states";
import { ModelCapabilityBanner } from "@/components/dashboard/model-capability-banner";
import { TrackTable } from "@/components/dashboard/track-table";
import { useStatusQuery, useTracksQuery } from "@/hooks/use-aegis-api";

export default function TracksPage() {
  const statusQuery = useStatusQuery();
  const tracksQuery = useTracksQuery();

  return (
    <AppShell>
      <section className="section-shell">
        <PageHeader
          eyebrow="Tracking"
          title="Tracked Objects"
          description="Persistent object tracking view sourced only from GET /tracks."
          badge="GET /tracks"
        />

        <ApiStatusBanner endpoints={[{ name: "/status", query: statusQuery }, { name: "/tracks", query: tracksQuery }]} />
        <ModelCapabilityBanner status={statusQuery.data} />

        {tracksQuery.isLoading ? <LoadingState label="Loading active tracks from backend" /> : null}
        {tracksQuery.isError ? <ErrorState error={tracksQuery.error} title="/tracks unavailable" /> : null}
        {tracksQuery.data ? (
          <TrackTable
            tracks={tracksQuery.data.tracks}
            title="Active Tracked Objects"
            description="Shows backend-returned track_id, class_name, confidence, bbox, movement, behavior, risk, and last seen fields."
          />
        ) : null}
      </section>
    </AppShell>
  );
}
