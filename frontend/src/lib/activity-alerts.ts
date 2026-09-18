import type { Camera, OperationalAlert, RiskEvent } from "@/types";

export type ActivityFilter = "all" | "review" | "high" | "resolved" | "camera";
export type ActivityStatus = "high" | "attention" | "monitoring" | "resolved" | "offline" | "delayed" | "unavailable";

export type ActivityAlertItem = {
  id: string;
  status: ActivityStatus;
  priority: number;
  camera?: Camera;
  cameraLabel: string;
  location?: string;
  event?: RiskEvent;
  summary: string;
  occurredAt?: string | number;
  relatedEvents: RiskEvent[];
};

const resolvedValues = new Set(["resolved", "closed", "acknowledged"]);
const vehicleClasses = new Set(["vehicle", "car", "bus", "truck", "motorcycle", "bicycle"]);

export function cameraDisplayName(camera?: Camera, cameraId?: string) {
  const name = camera?.name?.trim();
  if (name && !["http stream", "rtsp stream", "local device", "browser webcam", "uploaded video"].includes(name.toLowerCase())) return name;
  const reference = camera?.camera_id ?? cameraId;
  if (!reference) return "Camera unavailable";
  const cleanReference = reference
    .replace(/^(?:http|rtsp)[-_]?stream[-_]?/i, "")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/[-_]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .split(" ")
    .map((part) => part ? `${part[0]?.toUpperCase()}${part.slice(1)}` : part)
    .join(" ");
  return cleanReference ? `Camera ${cleanReference}` : "Camera unavailable";
}

export function cameraCondition(camera?: Camera): "live" | "offline" | "delayed" | "unavailable" {
  if (!camera) return "unavailable";
  if (["offline", "error", "stopped"].includes(camera.runtime.status)) return "offline";
  if (["connecting", "reconnecting"].includes(camera.runtime.status)) return "delayed";
  if (camera.runtime.status === "online" && camera.runtime.running) return "live";
  return "unavailable";
}

export function eventTimestamp(event?: RiskEvent) {
  if (!event?.timestamp) return 0;
  return typeof event.timestamp === "number" ? event.timestamp * 1_000 : Date.parse(event.timestamp) || 0;
}

/** Convert a durable alert into the existing evidence-view event shape.
 *
 * The dashboard and activity workspace retain their visual presentation, but
 * review work now begins with persisted alerts instead of inferred per-frame
 * risk observations.  The event ID remains the evidence ID for deep links.
 */
export function operationalAlertToEvent(alert: OperationalAlert): RiskEvent {
  return {
    id: alert.alert_id,
    event_id: alert.event_id,
    alert_id: alert.alert_id,
    incident_id: alert.incident_id ?? undefined,
    timestamp: alert.timestamp ?? undefined,
    risk_level: alert.risk_level.toUpperCase() as RiskEvent["risk_level"],
    risk_score: alert.risk_score ?? undefined,
    track_id: alert.track_id ?? undefined,
    camera_id: alert.camera_id ?? undefined,
    zone: alert.zone,
    description: alert.message,
    explanation: alert.message,
    reason: alert.message,
    factors: alert.factors,
    snapshot_path: alert.snapshot_path ?? undefined,
    snapshot_status: alert.evidence_status,
    verification_status: alert.acknowledged ? "acknowledged" : "confirmed",
  };
}

function eventStatus(event: RiskEvent): ActivityStatus {
  const verification = String(event.verification_status ?? "").trim().toLowerCase();
  if (resolvedValues.has(verification)) return "resolved";
  const level = String(event.risk_level ?? event.severity ?? event.level ?? "").toUpperCase();
  if (["CRITICAL", "HIGH"].includes(level)) return "high";
  if (["CANDIDATE_MEDIUM", "MEDIUM", "WARNING"].includes(level)) return "attention";
  return "monitoring";
}

function eventPriority(status: ActivityStatus) {
  if (status === "high") return 5;
  if (status === "offline") return 4;
  if (status === "attention" || status === "delayed") return 3;
  if (status === "unavailable") return 2;
  if (status === "monitoring") return 1;
  return 0;
}

export function eventObjectLabel(event: RiskEvent) {
  const value = String(event.object_class ?? event.object_type ?? event.class_name ?? "").trim().toLowerCase();
  if (value === "person") return "Person";
  if (vehicleClasses.has(value)) return "Vehicle";
  if (["weapon", "knife", "pistol"].includes(value)) return "Potential weapon";
  return "Activity";
}

function eventSummary(event: RiskEvent, status: ActivityStatus) {
  if (status === "high") return eventObjectLabel(event) === "Activity" ? "High-priority activity needs review" : `${eventObjectLabel(event)} activity needs review`;
  if (status === "attention") return `${eventObjectLabel(event)} activity needs review`;
  if (status === "resolved") return "Reviewed activity";
  return `${eventObjectLabel(event)} activity reported`;
}

