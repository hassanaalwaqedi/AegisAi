import { z } from "zod";

import { appConfig } from "@/lib/config";
import { availabilitySchema } from "@/lib/intelligence-context";
import { operatorExecutionSchema } from "@/lib/operator-api";

export const voiceStateSchema = z.enum([
  "off",
  "connecting",
  "ready",
  "listening",
  "thinking",
  "speaking",
  "error"
]);

export type VoiceState = z.infer<typeof voiceStateSchema>;

/** Frontend-only presentation state; the backend never needs to emit it. */
export const aegisVoiceCoreStateSchema = z.union([voiceStateSchema, z.literal("degraded")]);

export type AegisVoiceCoreState = z.infer<typeof aegisVoiceCoreStateSchema>;

const citationSchema = z.object({
  evidenceId: z.string().min(1),
  kind: z.enum(["camera", "event", "alert", "track", "detection", "recording", "statistics", "health"]),
  label: z.string().min(1),
  cameraId: z.string().min(1).optional().nullable(),
  observedAt: z.string().min(1).optional().nullable(),
  availability: availabilitySchema
});

export type LiveCitation = z.infer<typeof citationSchema>;

export const safeUiCommandSchema = z.object({
  kind: z.enum([
    "open_cameras",
    "show_track_evidence",
    "open_semantic_evidence",
    "show_risk_evidence",
    "focus_health"
  ]),
  targetId: z.string().min(1).optional().nullable(),
  cameraId: z.string().min(1).optional().nullable()
}).strict();

export type SafeUICommand = z.infer<typeof safeUiCommandSchema>;

export const liveCapabilitiesSchema = z.object({
  availability: availabilitySchema,
  reason: z.string().min(1).optional().nullable(),
  nativeAudio: z.boolean(),
  inputTranscription: z.boolean(),
  outputTranscription: z.boolean(),
  inputSampleRate: z.number().int().min(8000).max(48000).optional().nullable(),
  outputSampleRate: z.number().int().min(8000).max(48000).optional().nullable(),
  pushToTalk: availabilitySchema,
  websocketProtocol: z.literal("aegis-live-v1")
});

export type LiveCapabilities = z.infer<typeof liveCapabilitiesSchema>;

export const liveSessionSchema = z.object({
  sessionId: z.string().min(1),
  connectionToken: z.string().min(16),
  expiresAt: z.string().min(1),
  correlationId: z.string().min(1),
  capabilities: liveCapabilitiesSchema
});

export type LiveSession = z.infer<typeof liveSessionSchema>;

export const serverVoiceEnvelopeSchema = z.object({
  version: z.literal("1.0"),
  type: z.enum(["session_ready", "state", "transcript", "citations", "ui_command", "tool_activity", "turn_complete", "interrupted", "error", "pong", "projection"]),
  projection: operatorExecutionSchema.optional().nullable(),
  state: voiceStateSchema.optional(),
  sessionId: z.string().min(1).optional(),
  inputSampleRate: z.number().int().min(8000).max(48000).optional(),
  outputSampleRate: z.number().int().min(8000).max(48000).optional(),
  speaker: z.enum(["operator", "aegis"]).optional(),
  text: z.string().min(1).optional(),
  isFinal: z.boolean().optional(),
  turnId: z.string().min(1).optional().nullable(),
  citations: z.array(citationSchema).optional(),
  uiCommand: safeUiCommandSchema.optional(),
  tool: z.string().min(1).optional(),
  toolStatus: z.enum(["calling", "completed", "failed"]).optional(),
  code: z.string().min(1).optional(),
  message: z.string().min(1).optional(),
  recoverable: z.boolean().optional(),
  correlationId: z.string().min(1).optional()
});

export type ServerVoiceEnvelope = z.infer<typeof serverVoiceEnvelopeSchema>;

export class LiveVoiceError extends Error {
  constructor(message: string, readonly status?: number) {
    super(message);
    this.name = "LiveVoiceError";
  }
}

async function parseResponse<T>(response: Response, schema: z.ZodType<T>): Promise<T> {
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new LiveVoiceError("The voice gateway returned invalid JSON.", response.status);
  }
  const parsed = schema.safeParse(payload);
  if (!parsed.success) throw new LiveVoiceError("The voice gateway returned an invalid contract.", response.status);
  return parsed.data;
}

async function responseMessage(response: Response) {
  try {
    const payload = await response.json();
    if (typeof payload?.detail === "string") return payload.detail;
  } catch {
    // A status-specific message is clearer than a JSON parsing exception.
  }
  return `The voice gateway request failed (HTTP ${response.status}).`;
}

export async function fetchLiveCapabilities(signal?: AbortSignal): Promise<LiveCapabilities> {
  let response: Response;
  try {
    response = await fetch(`${appConfig.apiUrl}/api/intelligence/live/capabilities`, { cache: "no-store", signal });
  } catch {
    throw new LiveVoiceError("The voice gateway is offline.");
  }
  if (!response.ok) throw new LiveVoiceError(await responseMessage(response), response.status);
  return parseResponse(response, liveCapabilitiesSchema);
}

export async function createLiveSession(
  options: { audibleAlertId?: string; signal?: AbortSignal } = {},
): Promise<LiveSession> {
  let response: Response;
  try {
    response = await fetch(`${appConfig.apiUrl}/api/intelligence/live/sessions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(options.audibleAlertId ? { audibleAlertId: options.audibleAlertId } : {}),
      cache: "no-store",
      signal: options.signal
    });
  } catch {
    throw new LiveVoiceError("The voice gateway is offline.");
  }
  if (!response.ok) throw new LiveVoiceError(await responseMessage(response), response.status);
  return parseResponse(response, liveSessionSchema);
}

export async function closeLiveSession(sessionId: string) {
  try {
    await fetch(`${appConfig.apiUrl}/api/intelligence/live/sessions/${encodeURIComponent(sessionId)}`, {
      method: "DELETE",
      cache: "no-store"
    });
  } catch {
    // Local cleanup must never leave microphone capture active because a
    // network teardown failed. The short-lived server token still expires.
  }
}

function liveWebSocketBase() {
  const configured = process.env.NEXT_PUBLIC_AEGIS_LIVE_WS_URL || process.env.NEXT_PUBLIC_WS_URL;
  if (configured) return configured;
  if (typeof window === "undefined") return "";

  const url = new URL(window.location.origin);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  // Local Next development can choose any available port (for example 3001
  // when 3000 is occupied), while FastAPI serves the Live gateway on 8080.
  // Deployed environments must configure NEXT_PUBLIC_AEGIS_LIVE_WS_URL.
  if (["localhost", "127.0.0.1", "[::1]"].includes(url.hostname) && url.port !== "8080") {
    url.port = "8080";
  }
  return url.toString();
}

export function liveWebSocketUrl(sessionId: string) {
  const base = liveWebSocketBase();
  if (!base) throw new LiveVoiceError("No public WebSocket endpoint is configured for Gemini Live.");
  const url = new URL(base);
  url.pathname = `/ws/intelligence/live/${encodeURIComponent(sessionId)}`;
  url.search = "";
  return url.toString();
}

export function browserVoiceEnvelope(type: "audio" | "text" | "audio_end" | "interrupt" | "stop" | "ping", data?: string, mimeType?: string) {
  return JSON.stringify({ version: "1.0", type, ...(data ? { data } : {}), ...(mimeType ? { mimeType } : {}) });
}
