import { z } from "zod";

export const riskLevelSchema = z.enum(["LOW", "CANDIDATE_MEDIUM", "MEDIUM", "HIGH", "CRITICAL"]);

export const severitySchema = z.enum([
  "LOW",
  "CANDIDATE_MEDIUM",
  "MEDIUM",
  "HIGH",
  "CRITICAL",
  "low",
  "medium",
  "high",
  "critical",
  "info",
  "warning"
]);

const idSchema = z.union([z.string(), z.number()]);
const numericRecordSchema = z.record(z.string(), z.number());
const bboxSchema = z.tuple([z.number(), z.number(), z.number(), z.number()]);

export const statusSystemSchema = z
  .object({
    running: z.boolean().optional(),
    uptime_seconds: z.number().optional(),
    frames_processed: z.number().optional(),
    current_fps: z.number().optional(),
    fps: z.number().optional(),
    active_tracks: z.number().optional(),
    total_detections: z.number().optional(),
    total_alerts: z.number().optional(),
    total_anomalies: z.number().optional(),
    high_risk_count: z.number().optional(),
    max_risk_level: riskLevelSchema.optional(),
    max_risk_score: z.number().optional(),
    semantic_enabled: z.boolean().optional(),
    model_name: z.string().optional(),
    supported_classes: z.array(z.string()).optional(),
    weapon_detection_supported: z.boolean().optional(),
    action_recognition_supported: z.boolean().optional(),
    pose_estimation_supported: z.boolean().optional(),
    semantic_verification_supported: z.boolean().optional(),
    camera_id: z.string().optional(),
    camera_status: z.string().optional(),
    source: z.string().optional(),
    source_status: z.string().optional()
  })
  .passthrough();

export const statusResponseSchema = z
  .object({
    status: z.string().optional(),
    version: z.string().optional(),
    timestamp: z.string().optional(),
    system: statusSystemSchema.optional(),
    performance: statusSystemSchema.optional(),
    counts: statusSystemSchema.optional()
  })
  .passthrough();

export const trackSchema = z
  .object({
    track_id: idSchema,
    class_name: z.string().optional(),
    class_id: z.number().optional(),
    object_category: z.string().optional(),
    is_person: z.boolean().optional(),
    is_vehicle: z.boolean().optional(),
    is_weapon: z.boolean().optional(),
    confidence: z.number().optional(),
    bbox: bboxSchema.optional(),
    first_seen: z.string().nullable().optional(),
    duration_seconds: z.number().optional(),
    total_seen_count: z.number().optional(),
    confidence_history: z.array(z.number()).optional(),
    risk_level: riskLevelSchema.optional(),
    risk_score: z.number().optional(),
    zone: z.string().optional(),
    behaviors: z.array(z.string()).optional(),
    behavior_labels: z.array(z.string()).optional(),
    detected_classes: z.array(z.string()).optional(),
    risk_explanation: z.string().optional(),
    risk_factors: z.array(z.string()).optional(),
    evidence_type: z.string().optional(),
    model_source: z.array(z.string()).optional(),
    verification_status: z.string().optional(),
    reason_codes: z.array(z.string()).optional(),
    visual_evidence: z.record(z.string(), z.unknown()).optional(),
    weapon_class: z.string().nullable().optional(),
    weapon_confidence: z.number().nullable().optional(),
    person_track_id: idSchema.nullable().optional(),
    weapon_track_id: idSchema.nullable().optional(),
    association_type: z.string().nullable().optional(),
    association_score: z.number().nullable().optional(),
    stable_frames: z.number().optional(),
    evidence_objects: z.array(z.record(z.string(), z.unknown())).optional(),
    behavior: z.string().optional(),
    movement_state: z.string().optional(),
    time_tracked: z.number().optional(),
    frame_id: z.number().optional(),
    frame_number: z.number().optional(),
    last_seen: z.string().optional(),
    last_updated: z.string().optional()
  })
  .passthrough();

export const tracksResponseSchema = z
  .object({
    count: z.number(),
    tracks: z.array(trackSchema)
  })
  .passthrough();

