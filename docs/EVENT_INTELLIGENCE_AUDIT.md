# Aegis AI: event-intelligence audit and proposed architecture

Date: 2026-09-16. Scope: Phase 1, audit and design only. Deployment target: Hassan's local PC first.

> Implementation update — after this audit was approved, the first P0 slice
> began. The baseline findings below remain evidence of the pre-change system.
> Current changes add durable `Observation` records before alert handling,
> source epochs for camera-local track identity, bootstrappable Alembic
> migrations, versioned explainable `RiskAssessment` records for incident
> updates, and a conservative rule: stable geometric weapon/person
> containment alone is HIGH (with interaction confirmation required), not
> CRITICAL. The remaining target architecture is not complete yet.

## Executive conclusion

Aegis already has tracking, temporal heuristics, object-person association, persistent evidence, operational alerts, and an incident correlation service. It is not simply a knife detector. However, the primary camera path decides risk and dispatches alerts **before** persistent incident correlation. Incidents currently summarize selected, already-scored events; they are not the authority that determines risk.

Production readiness is **not established**. Highest-priority findings:

1. Strong geometric weapon association can produce HIGH in one analyzed frame; persistent containment alone can produce CRITICAL. Neither establishes violent intent. See `FrameIngestionService._build_evidence` and `WeaponAggressionEngine` below.
2. Alert cooldown suppresses severity escalation and, in the camera path, prevents the suppressed frame from updating durable evidence/incidents. See `AlertManager.process_risk` and `FrameIngestionService._maybe_generate_alert`.
3. Several execution paths implement different risk policies. The Redis pipeline passes process-local objects that its serializer cannot encode. See `aegis/pipeline/*` and `aegis/core/events.py`.
4. Persistence and dispatch are not one durable transaction/outbox. Database/queue failures can leave notifications without durable evidence or lose delivery. See `FrameIngestionService._persist_event`, `_maybe_generate_alert`, and `AlertManager.persist_alert`.
5. Blank-database migrations fail. An isolated in-memory SQLite migration run failed with `no such table: events` in `20260802_02_persistent_evidence.upgrade`.
6. The frontend backend-proxy injects privileged credentials without authenticating its caller. The optional cloud analysis server accepts an API-key header without validating it. Keep these services off untrusted networks pending hardening.

Recommendation: stabilize one local execution path and introduce observation-first correlation with explicit uncertainty. Do not add Kafka, cross-camera re-identification, or additional paid AI services for this phase.

## Audit method and verification limits

Repository-wide file inventory and symbol searches covered backend, camera/CV, tracking, analysis, risk, pipelines, database/migrations, APIs/WebSockets, frontend, recording, semantic/AI services, deployment, and tests. Deep tracing focused on the reachable camera-to-operator paths and their alternatives. This is not a claim that every generated file, dependency, model binary, or historical document was read.

The working tree already contains extensive modifications and untracked implementation files. Findings refer to the current working tree, not a clean release commit. Existing changes were preserved. This report is the only new audit deliverable; no application code or configuration was changed for this audit. Secrets were not inspected.

Verification performed:

- 54 existing focused tests passed, with 83 warnings, in 5.43 seconds. Modules are listed in section 15. Passing these tests establishes current behavior, not that the encoded policy meets the requested safety requirements.
- Isolated, model-free probe: a person and a far-away knife passed repeatedly to `ProximityRiskEngine.assess` produced HIGH, HIGH, HIGH, HIGH, CRITICAL. This is the alternate proximity engine, not proof that the fully gated camera path emits those alerts.
- Isolated alert probe: HIGH followed immediately by CRITICAL with the same cooldown identity created the HIGH alert and suppressed the CRITICAL alert.
- Isolated serialization probe: `aegis.core.events._serialize` rejected a dictionary containing a NumPy frame with `TypeError`.
- `alembic upgrade head` against `sqlite:///:memory:` failed at revision `20260802_02`, attempting to alter a missing `events` table. No saved database was migrated.

Not found / not verified: real-video precision/recall, model calibration, installed weights' accuracy or provenance, sustained GPU/CPU throughput, end-to-end latency distributions, live Redis recovery, PostgreSQL migration execution, deployment penetration testing, full test suite, frontend test execution, browser verification, or production certification. Numeric defaults below are code defaults, not measured installation settings.

## 1. Current architecture

### Main API camera path

```text
Camera source / browser frame / uploaded video
  -> camera.MultiCameraPipelineManager
  -> video.camera_sources.FrameIngestionService.process_frame
  -> MultiModelDetector (base YOLO + optional weapon model)
  -> per-camera ByteTrack
  -> track history / motion / behavior / crowd
  -> base risk + proximity + person-weapon association + aggression heuristics
  -> per-track evidence/verification gates
  -> AlertManager: cooldown and dispatch
  -> snapshot + Event row
  -> IncidentCorrelationService: attach already-scored Event
  -> OperationalAlert persistence (separate transaction)
  -> APIState / events bus / REST and WebSocket snapshots
  -> dashboard polling / camera sockets / operator presentation
```

Ordinary detection events branch into in-memory history without the serious-alert persistence path. Sources: [camera manager](../aegis/camera/manager.py), [FrameIngestionService](../aegis/video/camera_sources.py), [incident correlation](../aegis/intelligence/incident_correlation.py), [alert manager](../aegis/alerts/alert_manager.py).

### Other paths that must not be mistaken for that path

- `aegis/pipeline/startup.py:create_pipeline` constructs threaded Detection, Tracking, RiskScoring, and Alerting stages over `EventBus`. `aegis/api/app.py:create_app` initializes this pipeline. A producer wiring active camera frames to `Streams.FRAMES` was **Not found / not verified**; camera ingestion calls its own service directly. Initializing stage threads does not prove frames traverse them.
- `aegis/api/routes/analyze.py:analyze_frame` uses its own detector/tracker and `ProximityRiskEngine`; its semantics are not the camera evidence policy.
- `aegis/edge/edge_pipeline.py:EdgePipeline.process_frame` uses YOLO, ByteTrack, proximity scoring, and optional cloud escalation.
- `aegis/pipeline/ai_pipeline.py:AICameraPipeline` and `aegis/edge/edge_risk_filter.py:EdgeRiskFilter` provide another edge/cloud route.
- `main.py:run_perception_pipeline` is the CLI perception/analysis/risk route, with optional Grounding DINO semantic execution. It is not evidence that the REST camera path uses DINO.
- `aegis/video/camera_sources.py` still contains an older `MultiCameraPipelineManager`; API routes import the newer manager from `aegis.camera`.

Redis Streams and an in-memory fallback exist in `aegis/core/events.py:EventBus`. Kafka/Celery infrastructure in the inspected execution paths: **Not found / not verified**.

## 2. Exact current event flow

The ordering inside `FrameIngestionService` matters:

1. `process_frame` assigns an analyzed-frame counter and processing timestamp, detects and tracks objects, and computes history and motion.
2. It evaluates risk and association before there is a durable Observation or Incident. `_apply_frame_rules` and `_build_evidence` further override scores, labels, verification status, and explanations.
3. `_maybe_generate_detection_event` deduplicates ordinary detection notifications by camera, track, event type, verification/association state, and risk level. These are runtime records, not a complete durable observation stream.
4. `_maybe_generate_alert` requires HIGH/CRITICAL, permitted reason codes, and confirmation. Normal confirmation requires three high-risk frames; confirmed threat context can reduce this to one.
5. `AlertManager.process_risk` applies cooldown, dispatches, and updates alert history. If suppressed, `_maybe_generate_alert` returns before this frame's serious-event persistence/correlation.
6. The successful alert path builds a generic `risk_alert` event; specialized threat type is separate metadata. It saves a snapshot and calls `_persist_event`.
7. `_persist_event` uses `EventRepository.create_or_get_evidence`, then calls `IncidentCorrelationService.correlate_event` within a nested savepoint. Correlation failure does not have to roll back the evidence row.
8. `AlertManager.persist_alert` runs separately. The finalized event is exposed to runtime state and the events bus. Failures are reported/logged, but a durable retry/outbox was **Not found / not verified**.

