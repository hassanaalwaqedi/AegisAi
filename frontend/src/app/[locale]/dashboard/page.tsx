"use client";

import { AppShell } from "@/components/layout/app-shell";
import { OperatorDashboard } from "@/components/dashboard/operator-dashboard";
import { useAlertsQuery, useCamerasQuery, useEventsQuery, useIncidentsQuery, usePersistedEvidenceQuery, useStatusQuery } from "@/hooks/use-aegis-api";

export default function DashboardPage() {
  const statusQuery = useStatusQuery();
  const camerasQuery = useCamerasQuery();
  const eventsQuery = useEventsQuery();
  const alertsQuery = useAlertsQuery();
  const incidentsQuery = useIncidentsQuery();
  const evidenceQuery = usePersistedEvidenceQuery();

  const isLoading = statusQuery.isLoading || camerasQuery.isLoading || eventsQuery.isLoading || alertsQuery.isLoading || incidentsQuery.isLoading || evidenceQuery.isLoading;
  const isUnavailable = statusQuery.isError || camerasQuery.isError || eventsQuery.isError || alertsQuery.isError || incidentsQuery.isError || evidenceQuery.isError;
  const retry = () => {
    void Promise.all([statusQuery.refetch(), camerasQuery.refetch(), eventsQuery.refetch(), alertsQuery.refetch(), incidentsQuery.refetch(), evidenceQuery.refetch()]);
  };

  return (
    <AppShell>
      <OperatorDashboard
        cameras={camerasQuery.data?.cameras ?? []}
        events={eventsQuery.data?.events ?? []}
        alerts={alertsQuery.data}
        incidents={incidentsQuery.data?.incidents}
        evidence={evidenceQuery.data?.evidence}
        status={statusQuery.data}
        availability={{
          status: !statusQuery.isError,
          cameras: !camerasQuery.isError,
          alerts: !alertsQuery.isError,
          events: !eventsQuery.isError,
          incidents: !incidentsQuery.isError,
          evidence: !evidenceQuery.isError,
        }}
        isLoading={isLoading}
        isUnavailable={isUnavailable}
        onRetry={retry}
      />
    </AppShell>
  );
}
