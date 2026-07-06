"use client";

import { Eye } from "lucide-react";
import { RiskBadge } from "@/components/dashboard/risk-badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/layout/states";
import {
  formatDecimal,
  formatTimestamp,
  getEventId,
  getEventObject,
  getEventRiskScore,
  getEventSeverity,
  getEventTitle
} from "@/lib/data-format";
import type { RiskEvent } from "@/types";

type EventListProps = {
  events: RiskEvent[];
  onSelect: (event: RiskEvent) => void;
};

export function EventList({ events, onSelect }: EventListProps) {
  if (events.length === 0) {
    return (
      <EmptyState
        title="No risk events detected yet."
        description="The backend returned no risk events for the selected filters."
      />
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border border-white/10 bg-white/[0.04]">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[1500px] border-collapse text-left text-sm">
          <thead className="border-b border-white/10 bg-white/[0.035] text-xs uppercase text-slate-500">
            <tr>
              <th className="px-5 py-3 font-medium">Timestamp</th>
              <th className="px-5 py-3 font-medium">Severity</th>
              <th className="px-5 py-3 font-medium">Event</th>
              <th className="px-5 py-3 font-medium">Object</th>
              <th className="px-5 py-3 font-medium">Track</th>
              <th className="px-5 py-3 font-medium">Risk score</th>
              <th className="px-5 py-3 font-medium">Verification</th>
              <th className="px-5 py-3 font-medium">Evidence</th>
              <th className="px-5 py-3 font-medium">Association</th>
              <th className="px-5 py-3 font-medium">Model source</th>
              <th className="px-5 py-3 font-medium">Reason codes</th>
              <th className="px-5 py-3 font-medium">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/8">
            {events.map((event, index) => (
              <tr key={getEventId(event, index)} className="bg-command-900/30">
                <td className="px-5 py-4 text-slate-300">{formatTimestamp(event.timestamp)}</td>
                <td className="px-5 py-4">
                  <RiskBadge level={String(getEventSeverity(event)).toUpperCase()} />
                </td>
                <td className="px-5 py-4 font-medium text-white">{getEventTitle(event)}</td>
                <td className="px-5 py-4 text-slate-300">{getEventObject(event)}</td>
                <td className="px-5 py-4 font-mono text-slate-300">{event.track_id ?? "Not returned"}</td>
                <td className="px-5 py-4 text-slate-300">{formatDecimal(getEventRiskScore(event), 2)}</td>
                <td className="px-5 py-4 text-slate-300">{event.verification_status ?? "Not returned"}</td>
                <td className="px-5 py-4 text-slate-300">{event.evidence_type ?? "Not returned"}</td>
                <td className="px-5 py-4 text-slate-300">{formatAssociation(event)}</td>
                <td className="px-5 py-4 text-slate-300">{formatList(event.model_source)}</td>
                <td className="px-5 py-4 text-slate-300">{formatList(event.reason_codes)}</td>
                <td className="px-5 py-4">
                  <Button variant="secondary" className="h-9 px-3" onClick={() => onSelect(event)}>
                    <Eye className="h-4 w-4" aria-hidden />
                    Detail
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function formatList(values?: string[]) {
  return values?.length ? values.join(", ") : "Not returned";
}

function formatAssociation(event: RiskEvent) {
  if (!event.association_type) return "Not returned";
  const person = event.person_track_id ? `Person #${event.person_track_id}` : "person not returned";
  const weapon = event.weapon_class ?? event.object_class ?? event.class_name ?? "weapon";
  const score = typeof event.association_score === "number" ? `score ${formatDecimal(event.association_score, 2)}` : "score not returned";
  const frames = typeof event.stable_frames === "number" ? `${event.stable_frames} frames` : "frames not returned";
  return `${weapon} ${event.association_type} ${person} (${score}, ${frames})`;
}
