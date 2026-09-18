import { z } from "zod";

import { appConfig } from "@/lib/config";

const persistedEvidenceSchema = z.object({
  event_id: z.string().min(1),
  alert_id: z.string().nullable().optional(),
  camera_id: z.string().nullable().optional(),
  camera_name: z.string().nullable().optional(),
  object_class: z.string().nullable().optional(),
  risk_level: z.string().nullable().optional(),
  risk_score: z.number().nullable().optional(),
  timestamp: z.string().nullable().optional(),
  reason: z.string().nullable().optional(),
  message: z.string().nullable().optional(),
  snapshot_available: z.boolean().optional().default(false),
  snapshot_url: z.string().nullable().optional(),
}).passthrough();

const persistedEvidenceResponseSchema = z.object({
  count: z.number().int().nonnegative(),
  evidence: z.array(persistedEvidenceSchema),
});

const incidentSchema = z.object({
  incident_id: z.string().min(1),
  camera_id: z.string().nullable().optional(),
  primary_track_id: z.string().nullable().optional(),
  zone_id: z.string().nullable().optional(),
  zone_name: z.string().nullable().optional(),
  last_seen_time: z.string().nullable().optional(),
  current_risk_level: z.string().nullable().optional(),
  max_risk_score: z.number().nullable().optional(),
  status: z.enum(["active", "resolved"]),
  evidence_ids: z.array(z.string()).default([]),
  summary_reason: z.string().nullable().optional(),
}).passthrough();

const activeIncidentsResponseSchema = z.object({
  count: z.number().int().nonnegative(),
  incidents: z.array(incidentSchema),
});

export type PersistedEvidence = z.infer<typeof persistedEvidenceSchema>;
export type PersistedIncident = z.infer<typeof incidentSchema>;

export async function fetchRecentPersistedEvidence(signal?: AbortSignal): Promise<PersistedEvidence[]> {
  let response: Response;
  try {
    response = await fetch(`${appConfig.apiUrl}/events/persisted?limit=8`, {
      cache: "no-store",
      headers: { Accept: "application/json" },
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new Error("Persisted evidence is unavailable.");
  }

  if (!response.ok) throw new Error("Persisted evidence is unavailable.");
  const payload = persistedEvidenceResponseSchema.safeParse(await response.json());
  if (!payload.success) throw new Error("Persisted evidence response is invalid.");
  return payload.data.evidence;
}

export async function fetchActiveIncidents(signal?: AbortSignal): Promise<PersistedIncident[]> {
  let response: Response;
  try {
    response = await fetch(`${appConfig.apiUrl}/events/incidents?limit=6`, {
      cache: "no-store",
      headers: { Accept: "application/json" },
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new Error("Active incidents are unavailable.");
  }

  if (!response.ok) throw new Error("Active incidents are unavailable.");
  const payload = activeIncidentsResponseSchema.safeParse(await response.json());
  if (!payload.success) throw new Error("Active incident response is invalid.");
  return payload.data.incidents;
}

export function persistedEvidenceSnapshotUrl(evidence: PersistedEvidence): string | null {
  return evidence.snapshot_available && evidence.snapshot_url
    ? `${appConfig.apiUrl}${evidence.snapshot_url}`
    : null;
}
