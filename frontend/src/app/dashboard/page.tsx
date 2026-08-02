"use client";

import { AppShell } from "@/components/layout/app-shell";
import { OperatorDashboard } from "@/components/dashboard/operator-dashboard";
import { useCamerasQuery, useEventsQuery, useStatusQuery } from "@/hooks/use-aegis-api";

export default function DashboardPage() {
  const statusQuery = useStatusQuery();
  const camerasQuery = useCamerasQuery();
  const eventsQuery = useEventsQuery();

  const isLoading = statusQuery.isLoading || camerasQuery.isLoading || eventsQuery.isLoading;
  const isUnavailable = statusQuery.isError || camerasQuery.isError || eventsQuery.isError;
  const retry = () => {
    void Promise.all([statusQuery.refetch(), camerasQuery.refetch(), eventsQuery.refetch()]);
  };

  return (
    <AppShell>
      <OperatorDashboard
        cameras={camerasQuery.data?.cameras ?? []}
        events={eventsQuery.data?.events ?? []}
        status={statusQuery.data}
        isLoading={isLoading}
        isUnavailable={isUnavailable}
        onRetry={retry}
      />
    </AppShell>
  );
}
