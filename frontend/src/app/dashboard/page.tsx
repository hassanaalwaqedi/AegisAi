"use client";

import { AlertFeed } from "@/components/dashboard/alert-feed";
import { ModelCapabilityBanner } from "@/components/dashboard/model-capability-banner";
import { RiskSummary } from "@/components/dashboard/risk-summary";
import { SourceStatusCard } from "@/components/dashboard/source-status-card";
import { SystemHealthCard } from "@/components/dashboard/system-health-card";
import { TrackTable } from "@/components/dashboard/track-table";
import { ApiStatusBanner } from "@/components/layout/api-status-banner";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { ErrorState, LoadingState } from "@/components/layout/states";
import { useEventsQuery, useStatisticsQuery, useStatusQuery, useTracksQuery } from "@/hooks/use-aegis-api";
import { useAegisWebSocket } from "@/hooks/use-aegis-websocket";
import type { EventsResponse, StatusResponse, TracksResponse } from "@/types";

export default function DashboardPage() {
  const statusQuery = useStatusQuery();
  const tracksQuery = useTracksQuery();
  const eventsQuery = useEventsQuery();
  const statisticsQuery = useStatisticsQuery();
  const websocket = useAegisWebSocket(true);

  const liveStatus: StatusResponse | undefined = websocket.message?.status
    ? {
        status: "ok",
        timestamp: websocket.message.timestamp,
        system: websocket.message.status
      }
    : statusQuery.data;

  const liveTracks: TracksResponse | undefined = websocket.message?.tracks
    ? {
        count: websocket.message.tracks.length,
        tracks: websocket.message.tracks
      }
    : tracksQuery.data;

  const websocketEvents = websocket.message?.events ?? (websocket.message?.event ? [websocket.message.event] : websocket.message?.alert ? [websocket.message.alert] : undefined);
  const liveEvents: EventsResponse | undefined = websocketEvents
    ? {
        count: websocketEvents.length,
        events: websocketEvents
      }
    : eventsQuery.data;

  const liveStatistics = websocket.message?.statistics ?? statisticsQuery.data;
  const initialLoading = [statusQuery, tracksQuery, eventsQuery, statisticsQuery].every((query) => query.isLoading);
  const tracks = liveTracks?.tracks ?? [];
  const confirmedEvents = (liveEvents?.events ?? []).filter((event) => event.verification_status === undefined || event.verification_status === "confirmed");
  const candidateSignals = tracks.filter((track) => track.verification_status === "candidate" || track.risk_level === "CANDIDATE_MEDIUM");

  return (
    <AppShell>
      <section className="section-shell">
        <PageHeader
          eyebrow="Operations"
          title="Command Dashboard"
          description="Live operational view backed by AegisAI FastAPI endpoints and validated WebSocket messages when available."
          badge="Production data only"
        />

        <ApiStatusBanner
          endpoints={[
            { name: "/status", query: statusQuery },
            { name: "/tracks", query: tracksQuery },
            { name: "/events", query: eventsQuery },
            { name: "/statistics", query: statisticsQuery }
          ]}
          websocketState={websocket.state}
          websocketError={websocket.error}
        />

        {initialLoading ? <LoadingState /> : null}

        <div className="space-y-5">
          <ModelCapabilityBanner status={liveStatus} />

          <RiskSummary status={liveStatus} tracks={liveTracks} events={liveEvents} statistics={liveStatistics} />

          <div className="grid gap-5 lg:grid-cols-[1fr_0.85fr]">
            {statusQuery.isError && !liveStatus ? <ErrorState error={statusQuery.error} title="/status unavailable" /> : <SystemHealthCard status={liveStatus} />}
            {statusQuery.isError && !liveStatus ? <ErrorState error={statusQuery.error} title="Source status unavailable" /> : <SourceStatusCard status={liveStatus} />}
          </div>

          <div className="grid gap-5 xl:grid-cols-[1.1fr_0.9fr]">
            {tracksQuery.isError && !liveTracks ? <ErrorState error={tracksQuery.error} title="/tracks unavailable" /> : <TrackTable tracks={tracks} />}
            {eventsQuery.isError && !liveEvents ? <ErrorState error={eventsQuery.error} title="/events unavailable" /> : <AlertFeed events={confirmedEvents} />}
          </div>

          <TrackTable
            tracks={candidateSignals}
            title="Candidate Signals"
            description="BBox-only motion and other unconfirmed backend signals. These are not confirmed alerts."
            emptyTitle="No candidate signals returned"
            emptyDescription="The backend has not reported unconfirmed motion or other candidate risk signals."
          />

          {statisticsQuery.isError && !liveStatistics ? <ErrorState error={statisticsQuery.error} title="/statistics unavailable" /> : null}
        </div>
      </section>
    </AppShell>
  );
}