Consequences: cooldown controls what becomes lasting incident history; an incident's last-seen time reflects accepted events, not necessarily continued physical presence. The system cannot reliably reconstruct all pre-alert observations after restart.

## 3. Stage-by-stage implementation map

Paths are repository-relative. Every row names the implementation and its communication/persistence boundary.

| Stage and implementation | Input -> output | Communication / persistence | Failure behavior or limit |
| --- | --- | --- | --- |
| `aegis/api/routes/cameras.py:get_camera_manager`; `aegis/camera/manager.py:MultiCameraPipelineManager` | Camera configuration -> registered source | API calls; camera registry JSON, separated credential file | Restoration errors produce unavailable-source state; configuration changes reset analysis state |
| `aegis/camera/base.py:OpenCVLoopCameraSource._capture_loop`; `aegis/camera/sources.py` | USB/RTSP/HTTP/file -> BGR NumPy frame | Capture thread callback; latest full frame and JPEG preview in memory | Open retries back off from 1 to 20 seconds; configured retry limit; five failed live reads trigger reconnect; finite video ends as stopped |
| `MultiCameraPipelineManager._handle_frame` | Frame -> inference task | ThreadPoolExecutor, configured 1-4 workers, default 1 | Per-camera busy flag and 0.2-second submission interval skip frames; skips are not all counted as capture drops |
| `ingest_browser_frame`; `aegis/camera/utils.py:decode_base64_frame` | Base64 image -> frame -> ingestion result | Synchronous call from browser-frame route | Decode errors rejected; no decoded-pixel cap found; this path bypasses the executor and can block its async request handler |
| `aegis/detection/multi_model_detector.py:MultiModelDetector.detect`; `yolo_detector.py:YOLODetector`; `weapon_detector.py:WeaponDetector` | Frame -> `Detection` objects: xyxy bbox, class, confidence, source, flags | Direct model calls; no detection table | Base-model load/inference failures propagate to caller; optional weapon model can disable itself and return no detections |
| `aegis/tracking/bytetrack_tracker.py:ByteTrackTracker` | Detections -> tracks with IDs and detection attributes | Per-camera in-process tracker | Empty frames advance tracker; reset loses identity; no durable identity epoch |
| `aegis/analysis/track_history.py:TrackHistoryManager`; `motion_analyzer.py`; behavior/crowd analyzers | Tracks -> trajectory, displacement, behavior, density | In-memory history | Sample/frame-rate dependent; history bounded and stale tracks removed; no persistent observation trajectory found |
| `aegis/risk/risk_engine.py:RiskEngine.compute_risk`; association/aggression engines; `FrameIngestionService._build_evidence` | Track analyses -> scores, reasons, association, confirmation | Direct calls, per-camera memory | Multiple override layers; missing model signals are not positive evidence; confidence and geometry can nevertheless escalate severity |
| `FrameIngestionService._maybe_generate_detection_event` | Verified/candidate track state -> detection event dictionary | Runtime deque and `APIState` | Lifetime dedup set grows until reset; low-level history is lost on restart |
| `aegis/alerts/alert_manager.py:AlertManager.process_risk` | Track risk + cooldown key -> Alert or None | Console/file/API queue; in-memory history, persisted cooldown lookup | Queue capacity 100 by default; suppression precedes incident update; no escalation bypass; no durable delivery retry worker found |
| `FrameIngestionService._persist_event`; `aegis/database/repositories.py:EventRepository` | Event dictionary + image -> `Event` row / snapshot | Filesystem JPEG plus SQLAlchemy transaction | Snapshot and database can fail independently; no atomic file/database transaction or durable recovery protocol |
| `aegis/intelligence/incident_correlation.py:IncidentCorrelationService.correlate_event` | Existing Event -> new/updated Incident | SQLAlchemy, same-camera candidate lookup | Best-effort attachment; matching can be coarse; no scheduled expiration worker found |
| `aegis/api/routes/events.py`, `alerts.py`; `aegis/api/state.py:APIState` | Stored/runtime objects -> API JSON | REST; runtime event deque max 100 | Some endpoints fall back to runtime data after database errors; not equivalent to durable history |
| `aegis/api/websocket.py`; camera routes' WebSocket handlers | Runtime snapshots/previews -> JSON/JPEG messages | WebSocket, handshake authentication | Reconnection does not use a durable resume cursor; finite runtime history can omit outage events |
| `frontend/src/hooks/use-aegis-api.ts`; `components/dashboard/operator-dashboard.tsx`; `components/events/activity-alerts-workspace.tsx` | REST data -> operator UI | Primarily polling; camera preview/events sockets separately | Client schema drift and event/alert mixing affect presentation; successful rendering is not delivery acknowledgment |

## 4. Already implemented

- Real detection contracts with model-source metadata and optional weapon-model capability reporting: `aegis/detection/yolo_detector.py:Detection`, `WeaponDetector`, `MultiModelDetector`.
- Per-camera tracking, histories, velocity/direction-like features and geometric object association: `ByteTrackTracker`, `TrackHistoryManager`, `MotionAnalyzer`, `PersonWeaponAssociationEngine`.
- Temporal/pair confirmation and explanations: `aegis/risk/weapon_aggression.py:WeaponAggressionEngine`, `FrameIngestionService._build_evidence`.
- Persistent event/evidence records, incidents, operational alerts, lifecycle updates and audits: `aegis/database/models.py:Event`, `Incident`, `OperationalAlert`; `IncidentCorrelationService`; `aegis/audit/service.py:record_audit`.
- Snapshot serving with a resolved-path containment check: `aegis/api/routes/events.py` snapshot endpoint.
- Shared-key API enforcement, short-lived WebSocket credentials and readiness checks: `aegis/api/security.py:verify_api_key`, `aegis/api/routes/health.py`.

These are reusable foundations, not reasons to create a second competing incident subsystem.

## 5. Partially implemented

- Correlation already groups events, but is downstream of risk/alerts and consumes selected events rather than observations: `IncidentCorrelationService.correlate_event`.
- Evidence includes snapshot, bounding box, timestamps, metadata, factors and explanation on serious events. `FrameIngestionService._maybe_generate_alert` sets `clip_path=None`; model outputs are selected metadata, not an immutable, complete inference record.
- `aegis/recording/risk_recorder.py:RiskRecorder` has a five-second nominal pre-buffer, risk-triggered recording, MP4 output and JSON metadata. `MultiCameraRecorder` exists. Integration from the active camera/incident path was **Not found / not verified**; class presence does not mean incident clips are being recorded.
- `aegis/semantic/query_engine.py:SemanticQueryEngine` implements keyword/concept matching over live tracks/events, not general semantic search across stored video. `main.py:run_perception_pipeline` separately supports optional DINO. `aegis/fusion/risk_fusion.py:RiskFusionEngine` has CLIP/SAM/depth/action execution stubs returning no result, not operational multimodal validation.
- Operator lifecycle persistence exists in `IncidentRepository.set_lifecycle_status`; a complete confirm/escalate/note workflow with authenticated operator identity and matching dashboard controls was **Not found / not verified**.
- Observability modules and API health exist (`aegis/video/metrics.py`, `aegis/api/routes/metrics.py`, `aegis/intelligence/observability/telemetry.py`); complete timestamp-linked camera-to-operator latency accounting was **Not found / not verified**.