export const eventSchema = z
  .object({
    id: idSchema.optional(),
    event_id: idSchema.optional(),
    type: z.string().optional(),
    event_type: z.string().optional(),
    timestamp: z.union([z.string(), z.number()]).optional(),
    severity: severitySchema.optional(),
    level: severitySchema.optional(),
    risk_level: riskLevelSchema.optional(),
    object_type: z.string().optional(),
    object_class: z.string().optional(),
    class_name: z.string().optional(),
    track_id: idSchema.optional(),
    risk_score: z.number().optional(),
    edge_risk_score: z.number().optional(),
    title: z.string().optional(),
    description: z.string().optional(),
    explanation: z.string().optional(),
    reason: z.string().optional(),
    factors: z.array(z.union([z.string(), z.record(z.string(), z.unknown())])).optional(),
    triggers: z.array(z.string()).optional(),
    evidence_type: z.string().optional(),
    confidence: z.number().optional(),
    model_source: z.array(z.string()).optional(),
    verification_status: z.string().optional(),
    reason_codes: z.array(z.string()).optional(),
    visual_evidence: z.record(z.string(), z.unknown()).optional(),
    weapon_class: z.string().nullable().optional(),
    weapon_confidence: z.number().nullable().optional(),
    person_track_id: idSchema.nullable().optional(),
    weapon_track_id: idSchema.nullable().optional(),
    association_type: z.string().nullable().optional(),
    association_score: z.number().nullable().optional(),
    stable_frames: z.number().optional(),
    evidence_objects: z.array(z.record(z.string(), z.unknown())).optional(),
    detected_objects: z.array(z.string()).optional(),
    detected_classes: z.array(z.string()).optional(),
    behavior_labels: z.array(z.string()).optional(),
    frame_number: z.number().optional(),
    snapshot_path: z.string().nullable().optional(),
    snapshot_status: z.string().optional(),
    snapshot_url: z.string().nullable().optional(),
    incident_id: z.string().nullable().optional(),
    alert_id: z.string().nullable().optional(),
    zone: z.string().optional(),
    camera_id: z.string().optional()
  })
  .passthrough();

export const eventsResponseSchema = z
  .object({
    count: z.number(),
    events: z.array(eventSchema)
  })
  .passthrough();

export const operationalAlertSchema = z
  .object({
    alert_id: z.string(),
    event_id: z.string(),
    track_id: z.string().nullable().optional(),
    camera_id: z.string().nullable().optional(),
    camera_name: z.string().nullable().optional(),
    incident_id: z.string().nullable().optional(),
    evidence_id: z.string().nullable().optional(),
    evidence_status: z.string().optional(),
    snapshot_path: z.string().nullable().optional(),
    bounding_box: z.array(z.number()).nullable().optional(),
    risk_level: severitySchema,
    risk_score: z.number().nullable().optional(),
    message: z.string(),
    zone: z.string().optional(),
    factors: z.array(z.union([z.string(), z.record(z.string(), z.unknown())])).optional(),
    timestamp: z.string().nullable().optional(),
    acknowledged: z.boolean(),
    acknowledged_at: z.string().nullable().optional(),
    acknowledged_by: z.string().nullable().optional(),
    delivery_status: z.string().optional(),
    delivery_attempts: z.number().optional()
  })
  .passthrough();

export const alertsResponseSchema = z.array(operationalAlertSchema);

export const alertCountResponseSchema = z.object({
  total: z.number().int().nonnegative(),
  active: z.number().int().nonnegative(),
  by_level: numericRecordSchema
}).passthrough();

export const evidenceRecordSchema = eventSchema.extend({
  snapshot_available: z.boolean().optional(),
  snapshot_url: z.string().nullable().optional()
}).passthrough();

export const persistedEvidenceResponseSchema = z.object({
  count: z.number(),
  evidence: z.array(evidenceRecordSchema)
}).passthrough();

export const incidentSchema = z.object({
  incident_id: z.string(),
  camera_id: z.string(),
  primary_track_id: z.string().nullable().optional(),
  related_track_ids: z.array(z.string()).optional(),
  current_risk_level: severitySchema.optional(),
  max_risk_score: z.number().nullable().optional(),
  status: z.string(),
  event_ids: z.array(z.string()).optional(),
  alert_ids: z.array(z.string()).optional(),
  evidence_ids: z.array(z.string()).optional(),
  summary_reason: z.string().nullable().optional(),
  contributing_factors: z.array(z.union([z.string(), z.record(z.string(), z.unknown())])).optional(),
  start_time: z.string().nullable().optional(),
  last_seen_time: z.string().nullable().optional()
}).passthrough();

