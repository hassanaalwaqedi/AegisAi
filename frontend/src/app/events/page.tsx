"use client";

import { useMemo, useState } from "react";
import { EventDetailDialog } from "@/components/events/event-detail-dialog";
import { type EventFilters, EventFiltersBar } from "@/components/events/event-filters";
import { EventList } from "@/components/events/event-list";
import { ModelCapabilityBanner } from "@/components/dashboard/model-capability-banner";
import { ApiStatusBanner } from "@/components/layout/api-status-banner";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { ErrorState, LoadingState } from "@/components/layout/states";
import { useEventsQuery, useStatusQuery } from "@/hooks/use-aegis-api";
import { getEventObject, getEventSeverity } from "@/lib/data-format";
import type { RiskEvent } from "@/types";

const initialFilters: EventFilters = {
  severity: "All",
  objectType: "All",
  riskLevel: "All",
  timeWindow: "All"
};

export default function EventsPage() {
  const statusQuery = useStatusQuery();
  const eventsQuery = useEventsQuery();
  const [filters, setFilters] = useState(initialFilters);
  const [selectedEvent, setSelectedEvent] = useState<RiskEvent | null>(null);

  const filteredEvents = useMemo(() => {
    const events = eventsQuery.data?.events ?? [];
    const now = Date.now();

    return events.filter((event) => {
      const severityMatches = filters.severity === "All" || String(getEventSeverity(event)).toUpperCase() === filters.severity.toUpperCase();
      const objectMatches = filters.objectType === "All" || getEventObject(event) === filters.objectType;
      const riskMatches = filters.riskLevel === "All" || event.risk_level === filters.riskLevel;

      let timeMatches = true;
      if (filters.timeWindow !== "All") {
        const rawTimestamp = event.timestamp;
        const parsed =
          typeof rawTimestamp === "number"
            ? rawTimestamp * 1000
            : typeof rawTimestamp === "string"
              ? new Date(rawTimestamp).getTime()
              : Number.NaN;

        if (Number.isNaN(parsed)) {
          timeMatches = false;
        } else {
          const maxAge = filters.timeWindow === "Last hour" ? 60 * 60 * 1000 : 24 * 60 * 60 * 1000;
          timeMatches = now - parsed <= maxAge;
        }
      }

      return severityMatches && objectMatches && riskMatches && timeMatches;
    });
  }, [eventsQuery.data?.events, filters]);

  return (
    <AppShell>
      <section className="section-shell">
        <PageHeader
          eyebrow="Events"
          title="Risk Event Log"
          description="Operational event review sourced only from GET /events. Filters operate on the returned backend data."
          badge="GET /events"
        />

        <ApiStatusBanner endpoints={[{ name: "/status", query: statusQuery }, { name: "/events", query: eventsQuery }]} />
        <ModelCapabilityBanner status={statusQuery.data} />

        {eventsQuery.isLoading ? <LoadingState label="Loading events from backend" /> : null}
        {eventsQuery.isError ? <ErrorState error={eventsQuery.error} title="/events unavailable" /> : null}

        {eventsQuery.data ? (
          <div className="space-y-4">
            <EventFiltersBar events={eventsQuery.data.events} value={filters} onChange={setFilters} />
            <EventList events={filteredEvents} onSelect={setSelectedEvent} />
          </div>
        ) : null}
      </section>

      <EventDetailDialog event={selectedEvent} onClose={() => setSelectedEvent(null)} />
    </AppShell>
  );
}
