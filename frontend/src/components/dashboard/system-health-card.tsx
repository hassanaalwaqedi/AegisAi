import { Activity, Cpu, Database, Gauge, RadioTower } from "lucide-react";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { getStatusSystem, formatDecimal, formatNumber } from "@/lib/data-format";
import type { StatusResponse } from "@/types";

type SystemHealthCardProps = {
  status?: StatusResponse;
};

export function SystemHealthCard({ status }: SystemHealthCardProps) {
  const system = getStatusSystem(status);
  const running = system.running;

  const rows = [
    { label: "Version", value: status?.version ?? "Not returned", icon: Cpu },
    { label: "FPS", value: formatDecimal(system.current_fps ?? system.fps, 1), icon: Gauge },
    { label: "Frames processed", value: formatNumber(system.frames_processed), icon: Database },
    { label: "Uptime seconds", value: formatNumber(system.uptime_seconds), icon: Activity },
    { label: "Semantic layer", value: typeof system.semantic_enabled === "boolean" ? (system.semantic_enabled ? "Enabled" : "Disabled") : "Not returned", icon: RadioTower }
  ];

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>System Health</CardTitle>
          <p className="mt-1 text-sm text-slate-400">Validated from GET /status</p>
        </div>
        <Badge variant={running ? "success" : running === false ? "warning" : "outline"}>
          {running === true ? "Running" : running === false ? "Stopped" : "Not returned"}
        </Badge>
      </CardHeader>

      <div className="space-y-3">
        {rows.map((row) => {
          const Icon = row.icon;
          return (
            <div key={row.label} className="flex items-center justify-between gap-4 rounded-md border border-white/8 bg-white/[0.035] px-3 py-2">
              <div className="flex items-center gap-2 text-sm text-slate-300">
                <Icon className="h-4 w-4 text-slate-500" aria-hidden />
                {row.label}
              </div>
              <span className="text-sm font-medium text-white">{row.value}</span>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