## 6. Missing foundations and concept separation

| Concept | Required meaning | Current representation and conflation |
| --- | --- | --- |
| Detection | One model's claim about one frame | `Detection` exists and is distinct at inference time |
| Observation | Measured, timestamped evidence about an entity/relationship | Track dictionaries and histories carry fragments; dedicated durable Observation entity **Not found / not verified** |
| Event | Temporally supported assertion derived from observations | Runtime detection events and durable generic `risk_alert` rows share the event vocabulary |
| Incident | Stateful hypothesis linking events and participants | `Incident` exists, but summarizes previously scored events and their peak severity |
| Evidence | Independently identified provenance/artifact | `Event` contains artifact fields; incident `evidence_ids` and `event_ids` receive the same event IDs |
| RiskAssessment | Versioned reasoning about an incident | Scores/factors are embedded in events/incidents; independent append-only assessment entity **Not found / not verified** |
| Alert | A delivery/review decision about an assessment transition | `OperationalAlert` is separate, but the camera path uses the alert's identifier for the event/evidence chain and dispatches first |

Sources: `aegis/database/models.py:Event/Incident/OperationalAlert`, `IncidentCorrelationService`, `FrameIngestionService._maybe_generate_alert`. Explicit participants with role/confidence, versioned domain envelopes, immutable assessment history, durable delivery outbox and cross-camera identity mapping: **Not found / not verified** in these paths.

## 7. Critical architectural problems

### Different paths mean different safety policy

`aegis/pipeline/risk_scoring.py:RiskScoringStage` marks a sufficiently confident unassociated weapon MEDIUM/concerning; `AlertingStage.process` can emit `risk_alert` events for concerning results even when an operational alert is not dispatched. Persistence accepts HIGH/CRITICAL or score >=0.7; `_trigger_alert` dispatches only CRITICAL or score >=0.85. Ordinary base-risk events without a threat event type do not share the specialized threat cooldown and can generate per-frame event IDs. Camera ingestion uses different gates. These differences undermine one consistent incident definition.

### Redis does not currently make the stages durable

`DetectionStage.process` consumes/produces `_frame` as a NumPy array. `TrackingStage.process` passes raw track-analysis/history objects, and `RiskScoringStage` also carries process-local objects. `aegis/core/events.py:_serialize` uses MessagePack without serializers for those objects. The in-memory mode can conceal this boundary problem.

`EventBus` uses consumer-group reads for new messages, but pending-message reclaim, durable replay and a disk spool were **Not found / not verified**. The fallback deque is bounded at 10,000 and pops on read before successful processing. Publish/read failures do not implement a consistent reconnect-and-reconcile protocol. Subclass stage methods can catch a processing error and return no outputs, after which `PipelineStage._loop` acknowledges the input. Safety-critical delivery is therefore not guaranteed.

### Dispatch precedes durable authority

`AlertManager.process_risk` dispatches before `FrameIngestionService` stores Event/Incident and then OperationalAlert. A failure can create an apparent alert with incomplete lasting evidence. Conversely, dispatch success recorded on queue insertion is not receipt by an operator. A transactional outbox and explicit delivery states are needed.

## 8. False-positive and false-negative risks

- `WeaponAggressionEngine` can confirm a weapon association in one frame when weapon confidence >=0.90, association score >=0.80 and overlap/containment is present. Existing test `test_one_strong_high_confidence_weapon_association_can_confirm_high_risk` requires this. High detection confidence establishes neither intent nor interaction.
- `FrameIngestionService._build_evidence` can label persistent overlap/containment CRITICAL without aggressive behavior. This is especially risky for cooking, work tools, sporting equipment, occlusion and adjacent silhouettes.
- `ProximityRiskEngine.assess` creates pairs for person/weapon co-presence, even far apart; five stable samples can produce CRITICAL. Comments call 0.5 MEDIUM and 0.85 HIGH, but `_score_to_level` returns HIGH and CRITICAL respectively.
- Motion features use image coordinates. Camera shake, zoom, perspective and variable analyzed FPS can look like running or approach. `MotionAnalyzer`, `_motion_behavior_confirmed` and `WeaponAggressionEngine` do not establish metric distance or a learned fight classification.
- `PersonWeaponAssociationEngine` chooses a best geometric person. It is not proof of carrying, holding, aiming or ownership. Multiple overlapping people can make the chosen identity ambiguous.
- Temporal protections exist, but high-confidence bypasses, short frame-count thresholds, tracker-ID churn and different execution paths weaken them. `AlertManager` cooldown can also suppress a genuine escalation.
- `_build_evidence` resets ordinary person/vehicle risk and overwrites explanations, then merges other contexts. This can remove or misrepresent base zone/crowd reasoning. Rule composition needs explicit tests rather than assuming higher layers preserve prior factors.

## 9. Data model and migration problems

`aegis/database/models.py` currently provides:

- `Event`: unique nullable external event ID, camera/track keys, score/level, factors, bounding box, snapshot/clip fields and metadata. Incident ID is a string link, not a complete normalized provenance graph.
- `Incident`: one `camera_id`, primary/related track IDs, zone, start/last-seen, risk/peak score, processing/lifecycle states and JSON arrays of event/alert/evidence IDs.
- `OperationalAlert`: durable alert/event links, risk, cooldown, acknowledgment and delivery fields. The older `Alert` model also remains; it is not the primary camera operational-alert persistence path.
- `TrackStats`: integer track ID primary key without camera/session namespace. `aegis/database/repository.py` contains aggregate save/get methods; active ingestion of full persistent track histories was **Not found / not verified**.

Problems: identity collisions across resets; JSON relationship arrays without strong referential guarantees; evidence/event identity conflation; no independent assessment versions; one-camera incident assumption; current versus peak severity ambiguity; and unrestricted lifecycle transitions in `IncidentRepository.set_lifecycle_status`.

Schema management is split between `aegis/database/connection.py:create_tables`, `init.sql`, and Alembic. The first migration creates knowledge tables, while `20260802_02_persistent_evidence.py:upgrade` assumes `events` already exists. The isolated blank-database failure confirms that Alembic alone cannot bootstrap that database. `create_all` is not an upgrade mechanism for existing tables. A safe adoption/baseline procedure for existing installations is needed before adding domain tables. The deprecated `aegis/db` package explicitly points to `aegis.database`; it should not become a new write path.

## 10. Current correlation coverage and gaps

| Relationship | Current implementation | Limitation |
| --- | --- | --- |
| Across frames / detections to tracks | `ByteTrackTracker` | Camera-local IDs; no reset epoch or guaranteed identity continuity |
| Object to person | `PersonWeaponAssociationEngine` | Geometry and persistence, not hand/pose ownership |
| Person to person | `WeaponAggressionEngine` | Nearest-target proximity/approach heuristic; not validated fight recognition |
| Multiple event types/history | `IncidentCorrelationService.correlate_event` | Matches already-scored events; generic `risk_alert` often hides event taxonomy |
| Same camera/time/entity/zone | Same service | Default 3-minute candidate window, latest 50 same-camera active candidates; exact primary/related track or zone with nearby severity |
| Evidence/risk | Same service + `IncidentRepository` | Appends existing IDs/factors; severity/score preserve maximum, not a new contextual assessment |
| Cross-camera | Incident has one camera scalar | Cross-camera event correlation or ReID **Not found / not verified** |

Zone-only matching can merge unrelated situations. There is no general spatial-distance/event-compatibility model in incident matching. Default idle expiration is five minutes, invoked by correlation and an intelligence-context read path (`aegis/intelligence/context_service.py`), not by a verified scheduler. Under-review cases are exempt from the ordinary open/acknowledged expiration filter. Separate physical inactivity from operator case closure.

