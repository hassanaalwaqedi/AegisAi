import type { Camera, RiskEvent, StatisticsResponse } from "@/types";

export type AnalyticsCoverageStatus = "available" | "missing" | "degraded" | "unknown";

export type AnalyticsCoverageItem = {
  label: string;
  status: AnalyticsCoverageStatus;
  detail: string;
};

export type CameraRiskRow = {
  cameraId: string;
  cameraName: string;
  runtimeStatus: Camera["runtime"]["status"] | null;
  recentAlertCount: number;
  recentEventCount: number;
  highestRisk: string | null;
  lastEventTime: string | number | null;
};

export function analyticsCoverage(
  statistics: StatisticsResponse | undefined,
  options: { camerasAvailable: boolean; evidenceAvailable: boolean; evidenceDegraded: boolean },
): AnalyticsCoverageItem[] {
  if (!statistics) {
    return [
      { label: "Severity distribution", status: "unknown", detail: "Analytics unavailable" },
      { label: "Risk distribution", status: "unknown", detail: "Analytics unavailable" },
      { label: "Detection counts", status: "unknown", detail: "Analytics unavailable" },
      { label: "Time series", status: "unknown", detail: "Analytics unavailable" },
      { label: "Camera ranking", status: "unknown", detail: "Analytics unavailable" },
      { label: "Crowd trend", status: "unknown", detail: "Analytics unavailable" },
      { label: "Evidence metrics", status: options.evidenceDegraded ? "degraded" : "unknown", detail: options.evidenceDegraded ? "Evidence information unavailable" : "Not available yet" },
    ];
  }

  const events = statistics.latest_detection_events ?? [];
  return [
    { label: "Severity distribution", status: statistics.alerts_by_severity ? "available" : "missing", detail: statistics.alerts_by_severity ? "Available" : "Unavailable" },
    { label: "Risk distribution", status: statistics.risk?.distribution ? "available" : "missing", detail: statistics.risk?.distribution ? "Available" : "Unavailable" },
    { label: "Detection counts", status: statistics.detections ? "available" : "missing", detail: statistics.detections ? "Available" : "Unavailable" },
    { label: "Time series", status: statistics.detections_over_time?.length ? "available" : "missing", detail: statistics.detections_over_time?.length ? "Timeline available" : "No timeline data yet" },
    { label: "Camera ranking", status: events.some((event) => Boolean(event.camera_id)) && options.camerasAvailable ? "available" : options.camerasAvailable ? "missing" : "degraded", detail: !options.camerasAvailable ? "Camera status unavailable" : events.some((event) => Boolean(event.camera_id)) ? "Recent activity available" : "No camera-linked activity yet" },
    { label: "Crowd trend", status: (statistics.crowd_density_trend?.length || statistics.crowd?.density_trend?.length) ? "available" : "missing", detail: (statistics.crowd_density_trend?.length || statistics.crowd?.density_trend?.length) ? "Timeline available" : "No trend data yet" },
    { label: "Evidence metrics", status: options.evidenceDegraded ? "degraded" : options.evidenceAvailable ? "available" : "missing", detail: options.evidenceDegraded ? "Evidence information unavailable" : options.evidenceAvailable ? "Evidence available" : "Unavailable" },
  ];
}

export function cameraRiskRanking(events: RiskEvent[], cameras: Camera[]): CameraRiskRow[] {
  const rows = new Map<string, CameraRiskRow>();

  for (const event of events) {
    const cameraId = event.camera_id;
    if (!cameraId) continue;
    const existing = rows.get(cameraId);
    const camera = cameras.find((item) => item.camera_id === cameraId);
    const eventType = String(event.event_type ?? event.type ?? "").toLowerCase();
    const risk = normalizeRisk(event.risk_level ?? event.severity ?? event.level);
    const next: CameraRiskRow = existing ?? {
      cameraId,
      cameraName: camera?.name ?? cameraId,
      runtimeStatus: camera?.runtime.status ?? null,
      recentAlertCount: 0,
      recentEventCount: 0,
      highestRisk: null,
      lastEventTime: null,
    };
    next.recentEventCount += 1;
    if (eventType === "risk_alert") next.recentAlertCount += 1;
    if (risk && riskRank(risk) > riskRank(next.highestRisk)) next.highestRisk = risk;
    if (isNewer(event.timestamp, next.lastEventTime)) next.lastEventTime = event.timestamp ?? null;
    rows.set(cameraId, next);
  }

  return Array.from(rows.values()).sort((left, right) => {
    const riskDelta = riskRank(right.highestRisk) - riskRank(left.highestRisk);
    if (riskDelta) return riskDelta;
    const alertDelta = right.recentAlertCount - left.recentAlertCount;
    if (alertDelta) return alertDelta;
    return timestampValue(right.lastEventTime) - timestampValue(left.lastEventTime);
  });
}

export function eventTypeBreakdown(statistics: StatisticsResponse | undefined) {
  return Object.entries(statistics?.events_by_type ?? {}).map(([eventType, count]) => ({
    eventType,
    label: readableEventType(eventType),
    count,
  })).sort((left, right) => right.count - left.count);
}

export function readableEventType(eventType: string) {
  const normalized = eventType.trim().toLowerCase();
  if (normalized.includes("assault")) return "Possible assault";
  if (normalized.includes("restricted")) return "Restricted zone";
  if (normalized.includes("crowd")) return "Crowding";
  if (normalized.includes("weapon")) return "Weapon-like object";
  if (!normalized || normalized === "event") return "Unknown / other";
  return normalized.replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function normalizeRisk(value?: string) {
  const normalized = value?.toUpperCase();
  return normalized === "CANDIDATE_MEDIUM" ? "MEDIUM" : normalized && ["LOW", "MEDIUM", "HIGH", "CRITICAL"].includes(normalized) ? normalized : null;
}

function riskRank(level: string | null) {
  if (level === "CRITICAL") return 4;
  if (level === "HIGH") return 3;
  if (level === "MEDIUM") return 2;
  if (level === "LOW") return 1;
  return 0;
}

function isNewer(next: string | number | undefined, previous: string | number | null) {
  return timestampValue(next) > timestampValue(previous);
}

function timestampValue(value: string | number | null | undefined) {
  if (typeof value === "number") return value > 10_000_000_000 ? value : value * 1_000;
  if (typeof value === "string") {
    const parsed = Date.parse(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
}
