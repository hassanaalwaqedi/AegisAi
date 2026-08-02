import type { Camera, Track } from "@/types";

export type TrackingFilter = "all" | "people" | "vehicles" | "attention";
export type TrackingCategory = "person" | "vehicle" | "other";
export type CameraPreviewState = "live" | "delayed" | "offline" | "unavailable";
export type TrackingMovement = "moving" | "stationary" | "stopped" | "unavailable";

export type TrackingTimelineEntry = {
  label: string;
  timestamp: string;
};

export type LiveTrackingItem = {
  id: string;
  track: Track;
  category: TrackingCategory;
  label: "Person" | "Vehicle" | "Tracked object";
  movement: TrackingMovement;
  movementLabel: string;
  needsAttention: boolean;
  riskLabel: string | null;
  cameraId: string | null;
  camera: Camera | null;
  cameraLabel: string;
  location: string | null;
  cameraPreviewState: CameraPreviewState;
  firstSeen: string | null;
  lastSeen: string | null;
  timeline: TrackingTimelineEntry[];
};

const vehicleClasses = new Set(["car", "truck", "bus", "motorcycle", "bicycle", "van", "vehicle"]);
const personClasses = new Set(["person", "people", "human", "pedestrian"]);
const attentionLevels = new Set(["CANDIDATE_MEDIUM", "MEDIUM", "HIGH", "CRITICAL"]);

export function buildLiveTrackingItems(tracks: Track[], cameras: Camera[]): LiveTrackingItem[] {
  const camerasById = new Map(cameras.map((camera) => [camera.camera_id, camera]));

  return tracks.map((track) => {
    const cameraId = stringField(track, "camera_id");
    const camera = cameraId ? camerasById.get(cameraId) ?? null : null;
    const category = trackCategory(track);
    const firstSeen = timestampField(track.first_seen);
    const lastSeen = timestampField(track.last_seen) ?? timestampField(track.last_updated);

    return {
      id: String(track.track_id),
      track,
      category,
      label: category === "person" ? "Person" : category === "vehicle" ? "Vehicle" : "Tracked object",
      movement: movementState(track),
      movementLabel: movementLabel(movementState(track)),
      needsAttention: attentionLevels.has(String(track.risk_level ?? "").toUpperCase()),
      riskLabel: readableRisk(track.risk_level),
      cameraId,
      camera,
      cameraLabel: camera ? cameraDisplayName(camera) : cameraId ? "Camera details unavailable" : "Camera unavailable",
      location: camera?.location?.trim() || null,
      cameraPreviewState: cameraPreviewState(camera),
      firstSeen,
      lastSeen,
      timeline: buildTimeline(firstSeen, lastSeen)
    };
  });
}

export function filterLiveTrackingItems(items: LiveTrackingItem[], filter: TrackingFilter, query: string) {
  const normalizedQuery = query.trim().toLowerCase();

  return items.filter((item) => {
    if (filter === "people" && item.category !== "person") return false;
    if (filter === "vehicles" && item.category !== "vehicle") return false;
    if (filter === "attention" && !item.needsAttention) return false;
    if (!normalizedQuery) return true;

    return [item.label, item.cameraLabel, item.location, item.movementLabel]
      .filter((value): value is string => Boolean(value))
      .some((value) => value.toLowerCase().includes(normalizedQuery));
  });
}

export function liveTrackingSummary(items: LiveTrackingItem[]) {
  return {
    total: items.length,
    people: items.filter((item) => item.category === "person").length,
    vehicles: items.filter((item) => item.category === "vehicle").length,
    attention: items.filter((item) => item.needsAttention).length
  };
}

export function cameraPreviewState(camera: Camera | null | undefined): CameraPreviewState {
  if (!camera) return "unavailable";
  if (!camera.enabled || ["offline", "error", "stopped"].includes(camera.runtime.status)) return "offline";
  if (["connecting", "reconnecting"].includes(camera.runtime.status)) return "delayed";
  if (camera.runtime.status === "online" && camera.runtime.running) return "live";
  if (camera.runtime.status === "online") return "delayed";
  return "unavailable";
}

export function cameraDisplayName(camera: Camera) {
  return camera.name?.trim() || "Registered camera";
}

function trackCategory(track: Track): TrackingCategory {
  const labels = [track.class_name, track.object_category, ...(track.detected_classes ?? [])]
    .filter((value): value is string => Boolean(value))
    .map((value) => value.trim().toLowerCase());

  if (track.is_person || labels.some((label) => personClasses.has(label))) return "person";
  if (track.is_vehicle || labels.some((label) => vehicleClasses.has(label))) return "vehicle";
  return "other";
}

function movementState(track: Track): TrackingMovement {
  const raw = String(track.movement_state ?? track.behavior ?? "").trim().toLowerCase();
  if (raw.includes("moving") || raw.includes("walking") || raw.includes("driving")) return "moving";
  if (raw.includes("stationary") || raw.includes("standing") || raw.includes("idle")) return "stationary";
  if (raw.includes("stopped")) return "stopped";
  return "unavailable";
}

function movementLabel(movement: TrackingMovement) {
  if (movement === "moving") return "Moving";
  if (movement === "stationary") return "Stationary";
  if (movement === "stopped") return "Stopped";
  return "Information unavailable";
}

function readableRisk(value: unknown) {
  const level = String(value ?? "").trim().toUpperCase();
  if (!level || level === "LOW") return null;
  if (level === "CANDIDATE_MEDIUM") return "Needs attention";
  if (level === "MEDIUM") return "Needs attention";
  if (level === "HIGH") return "High priority";
  if (level === "CRITICAL") return "Critical priority";
  return null;
}

function timestampField(value: unknown) {
  if (typeof value !== "string" || !value.trim() || !Number.isFinite(Date.parse(value))) return null;
  return value;
}

function stringField(value: unknown, field: string) {
  const candidate = (value as Record<string, unknown>)[field];
  return typeof candidate === "string" && candidate.trim() ? candidate : null;
}

function buildTimeline(firstSeen: string | null, lastSeen: string | null): TrackingTimelineEntry[] {
  const entries: TrackingTimelineEntry[] = [];
  if (firstSeen) entries.push({ label: "First seen", timestamp: firstSeen });
  if (lastSeen && lastSeen !== firstSeen) entries.push({ label: "Last seen", timestamp: lastSeen });
  return entries;
}

export const liveTrackingInternals = {
  buildLiveTrackingItems,
  filterLiveTrackingItems,
  liveTrackingSummary,
  cameraPreviewState
};
