import { z } from "zod";

import { appConfig } from "@/lib/config";

/**
 * The Intelligence page deliberately consumes one contract. Keeping the
 * schema next to the client prevents widgets from inventing values when an
 * endpoint is unavailable or returns a partial payload.
 */
export const availabilitySchema = z.enum([
  "live",
  "stale",
  "degraded",
  "offline",
  "unavailable"
]);

export type Availability = z.infer<typeof availabilitySchema>;

export const freshnessSchema = z
  .object({
    observedAt: z.string().min(1),
    expiresAt: z.string().min(1).optional().nullable(),
    status: availabilitySchema,
    reason: z.string().min(1).optional().nullable()
  })
  .passthrough();

export type Freshness = z.infer<typeof freshnessSchema>;

export const evidenceRefSchema = z
  .object({
    kind: z.enum(["event", "alert", "track", "detection", "recording", "statistics", "health"]),
    id: z.string().min(1),
    cameraId: z.string().min(1).optional().nullable(),
    occurredAt: z.string().min(1).optional().nullable(),
    recordingId: z.string().min(1).optional().nullable(),
    frameTimestamp: z.string().min(1).optional().nullable(),
    label: z.string().min(1),
    serverValidated: z.boolean().optional().default(false),
    validatedAt: z.string().min(1).optional().nullable()
  })
  .passthrough();

export type EvidenceRef = z.infer<typeof evidenceRefSchema>;

export const healthCheckSchema = z
  .object({
    name: z.enum(["api", "database", "redis", "pipeline", "model", "event_stream", "persistence"]),
    status: availabilitySchema,
    observedAt: z.string().min(1),
    detail: z.string().min(1).optional().nullable()
  })
  .passthrough();

export type IntelligenceHealthCheck = z.infer<typeof healthCheckSchema>;

const sourceCountSchema = z.number().int().nonnegative().nullable().optional();

export const intelligenceContextSchema = z
  .object({
    schemaVersion: z.literal("1.0"),
    contextId: z.string().min(1),
    generatedAt: z.string().min(1),
    refreshAfterSeconds: z.number().int().positive(),
    overall: z
      .object({
        status: availabilitySchema,
        degradedReasons: z.array(z.string().min(1)),
        checks: z.array(healthCheckSchema)
      })
      .passthrough(),
    cameras: z
      .object({
        totalConfigured: sourceCountSchema,
        // `total` supports the initial runtime implementation while the
        // contract settles on `totalConfigured`.
        total: sourceCountSchema,
        online: sourceCountSchema,
        offline: sourceCountSchema,
        stale: sourceCountSchema,
        unavailable: sourceCountSchema,
        items: z.array(
          z
            .object({
              cameraId: z.string().min(1),
              name: z.string().min(1).optional().nullable(),
              runtime: availabilitySchema,
              lastFrameAt: z.string().min(1).optional().nullable(),
              freshness: freshnessSchema
            })
            .passthrough()
        ),
        freshness: freshnessSchema
      })
      .passthrough(),
    alerts: z
      .object({
        activeCount: sourceCountSchema,
        items: z.array(
          z
            .object({
              alertId: z.string().min(1),
              level: z.string().min(1).nullable(),
              acknowledged: z.boolean().nullable(),
              evidence: z.array(evidenceRefSchema),
              freshness: freshnessSchema
            })
            .passthrough()
        ),
        freshness: freshnessSchema
      })
      .passthrough(),
    incidents: z
      .object({
        capability: availabilitySchema,
        reason: z.string().min(1).optional().nullable(),
        activeCount: sourceCountSchema
      })
      .passthrough(),
    events: z.array(
      z
        .object({
          eventId: z.string().min(1),
          riskScore: z.number().nullable().optional(),
          riskLevel: z.string().min(1).nullable().optional(),
          summary: z.string().min(1),
          evidence: z.array(evidenceRefSchema),
          freshness: freshnessSchema
        })
        .passthrough()
    ),
    tracks: z.array(
      z
        .object({
          trackId: z.string().min(1),
          cameraId: z.string().min(1).optional().nullable(),
          className: z.string().min(1),
          riskScore: z.number().nullable().optional(),
          verificationStatus: z.string().min(1).optional().nullable(),
          evidence: z.array(evidenceRefSchema),
          freshness: freshnessSchema
        })
        .passthrough()
    ),
    detections: z
      .object({
        recentCount: sourceCountSchema,
        freshness: freshnessSchema
      })
      .passthrough(),
    semantic: z
      .object({
        capability: availabilitySchema,
        mode: z.literal("live_evidence").optional().nullable(),
        reason: z.string().min(1).optional().nullable(),
        activeQuery: z.string().min(1).optional().nullable(),
        evidence: z.array(evidenceRefSchema),
        freshness: freshnessSchema
      })
      .passthrough(),
    pipeline: z
      .object({
        running: z.boolean().nullable().optional(),
        stages: z.array(
          z
            .object({
              name: z.string().min(1),
              status: availabilitySchema,
              observedAt: z.string().min(1),
              detail: z.string().min(1).optional().nullable()
            })
            .passthrough()
        ),
        freshness: freshnessSchema
      })
      .passthrough(),
    ai: z
      .object({
        chat: availabilitySchema,
        providerConfigured: z.boolean().nullable(),
        evidenceGrounding: availabilitySchema,
        reason: z.string().min(1).optional().nullable(),
        voice: z
          .object({
            pushToTalk: availabilitySchema,
            handsFree: availabilitySchema,
            reason: z.string().min(1).optional().nullable()
          })
          .passthrough()
      })
      .passthrough(),
    suggestions: z.array(
      z
        .object({
          suggestionId: z.string().min(1),
          label: z.string().min(1),
          reason: z.string().min(1),
          evidence: z.array(evidenceRefSchema).min(1),
          availability: availabilitySchema,
          href: z.string().min(1).optional().nullable()
        })
        .passthrough()
    )
  })
  .passthrough();

