import { AlertTriangle } from "lucide-react";
import { RiskBadge } from "@/components/dashboard/risk-badge";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/layout/states";
import {
  formatDecimal,
  formatTimestamp,
  getEventExplanation,
  getEventId,
  getEventObject,
  getEventRiskScore,
  getEventSeverity,
  getEventTitle
} from "@/lib/data-format";
import type { RiskEvent } from "@/types";

type AlertFeedProps = {
  events: RiskEvent[];
  title?: string;
};

export function AlertFeed({ events, title = "Confirmed Alerts" }: AlertFeedProps) {
  if (events.length === 0) {
    return (
      <EmptyState
        title="No risk events detected yet."
        description="The dashboard will remain clear until the backend emits real risk events."
      />
    );
  }

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{title}</CardTitle>
          <p className="mt-1 text-sm text-slate-400">Validated from GET /events or live WebSocket messages</p>
        </div>
        <AlertTriangle className="h-5 w-5 text-amber-200" aria-hidden />
      </CardHeader>

      <div className="space-y-3">
        {events.slice(0, 8).map((event, index) => (
          <div key={getEventId(event, index)} className="rounded-md border border-white/8 bg-white/[0.035] p-3">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="text-sm font-semibold text-white">{getEventTitle(event)}</p>
                <p className="mt-1 text-xs text-slate-500">{formatTimestamp(event.timestamp)}</p>
              </div>
              <RiskBadge level={String(getEventSeverity(event)).toUpperCase()} />
            </div>
            <div className="mt-3 grid gap-2 text-sm text-slate-300 sm:grid-cols-3">
              <span>Object: {getEventObject(event)}</span>
              <span>Track: {event.track_id ?? "Not returned"}</span>
              <span>Risk: {formatDecimal(getEventRiskScore(event), 2)}</span>
              <span>Weapon: {formatWeapon(event)}</span>
              <span>Association: {formatAssociation(event)}</span>
              <span>Verification: {event.verification_status ?? "Not returned"}</span>
              <span>Evidence: {event.evidence_type ?? "Not returned"}</span>
              <span>Model: {event.model_source?.length ? event.model_source.join(", ") : "Not returned"}</span>
            </div>
            {event.reason_codes?.length ? <p className="mt-2 text-xs text-slate-500">Reasons: {event.reason_codes.join(", ")}</p> : null}
            <p className="mt-2 text-sm leading-6 text-slate-400">
              {getEventExplanation(event) ?? "Explanation not returned by backend for this event."}
            </p>
          </div>
        ))}
      </div>
    </Card>
  );
}

function formatWeapon(event: RiskEvent) {
  if (!event.weapon_class) return "Not returned";
  const confidence = typeof event.weapon_confidence === "number" ? ` ${Math.round(event.weapon_confidence * 100)}%` : "";
  return `${event.weapon_class}${confidence}`;
}

function formatAssociation(event: RiskEvent) {
  if (!event.association_type) return "Not returned";
  const person = event.person_track_id ? `Person #${event.person_track_id}` : "person not returned";
  const frames = typeof event.stable_frames === "number" ? `${event.stable_frames} frames` : "frames not returned";
  return `${event.association_type} with ${person}, ${frames}`;
}
