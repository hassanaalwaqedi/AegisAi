import type { z } from "zod";
import type {
  eventSchema,
  eventsResponseSchema,
  browserFrameResponseSchema,
  cameraConnectionStatusSchema,
  cameraConnectionTestResponseSchema,
  cameraDetectionsResponseSchema,
  cameraEventsResponseSchema,
  cameraRuntimeStatusSchema,
  cameraSchema,
  camerasResponseSchema,
  cameraSourceTypeSchema,
  cameraWebSocketMessageSchema,
  semanticQueryResponseSchema,
  semanticResultsResponseSchema,
  statisticsResponseSchema,
  statusResponseSchema,
  statusSystemSchema,
  trackSchema,
  tracksResponseSchema,
  websocketMessageSchema
} from "@/lib/schemas";

export type RiskLevel = "LOW" | "CANDIDATE_MEDIUM" | "MEDIUM" | "HIGH" | "CRITICAL";
export type CameraSourceType = z.infer<typeof cameraSourceTypeSchema>;
export type CameraConnectionStatus = z.infer<typeof cameraConnectionStatusSchema>;
export type CameraRuntimeStatus = z.infer<typeof cameraRuntimeStatusSchema>;
export type Camera = z.infer<typeof cameraSchema>;
export type CamerasResponse = z.infer<typeof camerasResponseSchema>;
export type CameraConnectionTestResponse = z.infer<typeof cameraConnectionTestResponseSchema>;
export type CameraEventsResponse = z.infer<typeof cameraEventsResponseSchema>;
export type CameraDetectionsResponse = z.infer<typeof cameraDetectionsResponseSchema>;
export type BrowserFrameResponse = z.infer<typeof browserFrameResponseSchema>;
export type CameraWebSocketMessage = z.infer<typeof cameraWebSocketMessageSchema>;
export type StatusSystem = z.infer<typeof statusSystemSchema>;
export type StatusResponse = z.infer<typeof statusResponseSchema>;
export type Track = z.infer<typeof trackSchema>;
export type TracksResponse = z.infer<typeof tracksResponseSchema>;
export type RiskEvent = z.infer<typeof eventSchema>;
export type EventsResponse = z.infer<typeof eventsResponseSchema>;
export type StatisticsResponse = z.infer<typeof statisticsResponseSchema>;
export type SemanticQueryResponse = z.infer<typeof semanticQueryResponseSchema>;
export type SemanticResultsResponse = z.infer<typeof semanticResultsResponseSchema>;
export type WebSocketMessage = z.infer<typeof websocketMessageSchema>;

export type ApiConnectionState = "checking" | "connected" | "degraded" | "unavailable";
export type WebSocketConnectionState = "idle" | "connecting" | "connected" | "reconnecting" | "disconnected" | "error";
