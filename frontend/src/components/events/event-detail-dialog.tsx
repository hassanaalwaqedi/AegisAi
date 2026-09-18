"use client";

import { X } from "lucide-react";
import { RiskBadge } from "@/components/dashboard/risk-badge";
import { Button } from "@/components/ui/button";
import { formatDecimal, formatOperatorLabel, formatOperatorList, formatTimestamp, getEventExplanation, getEventFactors, getEventObject, getEventRiskScore, getEventSeverity, getEventTitle } from "@/lib/data-format";
import type { RiskEvent } from "@/types";

type EventDetailDialogProps = {
  event: RiskEvent | null;
  onClose: () => void;
};

export function EventDetailDialog({ event, onClose }: EventDetailDialogProps) {
  if (!event) return null;

  const factors = getEventFactors(event);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-command-950/80 p-4 backdrop-blur-sm" role="dialog" aria-modal="true">
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-lg border border-white/10 bg-command-900 shadow-2xl">
        <div className="flex items-start justify-between gap-4 border-b border-white/10 p-5">
          <div>
            <p className="text-xs uppercase tracking-[0.16em] text-signal-cyan">Risk event detail</p>
            <h2 className="mt-2 text-xl font-semibold text-white">{getEventTitle(event)}</h2>
          </div>
          <Button variant="ghost" className="h-9 w-9 px-0" onClick={onClose} aria-label="Close event detail">
            <X className="h-4 w-4" aria-hidden />
          </Button>
        </div>

        <div className="space-y-5 p-5">
          <div className="grid gap-3 sm:grid-cols-2">
            <DetailItem label="Severity" value={<RiskBadge level={String(getEventSeverity(event)).toUpperCase()} />} />
            <DetailItem label="Timestamp" value={formatTimestamp(event.timestamp)} />
            <DetailItem label="Object" value={getEventObject(event)} />
            <DetailItem label="Tracking ID" value={event.track_id ?? "Unavailable"} />
            <DetailItem label="Risk score" value={formatDecimal(getEventRiskScore(event), 2)} />
            <DetailItem label="Confidence" value={formatDecimal(event.confidence, 2)} />
            <DetailItem label="Verification" value={formatOperatorLabel(event.verification_status)} />
            <DetailItem label="Evidence" value={formatOperatorLabel(event.evidence_type)} />
            <DetailItem label="Weapon" value={formatWeapon(event)} />
            <DetailItem label="Association" value={formatAssociation(event)} />
            <DetailItem label="Observed duration" value={event.stable_frames ?? "Unavailable"} />
            <DetailItem label="Activity source" value={formatOperatorList(event.model_source)} />
            <DetailItem label="Zone" value={event.zone ?? "Unavailable"} />
            <DetailItem label="Camera" value={event.camera_id ?? "Unavailable"} />
          </div>

          <section>
            <h3 className="text-sm font-semibold text-white">Why this needs review</h3>
            <p className="mt-2 rounded-md border border-white/8 bg-white/[0.035] p-3 text-sm leading-6 text-slate-300">
              {getEventExplanation(event) ?? "No additional explanation is available for this alert."}
            </p>
          </section>

          <section>
            <h3 className="text-sm font-semibold text-white">Why it needs review</h3>
            {factors.length ? (
              <div className="mt-2 flex flex-wrap gap-2">
                {factors.map((factor) => (
                  <span key={factor} className="rounded-md border border-white/10 bg-white/[0.045] px-2 py-1 text-xs text-slate-300">
                    {formatOperatorLabel(factor)}
                  </span>
                ))}
              </div>
            ) : (
              <p className="mt-2 rounded-md border border-amber-300/20 bg-amber-300/[0.055] p-3 text-sm text-amber-100/75">
                No additional review reasons are available for this alert.
              </p>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}

function DetailItem({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-md border border-white/8 bg-white/[0.035] p-3">
      <p className="text-xs uppercase text-slate-500">{label}</p>
      <div className="mt-2 text-sm font-medium text-white">{value}</div>
    </div>
  );
}

function formatWeapon(event: RiskEvent) {
  if (!event.weapon_class) return "Unavailable";
  const confidence = typeof event.weapon_confidence === "number" ? ` (${formatDecimal(event.weapon_confidence, 2)})` : "";
  return `${formatOperatorLabel(event.weapon_class)}${confidence}`;
}

function formatAssociation(event: RiskEvent) {
  if (!event.association_type) return "Unavailable";
  const person = event.person_track_id ? `Person #${event.person_track_id}` : "person unavailable";
  const weapon = event.weapon_track_id ? `Weapon #${event.weapon_track_id}` : event.weapon_class ?? "weapon";
  const score = typeof event.association_score === "number" ? `confidence ${formatDecimal(event.association_score, 2)}` : "confidence unavailable";
  return `${formatOperatorLabel(event.association_type)}: ${formatOperatorLabel(weapon)} with ${person}, ${score}`;
}
