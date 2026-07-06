import { Camera, Radio } from "lucide-react";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { getStatusSystem } from "@/lib/data-format";
import type { StatusResponse } from "@/types";

type SourceStatusCardProps = {
  status?: StatusResponse;
};

export function SourceStatusCard({ status }: SourceStatusCardProps) {
  const system = getStatusSystem(status);
  const source = system.source ?? system.camera_id;
  const sourceStatus = system.source_status ?? system.camera_status;
  const hasSource = Boolean(source || sourceStatus);

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Camera / Source</CardTitle>
          <p className="mt-1 text-sm text-slate-400">Source metadata returned by GET /status</p>
        </div>
        <Camera className="h-5 w-5 text-signal-cyan" aria-hidden />
      </CardHeader>

      {hasSource ? (
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-4 rounded-md border border-white/8 bg-white/[0.035] px-3 py-2">
            <span className="text-sm text-slate-400">Source</span>
            <span className="text-sm font-medium text-white">{source ?? "Not returned"}</span>
          </div>
          <div className="flex items-center justify-between gap-4 rounded-md border border-white/8 bg-white/[0.035] px-3 py-2">
            <span className="text-sm text-slate-400">Status</span>
            <Badge variant={sourceStatus?.toLowerCase().includes("online") ? "success" : "outline"}>
              {sourceStatus ?? "Not returned"}
            </Badge>
          </div>
        </div>
      ) : (
        <div className="rounded-md border border-amber-300/20 bg-amber-300/[0.055] p-4">
          <div className="flex gap-3">
            <Radio className="mt-0.5 h-5 w-5 shrink-0 text-amber-200" aria-hidden />
            <div>
              <p className="text-sm font-semibold text-amber-100">Source status not returned</p>
              <p className="mt-1 text-sm leading-6 text-amber-100/70">
                The backend should include camera_id, source, camera_status, or source_status in /status for production source observability.
              </p>
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}
