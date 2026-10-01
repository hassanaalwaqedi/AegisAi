"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { ActivityAlertsWorkspace } from "@/components/events/activity-alerts-workspace";
import { AppShell } from "@/components/layout/app-shell";
import { useAlertsQuery, useCamerasQuery, useEventsQuery } from "@/hooks/use-aegis-api";

export default function EventsPage() {
  return (
    <AppShell>
      <Suspense fallback={<div className="min-h-[40vh]" aria-busy="true" />}>
        <EventsWorkspace />
      </Suspense>
    </AppShell>
  );
}

function EventsWorkspace() {
  const searchParams = useSearchParams();
  const eventsQuery = useEventsQuery();
  const camerasQuery = useCamerasQuery();
  const alertsQuery = useAlertsQuery();
  const retry = () => { eventsQuery.refetch(); camerasQuery.refetch(); alertsQuery.refetch(); };

  return (
    <ActivityAlertsWorkspace
      events={eventsQuery.data?.events ?? []}
      alerts={alertsQuery.data}
      cameras={camerasQuery.data?.cameras ?? []}
      isLoading={eventsQuery.isLoading || camerasQuery.isLoading || alertsQuery.isLoading}
      isUnavailable={eventsQuery.isError || alertsQuery.isError}
      camerasUnavailable={camerasQuery.isError}
      incidentId={searchParams.get("incident") ?? undefined}
      eventId={searchParams.get("event") ?? undefined}
      onRetry={retry}
    />
  );
}