export type IntelligenceContext = z.infer<typeof intelligenceContextSchema>;

export type IntelligenceContextErrorKind =
  | "offline"
  | "unauthorized"
  | "unavailable"
  | "invalid_contract"
  | "unknown";

export class IntelligenceContextError extends Error {
  constructor(
    message: string,
    readonly kind: IntelligenceContextErrorKind,
    readonly status?: number
  ) {
    super(message);
    this.name = "IntelligenceContextError";
  }
}

function responseError(response: Response): IntelligenceContextError {
  if (response.status === 401 || response.status === 403) {
    return new IntelligenceContextError("The intelligence context is not authorised for this session.", "unauthorized", response.status);
  }

  if (response.status === 404 || response.status === 405 || response.status === 501) {
    return new IntelligenceContextError("The intelligence context endpoint is unavailable.", "unavailable", response.status);
  }

  if (response.status === 502 || response.status === 503 || response.status === 504) {
    return new IntelligenceContextError("The dashboard could not reach the intelligence backend.", "offline", response.status);
  }

  return new IntelligenceContextError(`The intelligence context request failed (HTTP ${response.status}).`, "unknown", response.status);
}

export async function fetchIntelligenceContext(signal?: AbortSignal): Promise<IntelligenceContext> {
  let response: Response;

  try {
    response = await fetch(`${appConfig.apiUrl}/api/intelligence/context`, {
      headers: { Accept: "application/json" },
      cache: "no-store",
      signal
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new IntelligenceContextError("The dashboard could not reach the intelligence backend.", "offline");
  }

  if (!response.ok) throw responseError(response);

  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new IntelligenceContextError("The intelligence context returned invalid JSON.", "invalid_contract", response.status);
  }

  const parsed = intelligenceContextSchema.safeParse(payload);
  if (!parsed.success) {
    throw new IntelligenceContextError("The intelligence context response does not match schema version 1.0.", "invalid_contract", response.status);
  }

  return parsed.data;
}

export function isContextStale(context: IntelligenceContext, now = Date.now()) {
  const generatedAt = Date.parse(context.generatedAt);
  if (!Number.isFinite(generatedAt)) return true;
  return now - generatedAt > context.refreshAfterSeconds * 1000;
}

export function availabilityLabel(status: Availability) {
  return status.charAt(0).toUpperCase() + status.slice(1);
}

export function formatFreshness(timestamp?: string | null, now = Date.now()) {
  if (!timestamp) return "Timestamp unavailable";

  const observedAt = Date.parse(timestamp);
  if (!Number.isFinite(observedAt)) return "Timestamp unavailable";

  const seconds = Math.max(0, Math.floor((now - observedAt) / 1000));
  if (seconds < 5) return "Updated just now";
  if (seconds < 60) return `Updated ${seconds} seconds ago`;

  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `Updated ${minutes} minute${minutes === 1 ? "" : "s"} ago`;

  const hours = Math.floor(minutes / 60);
  return `Updated ${hours} hour${hours === 1 ? "" : "s"} ago`;
}