## 11. Tracking and association audit

`ByteTrackTracker` wraps supervision ByteTrack with defaults activation 0.25, lost-track buffer 30, matching 0.3 and nominal frame rate 30. Those are tracker-update parameters, not a promise of one second of wall-clock survival under a five-FPS analyzed stream. It maintains detection metadata and matches returned tracks to class/bbox data. Its metadata map is not pruned with every lost track; `get_track_count` can count historical metadata. Reset clears identity without a persistent epoch.

`aegis/tracking/deepsort_tracker.py:DeepSortTracker` is an alternative used by the stream tracking fallback for unavailable ByteTrack imports. Defaults include max age 30, three initial observations, cosine distance 0.3 and IoU distance 0.7. Its output construction does not preserve all the weapon/category/source fields of the enhanced ByteTrack contract. End-to-end metadata parity is required before treating the fallback as equivalent.

`TrackHistoryManager` defaults to 60 positions and removal after 90 stale processed frames. It has timestamps, centers, bounding boxes and cumulative image displacement. `MotionAnalyzer` derives velocity, acceleration and direction from sample displacement, not calibrated meters/second. There is no durable complete trajectory in the active ingestion path.

`PersonWeaponAssociationEngine` uses these default geometric scores:

- Weapon center contained in person box: 0.92 plus a bounded overlap increment, capped at 0.99.
- Overlap: IoU >=0.04 or weapon-overlap fraction >=0.25; score starts at 0.78 with a capped 0.17 increment.
- Expanded upper-body region: score roughly 0.62-0.78 depending on normalized distance.
- Nearby center: normalized distance <=0.80; score `max(0.35, 0.72 - distance*0.35)`.

It tracks pair stability per assessment call; it does not validate frame continuity as strictly as aggression-pair tracking, and inactive pair-count keys are not comprehensively pruned. No hand pose, calibrated depth, independent ownership confidence, or cross-camera identity guarantee is present here.

## 12. Risk engine audit: actual rules and weights

These are alternative/layered policies, not one coherent probability model. A value of 0.9 must not be presented as a 90% probability of danger.

### Base behavior risk

Sources: `aegis/risk/risk_engine.py:RiskWeights/RiskEngine.compute_risk`, `risk_types.py:RiskThresholds`, `zone_context.py`, `temporal_model.py:TemporalConfig`.

| Factor | Default weight / calculation |
| --- | --- |
| Loitering | 0.25; severity ramps with track duration / 30 seconds, capped at 1; stationary fallback ramps over 60 seconds, capped at 0.5 |
| Sudden speed change | 0.18 times boolean signal |
| Direction change | 0.15 times boolean signal |
| Crowd density | 0.12 times bounded density / 10 when crowd signal is present |
| Erratic motion | 0.10 times boolean signal |
| Running | 0.05 times boolean signal |
| Zone | Declared weight 0.15, but zone factor is appended after base summation; operational influence is a multiplier, not that declared additive weight |
| Zone multipliers | normal 1, elevated 1.25, high-risk 1.5, restricted 2; configurable override |
| Temporal | After 30 suspicious frames, +0.02 per frame up to 0.3; after 15 normal frames, decay 0.01 per frame |

Final base-engine score is clamped `base * zone_multiplier + temporal_adjustment`. Default levels: LOW <0.25, MEDIUM >=0.25, HIGH >=0.50, CRITICAL >=0.75. The pipeline startup supplies different HIGH/CRITICAL thresholds (0.7/0.85) to its configured engine. Frame-count temporal adjustment changes real-time meaning with workload/FPS.

### Camera frame/evidence overrides

Source: `FrameIngestionService._apply_frame_rules`, `_build_evidence`, `_motion_behavior_confirmed`.

- Frame heuristics: ordinary person baseline 0.05; three-person presence 0.25; crowd 0.45; running/erratic 0.35; loitering 0.35. Global proximity signals are copied into relevant person/weapon scores, with weapon-overlap floor 0.90, before later evidence gates.
- Evidence gates reset ordinary persons/vehicles to LOW <=0.10; unsupported weapon classes also remain LOW. Weapon confidence <0.50 is a verification candidate around 0.25-0.30. Unassociated weapon is MEDIUM around 0.40-0.49.
- Near association, confidence >=0.70 and >=2 stable samples: HIGH, clamped `confidence*0.65 + association*0.25` to 0.55-0.70.
- Overlap/containment, confidence >=0.85, association >=0.75 and >=3 stable samples: CRITICAL, clamped `confidence*0.70 + association*0.25` to 0.80-0.95.
- Overlap with confidence >=0.70 and >=2 samples: HIGH, clamped `confidence*0.60 + association*0.25` to 0.55-0.72. Weaker association cases have MEDIUM floors around 0.42-0.45.
- Person-side association mirrors these transitions with floors HIGH 0.55 or CRITICAL 0.80. Motion-only remains candidate approximately 0.25-0.35; loitering approximately 0.25-0.45.
- Motion confirmation additionally requires at least 12 history samples, duration >=0.35 seconds, smoothed displacement >=18 pixels/frame and displacement/bbox-scale >=0.6.
- Threat context can subsequently override these values/confirmation; final supported-class and reason-code checks still apply. CRITICAL allowlisted reasons include stable weapon-person association and weapon-aggression combination, not only validated violence.

Detection confidence is explicitly multiplied into risk here. Even stable high-confidence geometry is not equivalent to high incident severity.

### Weapon/aggression context

Source: `aegis/risk/weapon_aggression.py:WeaponAggressionConfig/WeaponAggressionEngine`.

- Close normalized box gap <=0.22; shrinking gap >=0.025; fast motion / body diagonal >=0.055; approach cosine >=0.45.
- Association normally confirms after two frames. One-frame override requires weapon confidence >=0.90 and association >=0.80 with overlap/containment.
- Weapon-association candidate score 0.45; confirmed association HIGH 0.66. Existing tests demonstrate two-frame association with weapon confidence 0.40 can become HIGH.
- Confirmed armed actor with nearby person: HIGH at least 0.72. Repeated close interaction (two frames), fast movement, and approach/shrinking/sudden signal can become CRITICAL 0.90.
- Unarmed fast/close/approaching interaction: candidate MEDIUM 0.42, confirmed after three close frames HIGH 0.60. Close persistence is not proof that aggressive behavior persisted throughout that window.
- Pair history expires after 12 stale frames and checks continuity. Fast movement can come from either participant. These are deterministic motion heuristics, not a trained aggression model.

### Other scoring paths

- `ProximityRiskEngine`: co-presence floor 0.50, overlap floor 0.70, stable pair after five frames 0.85, anomaly boost 0.10, pair expiry ten frames, cloud escalation threshold 0.60. It uses level thresholds 0.25/0.50/0.75.
- `EdgeRiskFilter` / `config.py:EdgeConfig`: weapon +0.50, person co-presence +0.30, overlap +0.20 per matched weapon, behavior +0.15 once, clamped at 1; escalation default 0.40 and cooldown. This is additive edge triage, not validated incident inference.
- `RiskFusionEngine`: fallback to edge score; potential conditional boosts CLIP +0.15, holding +0.20, aiming/attacking +0.15, close depth +0.10. Model runner stubs do not provide those signals in the inspected implementation.

Unifying policies must cover camera, stream, analyze, edge and CLI entry points, not merely edit one threshold.

## 13. Reliability, performance and deployment gaps

