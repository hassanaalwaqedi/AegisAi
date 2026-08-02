"use client";

import { ActivityAlertsWorkspace } from "@/components/events/activity-alerts-workspace";
import { AppShell } from "@/components/layout/app-shell";
import { useCamerasQuery, useEventsQuery } from "@/hooks/use-aegis-api";

export default function EventsPage() {
  const eventsQuery = useEventsQuery();
  const camerasQuery = useCamerasQuery();
  const retry = () => {
    void Promise.all([eventsQuery.refetch(), camerasQuery.refetch()]);
  };

  return (
    <AppShell>
      <ActivityAlertsWorkspace
        events={eventsQuery.data?.events ?? []}
        cameras={camerasQuery.data?.cameras ?? []}
        isLoading={eventsQuery.isLoading || camerasQuery.isLoading}
        isUnavailable={eventsQuery.isError}
        camerasUnavailable={camerasQuery.isError}
        onRetry={retry}
      />
    </AppShell>
  );
}
