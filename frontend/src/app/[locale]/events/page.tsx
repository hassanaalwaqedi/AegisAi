"use client";

import { Suspense } from "react";
import { ActivityAlertsWorkspace } from "@/components/events/activity-alerts-workspace";
import { AppShell } from "@/components/layout/app-shell";
import { useAlertsQuery, useCamerasQuery, useEventsQuery } from "@/hooks/use-aegis-api";

export default function EventsPage() {
  const eventsQuery = useEventsQuery();
  const camerasQuery = useCamerasQuery();
  const alertsQuery = useAlertsQuery();
  const retry = () => { eventsQuery.refetch(); camerasQuery.refetch(); alertsQuery.refetch(); };

  return (
    <AppShell>
      <ActivityAlertsWorkspace
        events={eventsQuery.data?.events ?? []}
        alerts={alertsQuery.data}
        cameras={camerasQuery.data?.cameras ?? []}
        isLoading={eventsQuery.isLoading || camerasQuery.isLoading || alertsQuery.isLoading}
        isUnavailable={eventsQuery.isError || alertsQuery.isError}
        camerasUnavailable={camerasQuery.isError}
        onRetry={retry}
      />
    </AppShell>
  );
}
