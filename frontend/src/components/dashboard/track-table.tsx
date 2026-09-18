import { RiskBadge } from "@/components/dashboard/risk-badge";
import { EmptyState } from "@/components/layout/states";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDecimal, formatOperatorLabel, formatOperatorList, formatPercent, formatTimestamp, getTrackBehaviors, getTrackLastSeen, getTrackObjectName } from "@/lib/data-format";
import type { Track } from "@/types";

type TrackTableProps = {
  tracks: Track[];
  title?: string;
  description?: string;
  emptyTitle?: string;
  emptyDescription?: string;
};

export function TrackTable({
  tracks,
  title = "Active Tracks",
  description = "Current tracked activity from live cameras.",
  emptyTitle = "No active movement right now",
  emptyDescription = "Tracked activity will appear here when movement is detected."
}: TrackTableProps) {
  if (tracks.length === 0) {
    return (
      <EmptyState
        title={emptyTitle}
        description={emptyDescription}
      />
    );
  }

  return (
    <Card className="overflow-hidden p-0">
      <CardHeader className="p-5 pb-3">
        <div>
          <CardTitle>{title}</CardTitle>
          <p className="mt-1 text-sm text-slate-400">{description}</p>
        </div>
      </CardHeader>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[1700px] border-collapse text-start text-sm">
          <thead className="border-y border-white/10 bg-white/[0.035] text-xs uppercase text-slate-500">
            <tr>
              <th className="px-5 py-3 font-medium">Tracking ID</th>
              <th className="px-5 py-3 font-medium">Activity</th>
              <th className="px-5 py-3 font-medium">Confidence</th>
              <th className="px-5 py-3 font-medium">Risk</th>
              <th className="px-5 py-3 font-medium">Verification</th>
              <th className="px-5 py-3 font-medium">Evidence</th>
              <th className="px-5 py-3 font-medium">Association</th>
              <th className="px-5 py-3 font-medium">Activity source</th>
              <th className="px-5 py-3 font-medium">Why it needs review</th>
              <th className="px-5 py-3 font-medium">Behavior</th>
              <th className="px-5 py-3 font-medium">Explanation</th>
              <th className="px-5 py-3 font-medium">Movement</th>
              <th className="px-5 py-3 font-medium">Observed area</th>
              <th className="px-5 py-3 font-medium">Last Seen</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/8">
            {tracks.map((track) => {
              const behaviors = getTrackBehaviors(track);
              return (
                <tr key={track.track_id} className="bg-white/[0.015]">
                  <td className="px-5 py-4 font-mono text-signal-cyan">{track.track_id}</td>
                  <td className="px-5 py-4 text-white">{getTrackObjectName(track)}</td>
                  <td className="px-5 py-4 text-slate-300">{formatPercent(track.confidence)}</td>
                  <td className="px-5 py-4">
                    <div className="flex flex-col gap-1">
                      <RiskBadge level={track.risk_level} />
                      <span className="text-xs text-slate-500">Score {formatDecimal(track.risk_score, 2)}</span>
                    </div>
                  </td>
                  <td className="px-5 py-4 text-slate-300">{formatOperatorLabel(track.verification_status)}</td>
                  <td className="px-5 py-4 text-slate-300">{formatOperatorLabel(track.evidence_type)}</td>
                  <td className="px-5 py-4 text-slate-300">
                    {formatAssociation(track)}
                  </td>
                  <td className="px-5 py-4 text-slate-300">{formatOperatorList(track.model_source)}</td>
                  <td className="px-5 py-4 text-slate-300">{formatOperatorList(track.reason_codes)}</td>
                  <td className="px-5 py-4 text-slate-300">{behaviors.length ? formatOperatorList(behaviors) : "Unavailable"}</td>
                  <td className="px-5 py-4 text-slate-300">{track.risk_explanation ?? "Unavailable"}</td>
                  <td className="px-5 py-4 text-slate-300">{track.movement_state ?? "Unavailable"}</td>
                  <td className="px-5 py-4 font-mono text-xs text-slate-300">{track.bbox ? track.bbox.join(", ") : "Unavailable"}</td>
                  <td className="px-5 py-4 text-slate-300">{formatTimestamp(getTrackLastSeen(track))}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function formatAssociation(track: Track) {
  if (!track.association_type) {
    if (track.is_weapon) return "No person association";
    return "Unavailable";
  }

  const target = track.person_track_id ? `Person #${track.person_track_id}` : track.weapon_track_id ? `Weapon #${track.weapon_track_id}` : "associated object";
  const score = typeof track.association_score === "number" ? `confidence ${formatDecimal(track.association_score, 2)}` : "confidence unavailable";
  const frames = typeof track.stable_frames === "number" ? `${track.stable_frames} frames` : "duration unavailable";
  return `${formatOperatorLabel(track.association_type)} with ${target} (${score}, ${frames})`;
}