| Failure | Current behavior and source | Required direction |
| --- | --- | --- |
| Camera disconnect | Reconnect/error/stopped states and backoff in `OpenCVLoopCameraSource._capture_loop` | Surface coverage loss and observation gaps; never interpret missing frames as safe |
| Inference exception | Manager task wrapper catches/logs and updates source error state; stage loops also catch errors | Worker health distinct from camera health; supervised restart, explicit lost-work accounting |
| Tracker reset | `FrameIngestionService.reset_camera` and tracker reset discard state | New source/tracker epoch; conservative continuity, no accidental ID reuse |
| Redis unavailable | `EventBus` switches to bounded process-local fallback; no verified reconciliation | Local durable authority/outbox; optional Redis transport with idempotent replay |
| Database unavailable | Persistence catches/reports failures; some APIs return runtime data | Durable bounded spool or explicit unavailable state, visible unsaved events and retry |
| WebSocket disconnect | Client reconnect/snapshot mechanisms, finite recent histories | Cursor-based catch-up, incident revision checks and resync |
| Optional model failure | `WeaponDetector` disables optional capability and returns no detections | Distinguish no detections from model unavailable; do not lower risk based on missing evidence |
| Malformed/oversized frame | Decode rejection in camera utils; upload extension validation in camera API | Size/pixel limits, timeouts and bounded decode/inference admission |
| Snapshot/clip failure | Snapshot and DB persistence can diverge; active clip linkage not found | Artifact state machine, retry/quota, explicit missing evidence |
| Queue overflow/restart | Alert queue bounded; volatile state can be lost | Durable alert intent, per-channel attempt state and restart recovery |

Current latency identification: manager submission interval 0.2 seconds caps ordinary per-camera analysis at roughly five submissions/second before model cost; this is not measured throughput. Browser frames bypass that control. Preview and analysis FPS are different. `APIState` retains 100 recent events; ingestion has 1,000-entry deques. Default alert API queue is 100. Dashboard polling adds seconds of potential visibility delay independently of inference (`use-aegis-api.ts`); general WebSocket snapshots loop around 0.5 seconds (`aegis/api/websocket.py`). Real end-to-end percentile latency: **Not found / not verified**.

Proposed measurements: captured/accepted/analyzed/dropped frames by reason; inference and queue-wait p50/p95/p99; event and incident creation latency; DB commit latency/failures; outbox age/retries; camera disconnect duration; model availability; tracker resets/ID switches; buffer bytes; evidence completeness; alert transition/suppression counts; delivery-to-ack latency; reviewed false positives per camera-hour. Carry capture, receive, inference start/end, observation commit, assessment commit, dispatch and UI receive timestamps. Avoid track/incident IDs as unbounded metric labels.

Deployment findings:

- Root `docker-compose.yml` publishes database/cache/application ports and includes default database credentials; Redis has no configured authentication. Published ports are not loopback-restricted by that file.
- `deploy/docker-compose.yml` plus `deploy/nginx.conf` provide reverse-proxy/TLS structure, but this is not proof of deployment security. The camera credential production guard relies on Aegis-specific environment flags, not just frontend `NODE_ENV`.
- `Dockerfile` runs the API as non-root and preloads a base model, but startup does not supply a verified schema-upgrade workflow; liveness is not successful inference/persistence readiness.
- `aegis/api/routes/health.py` readiness checks include credentials/database/model files/evidence storage. File presence/import success does not prove a functioning inference-to-alert loop.
- `.github/workflows/ci.yml` runs unit/integration Python tests, not the separate security directory or frontend suite; dependency safety checking is non-blocking (`|| true`). Build/smoke checks are not replay/load/fault tests.

## 14. Security and privacy

Positive controls: `verify_api_key` fails closed when no server key is configured and uses constant-time comparison; evidence snapshot path containment is checked; camera URLs and credential storage are separated; WebSocket tokens are signed and short-lived. Sources: `aegis/api/security.py`, `aegis/api/routes/events.py`, `aegis/camera/credentials.py`.

Material gaps:

1. `frontend/src/app/api/backend/[...path]/route.ts` forwards broad HTTP methods/paths while injecting the server API key and internal HMAC marker. Caller authentication, role checks and origin enforcement were **Not found / not verified**. `frontend/src/middleware.ts` performs locale handling and excludes API routes. Thus the shared backend key does not protect callers arriving through this proxy. Valid internal proxy signatures bypass backend IP rate limiting in `GlobalRateLimitMiddleware`, so caller-facing limits are also needed.
2. `aegis/cloud/cloud_server.py:analyze_event` accepts `x_api_key` but does not validate it. This is a separate optional service, not the main secured API. Do not expose it as authenticated cloud analysis.
3. Main API authorization is a shared key, not camera/evidence-specific roles or authenticated operator identities. Tenant isolation: **Not found / not verified**. Single-owner localhost deployment does not require a tenancy platform, but LAN/public exposure must be a deliberate later step.
4. WebSocket credentials authorize at handshake and are not scoped to a particular user/camera; ongoing revocation, origin restrictions and per-resource authorization were **Not found / not verified** in the inspected handlers.
5. `CameraCredentialStorage` uses plaintext local JSON in development. Its production guard applies to saving, not proof that previously saved plaintext cannot be loaded. POSIX permission-setting is not an audited Windows ACL policy. Use Windows credential protection for this target.
6. `validate_stream_url` checks scheme/hostname, not allowed destinations. Camera connection and uploaded-path capabilities need intentional LAN/device/path scope. Do not blanket-block private addresses, because local cameras need them; enforce an operator-controlled allowlist instead.
7. Camera upload copies data after extension checks without an explicit application-level size quota. Recording routes trust stored recording paths more broadly than the snapshot root check. Exploitability beyond authorized inputs was **Not verified**; constrain path roots, upload bytes, decoded pixels and processing time.
8. `aegis/audit/service.py:record_audit` is best-effort, and `x_aegis_actor` is a caller-provided label, not trusted identity. Complete recording-access auditing, tamper-evident audit retention, encryption-at-rest policy and video deletion/retention enforcement were **Not found / not verified**.
9. Local snapshots/recordings contain sensitive people/video. Generic privacy helpers elsewhere do not establish video masking, consent, retention or safe external-AI egress in the camera path.

Local-PC baseline proposal: bind services to loopback, keep database/cache ports unpublished, validate Host/Origin and mutation requests, protect proxy access, restrict camera destinations and evidence roots, enforce quotas, store secrets with OS protection, and keep external video/model calls off unless explicitly configured. This is a technical proposal, not a jurisdiction-specific legal compliance assessment.

## 15. Testing gaps and observed results

Executed existing modules (54 passed, 83 warnings):

```text
tests/security/test_phase1_production_blockers.py
tests/unit/test_operational_alert_persistence.py
tests/unit/test_incident_correlation.py
tests/unit/test_phase3_operational_hardening.py
tests/unit/test_evidence_risk_phase2.py
tests/unit/test_risk_honesty.py
tests/unit/test_weapon_aggression_risk.py
tests/unit/test_weapon_aggression_pipeline.py
tests/unit/test_detection_intelligence_layer.py
tests/unit/test_event_bus_fallback.py
```

Useful existing sequence coverage includes stable association, consecutive close interaction, parallel running not confirming assault, actor ownership, weapon-ID-independent cooldown, incident grouping, duplicate-event handling, camera separation, explicit expiration calls and persistence failure. Sources: `test_weapon_aggression_risk.py`, `test_incident_correlation.py`, `test_evidence_risk_phase2.py`.

Some tests enforce the very policies the requested redesign should reconsider: one strong association becoming HIGH, and stable weapon containment becoming CRITICAL. Do not simply preserve all old assertions while claiming the new architecture is observation-first.

Frontend static findings needing contract tests:

