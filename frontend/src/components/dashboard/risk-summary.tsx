import { AlertTriangle, Gauge, ScanSearch, Users } from "lucide-react";
import { StatusCard } from "@/components/dashboard/status-card";
import { formatDecimal, formatNumber, getCrowdMetric, getStatusSystem } from "@/lib/data-format";
import type { EventsResponse, StatisticsResponse, StatusResponse, TracksResponse } from "@/types";

type RiskSummaryProps = {
  status?: StatusResponse;
  tracks?: TracksResponse;
  events?: EventsResponse;
  statistics?: StatisticsResponse;
};

export function RiskSummary({ status, tracks, events, statistics }: RiskSummaryProps) {
  const system = getStatusSystem(status);
  const highRiskTracks = tracks?.tracks.filter((track) => track.risk_level === "HIGH" || track.risk_level === "CRITICAL").length;

  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <StatusCard
        label="Total detections"
        value={formatNumber(system.total_detections)}
        detail="Current system activity"
        icon={ScanSearch}
      />
      <StatusCard
        label="Active tracks"
        value={formatNumber(tracks?.count ?? system.active_tracks)}
        detail="Current tracked activity"
        icon={Users}
        tone="good"
      />
      <StatusCard
        label="High-risk alerts"
        value={formatNumber(system.high_risk_count ?? highRiskTracks)}
        detail={events ? `${events.count} recent alerts` : "Current alert activity"}
        icon={AlertTriangle}
        tone={highRiskTracks && highRiskTracks > 0 ? "danger" : "neutral"}
      />
      <StatusCard
        label="Crowd density"
        value={formatDecimal(getCrowdMetric(statistics, "max_density"), 1)}
        detail="Highest current crowd level"
        icon={Gauge}
        tone="warning"
      />
    </div>
  );
}
