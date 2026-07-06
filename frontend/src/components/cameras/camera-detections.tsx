"use client";

import { ScanSearch } from "lucide-react";
import { RiskBadge } from "@/components/dashboard/risk-badge";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorState, LoadingState } from "@/components/layout/states";
import { formatDecimal, formatPercent, getTrackBehaviors } from "@/lib/data-format";
import { useCameraDetectionsQuery } from "@/hooks/use-aegis-api";
import type { Camera } from "@/types";

export function CameraDetections({ camera }: { camera?: Camera }) {
  const query = useCameraDetectionsQuery(camera?.camera_id);

  if (!camera) {
    return <EmptyState title="Select a camera" description="Detection results appear after selecting a registered source." />;
  }

  if (query.isLoading) return <LoadingState label="Loading camera detections" />;
  if (query.isError) return <ErrorState error={query.error} title="/cameras/{camera_id}/detections unavailable" />;

  const detections = query.data?.detections ?? [];

  return (
    <Card className="overflow-hidden p-0">
      <CardHeader className="p-5 pb-3">
        <div>
          <CardTitle>Detection Results</CardTitle>
          <CardDescription>{camera.camera_id}</CardDescription>
        </div>
        <ScanSearch className="h-5 w-5 text-signal-cyan" aria-hidden />
      </CardHeader>

      {detections.length === 0 ? (
        <div className="p-5 pt-0">
          <EmptyState title="No active detections returned" description="No tracked objects have been returned by the backend for this camera yet." />
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1260px] border-collapse text-left text-sm">
            <thead className="border-y border-white/10 bg-white/[0.035] text-xs uppercase text-slate-500">
              <tr>
                <th className="px-5 py-3 font-medium">Track</th>
                <th className="px-5 py-3 font-medium">Class</th>
                <th className="px-5 py-3 font-medium">Confidence</th>
                <th className="px-5 py-3 font-medium">Risk</th>
                <th className="px-5 py-3 font-medium">Verification</th>
                <th className="px-5 py-3 font-medium">Evidence</th>
                <th className="px-5 py-3 font-medium">Model source</th>
                <th className="px-5 py-3 font-medium">Reason codes</th>
                <th className="px-5 py-3 font-medium">Explanation</th>
                <th className="px-5 py-3 font-medium">Behavior</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/8">
              {detections.slice().reverse().map((detection) => {
                const behaviors = getTrackBehaviors(detection);
                return (
                  <tr key={`${detection.track_id}-${detection.last_seen ?? detection.frame_id ?? ""}`} className="bg-white/[0.015]">
                    <td className="px-5 py-4 font-mono text-signal-cyan">{detection.track_id}</td>
                    <td className="px-5 py-4 text-white">{detection.class_name ?? "Not returned"}</td>
                    <td className="px-5 py-4 text-slate-300">{formatPercent(detection.confidence)}</td>
                    <td className="px-5 py-4">
                      <div className="flex flex-col gap-1">
                        <RiskBadge level={detection.risk_level} />
                        <span className="text-xs text-slate-500">Score {formatDecimal(detection.risk_score, 2)}</span>
                      </div>
                    </td>
                    <td className="px-5 py-4 text-slate-300">{detection.verification_status ?? "Not returned"}</td>
                    <td className="px-5 py-4 text-slate-300">{detection.evidence_type ?? "Not returned"}</td>
                    <td className="px-5 py-4 text-slate-300">{formatList(detection.model_source)}</td>
                    <td className="px-5 py-4 text-slate-300">{formatList(detection.reason_codes)}</td>
                    <td className="px-5 py-4 text-slate-300">{detection.risk_explanation ?? "Not returned"}</td>
                    <td className="px-5 py-4 text-slate-300">{behaviors.length ? behaviors.join(", ") : "Not returned"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

function formatList(values?: string[]) {
  return values?.length ? values.join(", ") : "Not returned";
}