- `frontend/src/lib/evidence-api.ts:incidentSchema` accepts only `active`/`resolved`, while backend incident presentation includes operator lifecycle statuses such as `open`, `acknowledged`, `under_review`, and `false_positive`. `AegisVoiceCore.tsx` consumes this client. The separate schema in `lib/schemas.ts` accepts arbitrary status strings, so the mismatch is specific, not universal.
- `frontend/src/lib/activity-alerts.ts:buildActivityAlertItems` builds its displayed items from events even when operational alerts are supplied; alert data only helps related context. It groups with camera-level keys and treats acknowledged as resolved. This can hide distinctions between independent incidents and between acknowledgment and resolution.
- `activity-alerts-workspace.tsx` provides camera/evidence navigation; a complete lifecycle-mutation UI was **Not found / not verified**.
- `frontend/src/lib/config.ts` derives camera WebSocket URLs from configured API URLs; the relative default proxy URL cannot be used directly as an absolute URL. Socket operation with no explicit public backend URL needs a contract/browser test, not assumption.

Required new sequence acceptance tests:

| Sequence | Expected invariant (proposed policy) |
| --- | --- |
| Knife in one noisy frame | Observation only; no HIGH/CRITICAL from object confidence alone |
| Persistent knife, no person relationship | Object event may exist; no fabricated carrying/violence assertion |
| Persistent geometric person association | One uncertain carrying-associated event; no automatic violent-incident confirmation |
| Association plus sustained approach/nearby target | Escalation candidate with explicit heuristic limitations; classifier corroboration only if a real validated classifier is available |
| Same scene across 100 frames | One evolving chain; alerts on meaningful transitions, not every frame |
| Scene ends | Physical activity ends after tested grace; operator case remains separately reviewable |
| Track briefly disappears/ID changes | New track epoch/local identity handled conservatively; no automatic unrelated-person merge |
| HIGH then CRITICAL inside cooldown | One incident, durable assessment update and escalation notification |
| Two unrelated people in same zone | No merge solely because zone/time/score match |
| Replay duplicate/out-of-order frames | Idempotent writes, bounded lateness policy, no fabricated persistence |
| Restart/DB/Redis/queue/artifact failure | Recoverable intent or explicit loss/unavailable state; no false delivered status |

Replay harness proposal: consented local clips with labeled time intervals, participants and uncertainty; deterministic captured timestamps; cached model detections for cheap rule regression; a smaller real-model end-to-end set. Include kitchens/work tools, perspective, night blur, occlusion, camera shake, groups running together, genuine approach and benign close passing. Measure event/incident precision-recall, false alerts per camera-hour, time-to-detect, identity switches, duplicates and evidence completeness. Split evaluation by camera/location rather than adjacent frames from the same video. Do not tune thresholds against the final holdout.

## 16. Proposed target architecture: local-PC first

This design keeps the current Python/FastAPI/SQLAlchemy/SQLite-compatible shape and makes one source of truth. It deliberately does **not** require Kafka, Celery, Redis, cloud inference, LLM calls, or cross-camera re-identification. Redis may later be a transport/cache, but must not be the sole authority for safety-related history.

```text
camera frame (capture timestamp, camera/source epoch)
  -> detector output [immutable Detection observations]
  -> tracker/history [entity observations; camera-local track epoch]
  -> relation/behavior extractors [association, proximity, motion observations]
  -> bounded camera correlation buffer + durable append-only Observation store
  -> Event builder [claims with temporal/spatial/entity support]
  -> Incident resolver [find/update/merge one stateful incident]
  -> Risk assessor [versioned, explainable assessment of that incident]
  -> transactional intent/outbox [alert only on a meaningful transition]
  -> dispatcher [delivery attempts and operator actions]
  -> REST/WebSocket revision stream + dashboard
```

### Entity model and versioned envelopes

Use a shared `schema_version`, an immutable UUID, UTC capture/ingest times, source epoch and correlation key on every inter-service envelope. Keep bounding boxes in pixels **and** record frame width/height; only label a distance in meters when a camera calibration/version supports it. Preserve original model identifier/config/checkpoint fingerprint where available; otherwise state `model_version: "unknown"`.

| Entity | Purpose and minimum fields | Persistence / relationship |
| --- | --- | --- |
| `Observation` | `observation_id`, `schema_version`, camera/source/tracker epoch, captured/received/processed time, frame sequence, type, subject/related entity references, label, model confidence, bbox/normalized bbox, zone, source model, raw-artifact reference, metadata | Append-only. One frame can yield many observations; a detector claim is not a danger claim. Partition/retention by local camera/date. |
| `Event` | `event_id`, type, camera, start/end, state, involved entity refs, supporting-observation IDs/counts, event confidence, correlation rule/version, evidence summary | Derived state with revisions. Examples: `object_present`, `object_person_association_candidate`, `approach_interaction_candidate`; avoid asserting "armed confrontation" until support exists. |
| `Incident` | `incident_id`, `schema_version`, category/hypothesis, physical state, operator state, severity, uncertainty, start/last-observed, `camera_ids`, active event IDs, revision, merge/suppression keys | Stateful aggregate. `camera_ids` is an array/table even while local v1 only adds one camera. Do not attach cross-camera identities until a later, explicit re-ID capability. |
| `IncidentParticipant` | participant ID, incident ID, camera-local entity epoch, role (`subject`, `related_person`, `object`, `unknown`), association confidence, start/end and evidence refs | Normalized table. A relationship can be ambiguous instead of choosing an owner. |
| `Evidence` | evidence ID, kind (`frame`, `clip`, `model_output`, `operator_note`), immutable content reference/hash, timestamps, retention class, capture/model provenance, availability state | Link separately to observation/event/incident; never reuse an event ID as evidence ID. Files can be local paths initially, rooted and access-controlled. |
| `RiskAssessment` | assessment ID/revision, incident ID, policy/version, assessment time, severity band, non-probabilistic score (if retained), calibrated confidence separate from risk, factor results, missing/contradictory evidence, rationale | Append-only assessment history. Current assessment is a materialized pointer on Incident. |
| `Alert` | alert ID, incident ID, assessment revision, transition/reason, channel, delivery attempts/states, created/delivered/acknowledged times and trusted actor | Created only from committed assessment transitions; a delivery record is never evidence or an incident itself. |

Illustrative envelope, not a claim about existing schemas:

```json
{
  "schema_version": "1.0",
  "observation_id": "uuid",
  "camera_id": "front-door",
  "source_epoch": "camera-start-uuid",
  "tracker_epoch": "tracker-reset-uuid",
  "captured_at": "2026-09-16T12:00:00.120Z",
  "frame_sequence": 1923,
  "type": "object_detection",
  "entity_ref": {"kind": "track", "id": "43", "epoch": "..."},
  "label": "knife",
  "model_confidence": 0.87,
  "bbox_xyxy_px": [100, 120, 150, 180],
  "frame_size_px": [1920, 1080],
  "model": {"name": "weapon_detector", "version": "unknown"},
  "artifact_ref": "evidence://frame/sha256/..."
}
```

Migration strategy: extend, do not duplicate, existing `Event`, `Incident` and `OperationalAlert` where that preserves compatibility. Add new tables for `observations`, `incident_participants`, `evidence`, `risk_assessments`, `alert_deliveries`/`outbox`, and a schema-version/correlation-key field. Retain legacy event payloads behind an adapter during migration. First fix and test a clean Alembic baseline before applying any new revision; provide an upgrade plan for the current `create_all`/legacy database state rather than assuming one starting schema.

### Correlation engine

