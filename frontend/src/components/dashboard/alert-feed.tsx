import { AlertTriangle } from "lucide-react";
import { RiskBadge } from "@/components/dashboard/risk-badge";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/layout/states";
import {
  formatDecimal,
  formatOperatorLabel,
  formatOperatorList,
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
        title="No alerts right now."
        description="New security activity will appear here when it needs review."
      />
    );
  }

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{title}</CardTitle>
          <p className="mt-1 text-sm text-slate-400">Live security activity needing review.</p>
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
              <span>Track: {event.track_id ?? "Unavailable"}</span>
              <span>Risk: {formatDecimal(getEventRiskScore(event), 2)}</span>
              <span>Weapon: {formatWeapon(event)}</span>
              <span>Association: {formatAssociation(event)}</span>
              <span>Verification: {formatOperatorLabel(event.verification_status)}</span>
              <span>Evidence: {formatOperatorLabel(event.evidence_type)}</span>
              <span>Activity source: {formatOperatorList(event.model_source)}</span>
            </div>
            {event.reason_codes?.length ? <p className="mt-2 text-xs text-slate-500">Why it needs review: {formatOperatorList(event.reason_codes)}</p> : null}
            <p className="mt-2 text-sm leading-6 text-slate-400">
              {getEventExplanation(event) ?? "No additional explanation is available for this alert."}
            </p>
          </div>
        ))}
      </div>
    </Card>
  );
}

function formatWeapon(event: RiskEvent) {
  if (!event.weapon_class) return "Unavailable";
  const confidence = typeof event.weapon_confidence === "number" ? ` ${Math.round(event.weapon_confidence * 100)}%` : "";
  return `${formatOperatorLabel(event.weapon_class)}${confidence}`;
}

function formatAssociation(event: RiskEvent) {
  if (!event.association_type) return "Unavailable";
  const person = event.person_track_id ? `Person #${event.person_track_id}` : "person unavailable";
  const frames = typeof event.stable_frames === "number" ? `${event.stable_frames} frames` : "duration unavailable";
  return `${formatOperatorLabel(event.association_type)} with ${person}, ${frames}`;
}
