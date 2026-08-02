import type { RiskEvent, RiskLevel, StatisticsResponse, StatusResponse, StatusSystem, Track } from "@/types";

export function formatNumber(value: unknown, unavailableText = "Not returned") {
  return typeof value === "number" && Number.isFinite(value) ? value.toLocaleString() : unavailableText;
}

export function formatDecimal(value: unknown, digits = 2, unavailableText = "Not returned") {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : unavailableText;
}

export function formatPercent(value: unknown, unavailableText = "Not returned") {
  return typeof value === "number" && Number.isFinite(value) ? `${Math.round(value * 100)}%` : unavailableText;
}

export function formatTimestamp(value: unknown) {
  if (typeof value === "number") {
    return new Date(value * 1000).toLocaleString();
  }

  if (typeof value !== "string") return "Not returned";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  return date.toLocaleString();
}

export function getStatusSystem(status?: StatusResponse): StatusSystem {
  return {
    ...(status?.system ?? {}),
    ...(status?.performance ?? {}),
    ...(status?.counts ?? {})
  };
}

export function getRiskLevel(value?: string): RiskLevel | undefined {
  if (value === "LOW" || value === "CANDIDATE_MEDIUM" || value === "MEDIUM" || value === "HIGH" || value === "CRITICAL") {
    return value;
  }

  return undefined;
}

export function getTrackBehaviors(track: Track) {
  if (track.behaviors?.length) return track.behaviors;
  if (track.behavior) return [track.behavior];
  return [];
}

export function getTrackLastSeen(track: Track) {
  return track.last_seen ?? track.last_updated;
}

export function getTrackObjectName(track: Track) {
  return track.class_name ?? "Not returned";
}

export function getEventId(event: RiskEvent, index: number) {
  return String(event.id ?? event.event_id ?? `${event.timestamp ?? "event"}-${event.track_id ?? index}`);
}

export function getEventSeverity(event: RiskEvent) {
  return event.severity ?? event.level ?? event.risk_level ?? "info";
}

export function getEventObject(event: RiskEvent) {
  return event.object_type ?? event.object_class ?? event.class_name ?? "Not returned";
}

export function getEventRiskScore(event: RiskEvent) {
  return event.risk_score ?? event.edge_risk_score;
}

export function getEventTitle(event: RiskEvent) {
  return event.title ?? event.description ?? event.reason ?? "Risk event";
}

export function getEventExplanation(event: RiskEvent) {
  return event.explanation ?? event.reason ?? event.description;
}

export function getEventFactors(event: RiskEvent) {
  if (event.reason_codes?.length) return event.reason_codes;
  if (event.triggers?.length) return event.triggers;
  if (event.factors?.length) {
    return event.factors.map((factor) => (typeof factor === "string" ? factor : JSON.stringify(factor)));
  }
  return [];
}

export function riskDistributionData(statistics?: StatisticsResponse) {
  const record = statistics as (StatisticsResponse & { risk_distribution?: Record<string, number> }) | undefined;
  const distribution = statistics?.risk?.distribution ?? record?.risk_distribution;
  if (!distribution) return [];

  return Object.entries(distribution).map(([level, count]) => ({
    level,
    count
  }));
}

export function alertsBySeverityData(statistics?: StatisticsResponse) {
  const record = statistics as (StatisticsResponse & { alerts_by_severity?: Record<string, number> }) | undefined;
  const source = statistics?.alerts_by_severity ?? record?.alerts_by_severity;
  if (!source) return [];

  return Object.entries(source).map(([severity, count]) => ({
    severity,
    count
  }));
}

export function detectionsOverTimeData(statistics?: StatisticsResponse) {
  const record = statistics as (StatisticsResponse & { detections_over_time?: NonNullable<StatisticsResponse["detections_over_time"]> }) | undefined;
  return (statistics?.detections_over_time ?? record?.detections_over_time ?? []).map((point) => ({
    time: String(point.time ?? point.timestamp ?? ""),
    detections: point.detections ?? point.count ?? 0,
    alerts: point.alerts ?? 0
  }));
}

export function crowdDensityTrendData(statistics?: StatisticsResponse) {
  const record = statistics as (StatisticsResponse & { crowd_density_trend?: NonNullable<StatisticsResponse["crowd_density_trend"]> }) | undefined;
  const source = statistics?.crowd_density_trend ?? record?.crowd_density_trend ?? statistics?.crowd?.density_trend ?? [];

  return source.map((point) => ({
    time: String(point.time ?? point.timestamp ?? ""),
    density: point.density ?? point.value ?? point.count ?? 0
  }));
}

export function getCrowdMetric(statistics: StatisticsResponse | undefined, key: "person_count" | "vehicle_count" | "max_density") {
  const record = statistics as (StatisticsResponse & Record<string, unknown>) | undefined;
  return statistics?.crowd?.[key] ?? record?.[key];
}

export function getCrowdDetected(statistics: StatisticsResponse | undefined) {
  const record = statistics as (StatisticsResponse & Record<string, unknown>) | undefined;
  return statistics?.crowd?.crowd_detected ?? record?.crowd_detected;
}