export const incidentsResponseSchema = z.object({
  count: z.number(),
  incidents: z.array(incidentSchema)
}).passthrough();

const timeSeriesPointSchema = z
  .object({
    time: z.union([z.string(), z.number()]).optional(),
    timestamp: z.union([z.string(), z.number()]).optional(),
    detections: z.number().optional(),
    count: z.number().optional(),
    alerts: z.number().optional(),
    density: z.number().optional(),
    value: z.number().optional()
  })
  .passthrough();

const analyticsModelSchema = z
  .object({
    model_name: z.string().optional(),
    supported_classes: z.array(z.string()).optional(),
    weapon_detection_supported: z.boolean().optional(),
    action_recognition_supported: z.boolean().optional(),
    pose_estimation_supported: z.boolean().optional(),
    semantic_verification_supported: z.boolean().optional()
  })
  .passthrough();

export const statisticsResponseSchema = z
  .object({
    crowd: z
      .object({
        person_count: z.number().optional(),
        vehicle_count: z.number().optional(),
        weapon_count: z.number().optional(),
        crowd_detected: z.boolean().optional(),
        max_density: z.number().optional(),
        average_density: z.number().optional(),
        density_trend: z.array(timeSeriesPointSchema).optional()
      })
      .passthrough()
      .optional(),
    detections: z
      .object({
        active_count: z.number().optional(),
        people_count: z.number().optional(),
        vehicles_count: z.number().optional(),
        weapons_count: z.number().optional(),
        by_class: numericRecordSchema.optional(),
        object_registry_count: z.number().optional(),
        weapon_associations_count: z.number().optional(),
        critical_associations_count: z.number().optional()
      })
      .passthrough()
      .optional(),
    risk: z
      .object({
        distribution: numericRecordSchema.optional(),
        max_level: riskLevelSchema.optional(),
        max_score: z.number().optional()
      })
      .passthrough()
      .optional(),
    processing: z
      .object({
        frames: z.number().optional(),
        fps: z.number().optional(),
        active_tracks: z.number().optional()
      })
      .passthrough()
      .optional(),
    detections_over_time: z.array(timeSeriesPointSchema).optional(),
    alerts_by_severity: numericRecordSchema.optional(),
    crowd_density_trend: z.array(timeSeriesPointSchema).optional(),
    events_by_type: numericRecordSchema.optional(),
    latest_detection_events: z.array(eventSchema).optional(),
    model: analyticsModelSchema.optional()
  })
  .passthrough();

export const semanticQueryRequestSchema = z.object({
  prompt: z.string().min(3).max(500),
  priority: z.number().min(0).max(100).optional(),
  ttl_seconds: z.number().min(1).optional()
});

export const semanticQueryResponseSchema = z
  .object({
    success: z.boolean(),
    prompt_id: z.string(),
    message: z.string(),
    active_prompts: z.number(),
    matches: z.number().optional(),
    execution_ms: z.number().optional(),
    evidence_storage: z.enum(["available", "unavailable"]).optional(),
    reason: z.string().nullable().optional()
  })
  .passthrough();

export const semanticResultSchema = z
  .object({
    track_id: idSchema,
    source: z.enum(["track", "event", "statistics"]).optional(),
    base_class: z.string(),
    semantic_label: z.string().nullable().optional(),
    semantic_confidence: z.number().nullable().optional(),
    risk_score: z.number(),
    matched_phrase: z.string().nullable().optional(),
    behaviors: z.array(z.string()),
    camera_id: z.string().nullable().optional(),
    zone: z.string().nullable().optional(),
    confidence: z.number().nullable().optional(),
    verification_status: z.string().nullable().optional(),
    timestamp: z.string().nullable().optional(),
    evidence: z.array(z.string()).optional()
  })
  .passthrough();

export const semanticResultsResponseSchema = z
  .object({
    total_tracks: z.number(),
    semantic_matches: z.number(),
    results: z.array(semanticResultSchema),
    mode: z.enum(["live_evidence", "disabled"]).optional(),
    query: z.string().nullable().optional(),
    evaluated_tracks: z.number().optional(),
    evaluated_events: z.number().optional(),
    execution_ms: z.number().optional(),
    updated_at: z.string().nullable().optional(),
    evidence_storage: z.enum(["available", "unavailable"]).optional(),
    reason: z.string().nullable().optional()
  })
  .passthrough();