Run correlation per camera/source epoch in the local process. Maintain a short in-memory hot buffer (for example, 30 seconds or a bounded observation count) and append compact observations to the database. The buffer makes real-time queries cheap; durable observations make restart/replay/audit possible. It should be bounded by time and memory, expose eviction metrics, and never silently treat eviction as resolution.

For each new observation:

1. Validate schema, timestamp bounds, camera/source epoch and idempotency key `(camera, source_epoch, frame_sequence, extractor, entity/relation, model version)`.
2. Attach to a camera-local entity only when tracker epoch and spatial/temporal continuity support it. Otherwise create an uncertain relation, not a forced match.
3. Form or update events using explicit per-event windows: persistence count plus elapsed duration, max gap, spatial compatibility, zone, entity role and supporting evidence. An event must record its actual rule version and support list.
4. Find candidate incidents using event type compatibility, shared participants, explicit relation edges, camera/time overlap and spatial/zone compatibility. Zone/time alone can only create a candidate requiring additional support, never merge automatically.
5. Apply a monotonic revision to the chosen incident. A merge must leave an audit trail (`merged_from`, policy/reason, prior revisions); it must be reversible by an operator.
6. Run a new RiskAssessment from the committed incident graph. Persist its explanation and every considered factor, including unavailable models.
7. Write an alert-intent outbox row in the same transaction only when the assessment crosses an approved policy transition. Dispatch asynchronously after commit, idempotently per `(incident_id, assessment_revision, transition, channel)`.

Suggested windows are deliberately configuration starting points, not promised production values: object observations 2-5 seconds with a frame-count plus elapsed-time criterion; person-object association 2-10 seconds and association-confidence stability; approach/interaction 3-15 seconds; incident inactivity grace 30-120 seconds. Tune per camera with replay data and retain the chosen policy version.

### Incident state machine

Separate physical intelligence state from operator workflow. This prevents an operator acknowledgment from pretending the scene is over.

```text
physical:  NEW -> OBSERVING -> SUSPICIOUS -> HIGH_RISK -> INACTIVE -> RESOLVED
                         |             |              |
                         +--> DISMISSED +--------------+

operator:  UNREVIEWED -> ACKNOWLEDGED -> UNDER_REVIEW -> CONFIRMED | FALSE_POSITIVE
                                                     -> RESOLVED
```

- `NEW`: first correlatable evidence, below event persistence threshold.
- `OBSERVING`: evidence/event is accumulating; no urgent alert.
- `SUSPICIOUS`: supported but uncertain; optional dashboard item, not automatic emergency notification.
- `HIGH_RISK`: assessment satisfies the policy with durable reasons. Alert once on entry; update the same alert/incident on material escalation.
- `INACTIVE`: no relevant observations during tested grace period; evidence remains immutable and operator workflow stays open until handled.
- `DISMISSED`/`FALSE_POSITIVE`: a human decision with actor, time, reason and optional expiry/reopen policy. New independent evidence must not be suppressed forever.
- `RESOLVED`: physical and operator disposition complete; terminal except an audited reopen.

Allowed transitions must be validated in one service with optimistic incident revisions. Do not allow arbitrary status jumps. Add a transition table for actor/action/reason and explicit authorization. Alert policy should distinguish: create, severity escalation, evidence-completeness failure, operator reminder, and resolution—rather than use one fixed cooldown for everything.

### Explainable, calibrated risk policy

Start with a transparent rule/decision policy, not an arbitrary additive score. Use four outputs that must remain distinct:

- **Evidence confidence:** reliability and persistence of a specific observation/model claim.
- **Association confidence:** confidence that two entities are related; geometric association should remain explicitly uncertain.
- **Incident confidence:** support for the current incident hypothesis given all evidence and contradictions.
- **Risk severity:** expected consequence/urgency if the hypothesis is true. It is not probability and must not be inferred directly from a detector score.

Use prerequisite gates and bounded factor bands. Example policy shape:

| Candidate conclusion | Minimum evidence gates | Possible result |
| --- | --- | --- |
| Object present | Valid model observation persists per detector policy | Observation/event; LOW or informational |
| Object associated with person | Stable geometric relation, with ambiguity retained | Suspicious event; normally MEDIUM at most absent other context |
| Dangerous interaction candidate | Association + independent sustained interaction evidence (approach/proximity/behavior) + temporal continuity | SUSPICIOUS/HIGH candidate, with each factor shown |
| Critical urgent incident | Multiple independent supports, policy-specific persistence, no known contradiction; ideally a real validated classifier or operator confirmation | CRITICAL candidate/alert; geometry alone is insufficient |

Independence matters: do not count the same bounding-box overlap as separate weapon, association and proximity evidence. Factor outputs should be `supported`, `not_supported`, `unavailable`, or `contradictory`, each with value, window, source and rule/model version. A conservative policy takes the minimum required gates first; then a bounded severity matrix or monotonic decision tree maps context to a level. Calibrate any numerical score afterwards using replay labels, reliability plots and false-alert cost, and name it `policy_score` until calibrated. This avoids calling a hand-built number a probability.

For person-object association, retain current overlap/proximity as a weak signal and record its method. A later upgrade may combine pose/hands, temporal co-motion and image crops, but only after proving model availability, latency and camera-specific accuracy. Do not infer "carrying", "aiming" or a person identity from geometry alone. No cross-camera re-identification is proposed for v1.

### Alerting, API and dashboard contract

The dashboard consumes incident revisions, assessments and alert delivery state—not a mixture of generic events and alert rows. Provide cursor/revision endpoints and an authorized WebSocket stream that can resume from a revision token. REST responses must return a single documented status enum and schema version.

Minimum operator commands: acknowledge, confirm, dismiss/false-positive, escalate, resolve, add note, attach evidence and reopen. Every command needs authenticated actor identity, incident revision (`If-Match` equivalent), reason where appropriate, durable audit entry and domain event. These actions form labeled feedback data, but not automatically model training data.

For local use, one trusted operator role is enough initially; design the data as actor/role-capable so LAN/multi-user expansion does not rewrite history. Any notification must say "AI assessment—operator review required" and link the reasons/evidence, rather than claim certainty.

## 17. Prioritized implementation roadmap

No item below has been implemented by this audit. File lists are intentionally precise entry points, not exhaustive future diffs. Start each P0 item on a branch after the user approves the design.

### P0 — required before relying on local alerts