function chooseItem(current: ActivityAlertItem | undefined, next: ActivityAlertItem) {
  if (!current) return next;
  if (next.priority !== current.priority) return next.priority > current.priority ? next : current;
  return eventTimestamp(next.event) > eventTimestamp(current.event) ? next : current;
}

/** Build concise review work from returned event records and runtime camera state. */
export function buildActivityAlertItems(cameras: Camera[], events: RiskEvent[], alerts?: OperationalAlert[]) {
  const cameraById = new Map(cameras.map((camera) => [camera.camera_id, camera]));
  const relatedByCamera = new Map<string, RiskEvent[]>();
  // When the durable alert endpoint has answered, it is the only source for
  // operator review status.  Runtime events remain linked as timeline
  // evidence but cannot create a fake review item on their own.
  const reviewEvents = alerts === undefined ? events : alerts.map(operationalAlertToEvent);
  for (const event of reviewEvents) {
    if (!event.camera_id) continue;
    relatedByCamera.set(event.camera_id, [...(relatedByCamera.get(event.camera_id) ?? []), event]);
  }

  const items = new Map<string, ActivityAlertItem>();
  for (const event of events) {
    const status = eventStatus(event);
    // Normal per-frame detections are not review work. They remain available
    // in the camera timeline but do not flood this operator queue.
    if (status === "monitoring") continue;
    const camera = event.camera_id ? cameraById.get(event.camera_id) : undefined;
    const key = `event:${event.camera_id ?? event.event_id ?? event.id ?? eventTimestamp(event)}`;
    const item: ActivityAlertItem = {
      id: key,
      status,
      priority: eventPriority(status),
      camera,
      cameraLabel: cameraDisplayName(camera, event.camera_id),
      location: camera?.location?.trim() || event.zone?.trim() || undefined,
      event,
      summary: eventSummary(event, status),
      occurredAt: event.timestamp,
      relatedEvents: event.camera_id ? relatedByCamera.get(event.camera_id) ?? [] : [event],
    };
    items.set(key, chooseItem(items.get(key), item));
  }

  for (const camera of cameras) {
    const condition = cameraCondition(camera);
    if (condition !== "offline" && condition !== "delayed") continue;
    const status: ActivityStatus = condition;
    const item: ActivityAlertItem = {
      id: `camera:${camera.camera_id}:${status}`,
      status,
      priority: eventPriority(status),
      camera,
      cameraLabel: cameraDisplayName(camera),
      location: camera.location?.trim() || undefined,
      summary: status === "offline" ? "Camera offline" : "Live image is delayed",
      occurredAt: camera.runtime.last_frame_time ?? undefined,
      relatedEvents: relatedByCamera.get(camera.camera_id) ?? [],
    };
    items.set(item.id, item);
  }

  return Array.from(items.values()).sort((left, right) => right.priority - left.priority || eventTimestamp(right.event) - eventTimestamp(left.event));
}

export function filterActivityAlertItems(items: ActivityAlertItem[], filter: ActivityFilter, search: string) {
  const query = search.trim().toLowerCase();
  return items.filter((item) => {
    const filterMatches = filter === "all"
      || (filter === "review" && ["high", "attention"].includes(item.status))
      || (filter === "high" && item.status === "high")
      || (filter === "resolved" && item.status === "resolved")
      || (filter === "camera" && ["offline", "delayed", "unavailable"].includes(item.status));
    if (!filterMatches) return false;
    if (!query) return true;
    return [item.cameraLabel, item.location, item.summary]
      .filter(Boolean)
      .some((value) => value!.toLowerCase().includes(query));
  });
}

export function activitySummary(items: ActivityAlertItem[]) {
  const review = items.filter((item) => ["high", "attention", "offline", "delayed"].includes(item.status)).length;
  const high = items.filter((item) => item.status === "high").length;
  const resolved = items.filter((item) => item.status === "resolved").length;
  return { review, high, resolved };
}

export function isNewActivity(timestamp?: string | number, now = Date.now()) {
  const value = typeof timestamp === "number" ? timestamp * 1_000 : typeof timestamp === "string" ? Date.parse(timestamp) : Number.NaN;
  return Number.isFinite(value) && value <= now && now - value <= 5 * 60 * 1_000;
}

export function activityStatusLabel(status: ActivityStatus) {
  if (status === "high") return "High priority";
  if (status === "attention") return "Needs attention";
  if (status === "resolved") return "Resolved";
  if (status === "offline") return "Camera offline";
  if (status === "delayed") return "Live image delayed";
  if (status === "monitoring") return "Monitoring";
  return "Information unavailable";
}

export const activityAlertsInternals = {
  activityStatusLabel,
  buildActivityAlertItems,
  cameraCondition,
  cameraDisplayName,
  eventObjectLabel,
  eventTimestamp,
  filterActivityAlertItems,
  isNewActivity,
  operationalAlertToEvent,
};