const evidenceRiskLevelSchema = z.enum(["LOW", "CANDIDATE_MEDIUM", "MEDIUM", "HIGH", "CRITICAL"]);

export const evidenceSearchItemSchema = z.object({
  event_id: z.string(),
  alert_id: z.string().nullable().optional(),
  incident_id: z.string().nullable().optional(),
  camera_id: z.string().nullable().optional(),
  camera_name: z.string().nullable().optional(),
  event_type: z.string().nullable().optional(),
  timestamp: z.string().nullable().optional(),
  object_class: z.string().nullable().optional(),
  risk_level: z.string().nullable().optional(),
  risk_score: z.number().nullable().optional(),
  track_id: z.union([z.string(), z.number()]).nullable().optional(),
  zone: z.string().nullable().optional(),
  zone_name: z.string().nullable().optional(),
  reason: z.string().nullable().optional(),
  detection_confidence: z.number().nullable().optional(),
  detectors: z.array(z.string()).default([]),
  snapshot_available: z.boolean(),
  similarity: z.number().optional()
});

export const evidenceSearchRequestSchema = z.object({
  query: z.string().max(500).default(""),
  similar_to: z.string().max(128).nullable().optional(),
  camera_id: z.string().max(80).nullable().optional(),
  event_type: z.string().max(50).nullable().optional(),
  risk_level: evidenceRiskLevelSchema.nullable().optional(),
  start: z.string().datetime().nullable().optional(),
  end: z.string().datetime().nullable().optional(),
  min_confidence: z.number().min(0).max(1).default(0),
  min_similarity: z.number().min(-1).max(1).default(0.25),
  sort: z.enum(["relevance", "newest", "oldest", "risk", "confidence"]).default("relevance"),
  page: z.number().int().min(1).default(1),
  page_size: z.number().int().min(1).max(50).default(6)
});

export const evidenceSearchResponseSchema = z.object({
  results: z.array(evidenceSearchItemSchema), total: z.number().int().nonnegative(), page: z.number().int(),
  page_size: z.number().int(), sort: z.enum(["relevance", "newest", "oldest", "risk", "confidence"]), has_next: z.boolean(), has_previous: z.boolean(), as_of: z.string(),
  pending_evidence: z.number().int().nonnegative(), execution_ms: z.number()
});

export const evidenceSearchStatusSchema = z.object({
  total_evidence: z.number().int().nonnegative(), indexed_evidence: z.number().int().nonnegative(),
  pending_evidence: z.number().int().nonnegative(), last_sync: z.string().nullable(),
  event_types: z.array(z.string()), state: z.enum(["ready", "indexing", "offline"]), model: z.string(),
  similarity: z.literal("cosine"), representation: z.literal("stored_event_text")
});

export const evidenceSearchDetailSchema = z.object({
  evidence: evidenceSearchItemSchema, related: z.array(evidenceSearchItemSchema)
});

export const cameraSourceTypeSchema = z.enum([
  "LOCAL_DEVICE",
  "RTSP_STREAM",
  "HTTP_STREAM",
  "BROWSER_WEBCAM",
  "UPLOADED_VIDEO"
]);

export const cameraConnectionStatusSchema = z.enum([
  "online",
  "offline",
  "connecting",
  "reconnecting",
  "error",
  "stopped",
  "failed",
  "unverified",
  "disabled"
]);

export const cameraRuntimeStatusSchema = z
  .object({
    camera_id: z.string(),
    status: cameraConnectionStatusSchema,
    source_type: cameraSourceTypeSchema,
    error_message: z.string().nullable().optional(),
    frames_received: z.number().optional(),
    frames_dropped: z.number().optional(),
    reconnect_count: z.number().optional(),
    fps: z.number().optional(),
    width: z.number().nullable().optional(),
    height: z.number().nullable().optional(),
    last_frame_time: z.string().nullable().optional(),
    connected_since: z.string().nullable().optional(),
    running: z.boolean().optional()
  })
  .passthrough();