| Change | Reason | Existing files affected | New files / migration | Dependencies | API / frontend implication | Tests required |
| --- | --- | --- | --- | --- | --- | --- |
| P0.1 Establish one authoritative camera event path and policy contract | Current camera, pipeline, analyze, edge and CLI paths can emit different severities | `aegis/api/app.py`, `camera/manager.py`, `video/camera_sources.py`, `pipeline/startup.py`, `pipeline/*`, `api/routes/analyze.py`, `edge/*` | `aegis/intelligence/policy.py` or equivalent documented policy adapter | Inventory of callers; no new infrastructure | Mark alternate routes experimental or normalize their response contract; dashboard reads authority marker | End-to-end camera ingest; assert inactive stages receive no untyped frames; same fixture produces one policy result |
| P0.2 Make migrations bootstrappable and protect existing data | Clean Alembic upgrade demonstrably fails; schema authority is split | `alembic/env.py`, `alembic/versions/*`, `aegis/database/connection.py`, `init.sql`, Docker startup docs | Correct baseline/reconciliation migration and upgrade runbook | Backup/restore dry run on a copy of local DB | Readiness exposes schema version/migration health | Blank DB, legacy DB copy, upgrade/downgrade policy, interrupted migration recovery |
| P0.3 Introduce Observation, Evidence and RiskAssessment as distinct durable records | Current event/evidence/alert identity conflation prevents audit/replay | `database/models.py`, `repositories.py`, `video/camera_sources.py`, `events.py` | models/repositories/schema module; migration for six entity links | P0.2 | Versioned observation/event/incident DTOs; keep legacy adapter temporarily | Idempotent observation write; artifact link; rollback; legacy API contract tests |
| P0.4 Correlate before assessment/alert and preserve suppressed evidence | Alert cooldown now blocks durable incident updates | `video/camera_sources.py`, `intelligence/incident_correlation.py`, `alerts/alert_manager.py` | `intelligence/correlation_engine.py`, `risk/assessment_service.py` | P0.3 | Events endpoint gains incident/revision; dashboard can show evolving case | HIGH then CRITICAL inside cooldown; 100-frame scene; restart/replay; unrelated same-zone scenes |
| P0.5 Replace fixed cooldown with transition-aware durable outbox | Dispatch precedes durable truth; escalation can be lost | `alerts/alert_manager.py`, `database/models.py`, `repositories.py`, camera and pipeline alert callers | `alerts/outbox.py`; `alert_deliveries`/outbox migration | P0.3/P0.4 | Alert status separates pending/sent/failed/acknowledged; no "delivered" on enqueue | DB failure, dispatcher restart, duplicate delivery, queue full, escalation notification |
| P0.6 Conservative weapon/association policy and reason preservation | Geometry/confidence can create CRITICAL without intent; evidence overrides are hard to reason about | `risk/person_weapon_association.py`, `risk/weapon_aggression.py`, `risk/proximity_risk.py`, `risk/risk_engine.py`, `video/camera_sources.py`, `pipeline/risk_scoring.py` | versioned policy config / rationale formatter | P0.1/P0.4 and replay corpus | Expose factor statuses, policy version, uncertainty; label scores honestly | Required sequences in section 15; regression for current tests revised to new safety contract |
| P0.7 Local-PC boundary hardening | Privileged frontend proxy/cloud API and local secrets/video need protection | `frontend/src/app/api/backend/[...path]/route.ts`, `middleware.ts`, `api/security.py`, `api/websocket.py`, `cloud/cloud_server.py`, `camera/credentials.py`, `camera/utils.py`, compose files | local security configuration and Windows secret-storage adapter | User's intended loopback/LAN scope | Browser auth/session or strictly loopback UI; scoped WS token; API error contract | Proxy auth/origin, WS scope/expiry, localhost binding, upload/decode quota, URL allowlist, recording/evidence access |

### P1 — strongly recommended after P0 behavior is stable

| Change | Reason | Existing files affected | New files / migration | Dependencies | API / frontend implication | Tests required |
| --- | --- | --- | --- | --- | --- | --- |
| P1.1 Incident/participant state machine and trusted operator actions | Current lifecycle permits broad status changes and UI actions are incomplete | `intelligence/incident_correlation.py`, `database/repositories.py`, `api/routes/events.py`, `audit/service.py`, activity workspace | `intelligence/incident_lifecycle.py`; participant/transition tables | P0.3/P0.4/P0.7 | Commands for ack/confirm/dismiss/escalate/resolve/note with revision conflicts handled | Transition matrix, authorization, audit integrity, concurrent operator update, reopen policy |
| P1.2 Evidence recorder integration and retention | Active serious events have snapshots but no verified incident clip wiring | `recording/risk_recorder.py`, `video/camera_sources.py`, recording/event routes | evidence artifact service; retention/quota job/config | P0.3/P0.5 | Evidence availability, hash, clip/snapshot states; secure streaming | Pre/post buffer, disk full, missing artifact retry, retention, path containment |
| P1.3 Replay and calibration harness | Thresholds cannot be safely tuned by unit examples alone | current risk tests, `tests/integration/*`, `video/metrics.py` | `tests/replay/*`, fixtures manifest/labels, evaluator | P0 policy entities | Operator review exports evaluation labels, no automatic training | Determinism, camera split, calibration/precision metrics, real-model smoke clips |
| P1.4 Observability and recovery drills | Current metrics do not prove end-to-end reliability | `video/metrics.py`, metrics/health routes, `core/events.py`, alert service | structured metric/trace module, health/recovery checks | P0.5 | Dashboard system-health explicitly reports degraded persistence/model/camera states | Fault injection for DB, queue, tracker, model, WS; p95 latency and backpressure assertions |
| P1.5 Dashboard contract consolidation | Current frontend mixes events/alerts and incident schema differs by client | `frontend/src/lib/evidence-api.ts`, `lib/schemas.ts`, `lib/activity-alerts.ts`, dashboard/event components/hooks | generated/shared API schema types or a single adapter | P0 APIs | Revision-driven incident queue, factor/explanation/evidence display, operator commands | Contract fixtures for every lifecycle state, websocket resume, accessibility/action tests |
| P1.6 Optional Redis transport repair or removal | Current stage payloads are not serializable/durable | `core/events.py`, `pipeline/stages.py`, `pipeline/*` | explicit wire DTOs and replay/claim design, or remove inactive pipeline startup | P0.1 | Health reveals transport mode and lag; no silent fallback claim | Serializer round trips, pending reclaim, reconnect, duplicate/idempotency, broker outage |

### P2 — future, only after measured P0/P1 value

| Change | Reason | Existing files affected | New files / migration | Dependencies | API / frontend implication | Tests required |
| --- | --- | --- | --- | --- | --- | --- |
| P2.1 Validated pose/action/interaction models | Current hand/violence/action signals are absent or stubs; geometry is limited | `fusion/risk_fusion.py`, detector/risk/correlation adapters | model adapters, capability registry, model-evaluation records | Labeled replay corpus, hardware latency budget, privacy review | Show model availability/version and uncertainty, never claim missing model ran | Per-camera accuracy, drift, latency, unavailable-model fallback, adversarial/occlusion clips |
| P2.2 Cross-camera correlation without automatic ReID | Data model should support multiple cameras before identity linking | incident/correlation schema and services | camera-topology/time-sync relation tables | P1 stable incidents; privacy/consent design | Incident shows camera timeline; no asserted same-person identity in v1 | Clock skew, handoff ambiguity, merge/reversal workflows |
| P2.3 Calibrated probabilistic risk and feedback analysis | Policy score only becomes probability after evidence | assessment policy, observability, operator actions | calibration/evaluation pipeline and governance record | P1 replay/labels, bias/privacy review | Explain calibrated confidence and data coverage | Holdout calibration, per-camera drift, false-positive/negative cost analysis |
| P2.4 Multi-user/RBAC and remote deployment | Needed only when moving beyond one local trusted operator | API security, proxy, WS, frontend auth, deployment | identity/RBAC/tenant schema only if actual tenants are needed | P0.7/P1.1; threat model | Scoped resources, audit actor identity, team queues | Authorization matrix, tenant isolation, session/revocation, penetration test |

### Recommended first implementation slice after review

Keep the first change small and measurable: P0.2 followed by a narrow P0.3/P0.4 vertical slice for one camera and one `object_person_association_candidate` event. Persist observations, create/update one incident, create one versioned assessment, and display the explanation without changing model selection. Then replay the required benign and escalation sequences. This removes the most dangerous conflation before adding any "smarter" model, and it is much cheaper than a broad rewrite.

## Decision points for review

1. Approve the observation-first vocabulary and separate physical/operator incident states.
2. Agree that geometric weapon-person association alone cannot create CRITICAL; decide whether it can ever generate HIGH without an additional independent signal.
3. Choose loopback-only local operation as the P0 security posture. If LAN camera/UI access is required, specify the allowed devices/network so the allowlist and authentication are designed deliberately.
4. Confirm whether the existing local database should be treated as disposable development data or requires a migration-preservation rehearsal. This affects P0.2 sequencing, not the target architecture.