export const cameraSchema = z
  .object({
    camera_id: z.string(),
    source_type: cameraSourceTypeSchema,
    name: z.string().nullable().optional(),
    location: z.string().nullable().optional(),
    enabled: z.boolean(),
    url: z.string().nullable().optional(),
    device_index: z.number().nullable().optional(),
    video_id: z.string().nullable().optional(),
    connection_timeout: z.number().optional(),
    max_retries: z.number().optional(),
    auto_start: z.boolean().optional(),
    verification_status: z.enum(["verified", "unverified", "failed"]).optional(),
    last_connection_test: z.record(z.string(), z.unknown()).optional(),
    metadata: z.record(z.string(), z.unknown()).optional(),
    created_at: z.string().optional(),
    updated_at: z.string().optional(),
    runtime: cameraRuntimeStatusSchema
  })
  .passthrough();

export const camerasResponseSchema = z
  .object({
    count: z.number(),
    cameras: z.array(cameraSchema)
  })
  .passthrough();

export const cameraConnectionTestResponseSchema = z
  .object({
    ok: z.boolean(),
    status: cameraConnectionStatusSchema,
    error_message: z.string().nullable().optional(),
    error_category: z.string().nullable().optional(),
    dns_resolved: z.boolean().nullable().optional(),
    host_reachable: z.boolean().nullable().optional(),
    time_to_first_frame_ms: z.number().nullable().optional(),
    width: z.number().nullable().optional(),
    height: z.number().nullable().optional(),
    masked_url: z.string().nullable().optional(),
    snapshot_data_url: z.string().nullable().optional(),
    test_id: z.string().optional()
  })
  .passthrough();

export const cameraEventsResponseSchema = z
  .object({
    count: z.number(),
    events: z.array(eventSchema)
  })
  .passthrough();

export const cameraDetectionsResponseSchema = z
  .object({
    count: z.number(),
    detections: z.array(trackSchema)
  })
  .passthrough();

export const cameraZoneOverlaySchema = z
  .object({
    zone_id: z.string(),
    name: z.string(),
    type: z.string(),
    bounds: z.tuple([z.number(), z.number(), z.number(), z.number()]),
    description: z.string().optional(),
    active: z.boolean().optional()
  })
  .passthrough();

export const cameraHeatmapCellSchema = z
  .object({
    x: z.number(),
    y: z.number(),
    width: z.number(),
    height: z.number(),
    count: z.number(),
    intensity: z.number()
  })
  .passthrough();

export const cameraOverlayResponseSchema = z
  .object({
    camera_id: z.string(),
    frame_width: z.number().nullable().optional(),
    frame_height: z.number().nullable().optional(),
    zones: z.array(cameraZoneOverlaySchema),
    heatmap: z.array(cameraHeatmapCellSchema),
    heatmap_samples: z.number(),
    generated_at: z.string()
  })
  .passthrough();

export const browserFrameResponseSchema = z
  .object({
    camera_id: z.string(),
    frame_id: z.number(),
    timestamp: z.string(),
    detections: z.array(trackSchema),
    risk: z
      .object({
        risk_score: z.number(),
        risk_level: riskLevelSchema,
        triggers: z.array(z.string()).optional(),
        should_escalate: z.boolean().optional()
      })
      .passthrough(),
    event: eventSchema.nullable().optional()
  })
  .passthrough();

export const videoUploadResponseSchema = z
  .object({
    video_id: z.string(),
    filename: z.string(),
    content_type: z.string().nullable().optional(),
    size_bytes: z.number(),
    uploaded_at: z.string()
  })
  .passthrough();

export const cameraWebSocketMessageSchema = z
  .object({
    type: z.string(),
    camera_id: z.string().optional(),
    status: cameraConnectionStatusSchema.optional(),
    error_message: z.string().nullable().optional(),
    message: z.string().optional(),
    timestamp: z.string().optional(),
    frame: z.string().optional(),
    detections: z.array(trackSchema).optional(),
    events: z.array(eventSchema).optional()
  })
  .passthrough();

export const websocketMessageSchema = z
  .object({
    type: z.string().optional(),
    timestamp: z.string().optional(),
    status: statusSystemSchema.optional(),
    tracks: z.array(trackSchema).optional(),
    events: z.array(eventSchema).optional(),
    statistics: statisticsResponseSchema.optional(),
    event: eventSchema.optional(),
    alert: eventSchema.optional()
  })
  .passthrough();
