# Aegis Engineering Audit

**Scope:** repository and live local-container audit, 30 September 2026. This is an architecture and improvement audit only; no perception, risk, transport, or infrastructure behavior was changed as part of it.

## Executive assessment

Aegis already has the foundations of a credible real-time safety platform: source-specific camera lifecycle management, bounded in-memory state, YOLO-based detection, per-camera ByteTrack, temporal behavior/risk signals, durable event/incident records, authenticated REST/WebSocket APIs, and a polished Next.js operator surface. The project is much more than a set of independent CV demos.

The main engineering opportunity is to make the **active path explicit, measurable, and admission-controlled**. At present, a single processed frame can synchronously perform multiple model passes, tracking, behavior/risk/fusion, per-track database transactions, snapshot encoding, and JSON/base64 fan-out. This is safe enough for a small demo because the camera manager coalesces work, but it limits multi-camera throughput and makes latency difficult to explain or guarantee.

The immediate objective should not be a tracker or framework replacement. It should be:

1. measure per-stage latency and frame age;
2. remove synchronous persistence from the vision worker;
3. make preview delivery binary/compact and rate-aware;
4. enable an NVIDIA GPU correctly before attempting advanced GPU optimizations;
5. run a labelled tracker/inference benchmark before selecting a more complex tracker.

### Measured runtime context

The currently running local Docker API used approximately **293% CPU** and **1.05 GiB RAM**. Its installed PyTorch build is CUDA-capable (`2.14.0+cu130`), but `torch.cuda.is_available()` was `False`, the container saw zero CUDA devices, and Docker had no GPU `DeviceRequest`. This makes CPU contention—not a lack of model features—the present bottleneck. PostgreSQL and Redis were nearly idle at the same time.

## 1. Actual active architecture

The FastAPI camera routes instantiate `aegis.camera.manager.MultiCameraPipelineManager`. That manager imports and uses the active `FrameIngestionService` from `aegis.video.camera_sources`. The older `aegis.pipeline.AICameraPipeline` and a second legacy `MultiCameraPipelineManager` retained inside `aegis.video.camera_sources` are not wired by the FastAPI camera route and should not be treated as the production execution path.

```text
RTSP / HTTP / local device / uploaded video / browser webcam
        |
        | OpenCV VideoCapture capture thread, or browser JPEG POST
        v
BaseCameraSource
  - latest full NumPy frame (under a lock)
  - latest compact JPEG preview (throttled; default 15 FPS, 960 px, Q75)
  - frames received/dropped, reconnect count, source FPS/status
        |
        | on_frame(camera_id, frame)
        v
MultiCameraPipelineManager
  - one bounded ThreadPoolExecutor (default one worker, maximum four)
  - one in-flight submission per camera
  - cadence gate (default 5 inference FPS)
  - new capture frames are dropped while a camera is busy
        |
        v
FrameIngestionService.process_frame(camera_id, frame)
  |
  +--> MultiModelDetector
  |      +--> general YOLO detector
  |      +--> optional custom weapon detector
  |      +--> sampled YOLOE open-vocabulary threat detector
  |
  +--> per-camera ByteTrack
  +--> per-camera track history, motion, behavior, crowd analysis
  +--> per-camera RiskEngine, proximity/weapon association,
  |    weapon-aggression, threat fusion, SituationIntelligence, zones
  |
  +--> APIState current tracks/statistics/events
  +--> per-track durable Observation records (synchronous SQLAlchemy session)
  +--> event/alert policy, JPEG keyframe snapshot, durable Event record
  |    and IncidentCorrelationService
  |
  +--> REST: cameras, tracks, events, alerts, evidence, intelligence
  +--> WebSockets: global state (500 ms), camera frame preview, camera events
  +--> Next.js authenticated `/api/backend` proxy and dashboard
```

### Components already present

| Area | Existing implementation | Audit finding |
|---|---|---|
| Ingestion | OpenCV/FFmpeg `VideoCapture`, browser JPEG upload, uploaded video, local devices, HTTP/RTSP, YouTube support | Active source lifecycle is solid for a demo; source decoding is still OpenCV-thread based. |
| Backpressure | Per-camera in-flight coalescing and cadence throttling in `aegis/camera/manager.py` | Correct real-time preference: newest frame wins. It is not a queue-based multi-stage pipeline yet. |
| Detection | YOLO general detector, optional weapon detector, optional sampled YOLOE threat detector | Multiple inference passes occur serially in one worker. |
| Tracking | Active per-camera `supervision.ByteTrack`; DeepSORT exists only for the legacy pipeline | Good CPU-first default; no ReID on the active path. |
| Behaviour | Track history, motion, loitering, movement anomaly, crowd metrics, proximity and weapon association | Temporal signals exist and are deliberately evidence-based. |
| Risk | RiskEngine plus `SituationIntelligence`, confidence persistence and reason codes | Good foundation; calibration and time-based windows need measured tuning. |
| Event/incident | Alert cooldowns, idempotent events, observations, snapshots, durable incident correlation | Stronger than a frame-by-frame alert feed, but hot-path I/O needs isolation. |
| Evidence | High-risk JPEG snapshot; standalone raw-frame pre-buffer recorder | Snapshot is active. The circular recorder is currently not connected to the live ingestion path. |
| Camera health | online/offline/reconnecting/error, frames, dropped frames, reconnections, source FPS, resolution, last frame | Useful operator health, missing per-stage latency/frame-age/queue and GPU telemetry. |
| APIs | FastAPI REST, secured WebSockets, health/readiness, metrics endpoint, Next.js proxy | Global WS currently sends full state at a fixed cadence. |
| Persistence | PostgreSQL in Compose, SQLAlchemy pooling, Alembic migrations, Redis available | Per-track observation writes are synchronous in the vision worker; Redis is not the active video work queue. |

## 2. Concurrency, data flow, and current safeguards

### What is already done well

- The camera manager permits only one in-flight inference task per camera. It refuses a new task while the previous one is still running, so latency cannot grow into an unbounded per-camera backlog.
- `BaseCameraSource` maintains a separate compact preview JPEG and uses `CAP_PROP_BUFFERSIZE = 1` where supported. Preview encoding is throttled and no longer forces every captured frame through JPEG encoding.
- Camera sources run independently in capture threads. Failed reads trigger reconnect state with exponential backoff; source errors do not directly terminate other sources.
- The active tracker, track histories, risk engines, zone configuration, threat fusion, and situation state are keyed by camera ID. Camera removal/reset clears these per-camera maps and starts a new source epoch, avoiding false continuity across a restart.
- Recent event and detection memory buffers are bounded deques. Event persistence is idempotent through public event IDs; incident correlation merges compatible durable events.
- Model construction is lazy and detector construction is guarded by a lock, so the active detector is not reloaded once per frame.

### Important implementation distinction

`aegis/pipeline/ai_pipeline.py` exposes a separate 16-worker legacy polling pipeline with DeepSORT, while FastAPI uses the newer coalesced manager described above. A second legacy camera manager also remains at the end of `aegis/video/camera_sources.py`. This duplication is a maintenance and demo-risk issue: future work can accidentally improve or configure an inactive path.

## 3. Ranked bottlenecks and engineering issues

Severity reflects the active path and present CPU-only container deployment, not a hypothetical future GPU cluster.

| Rank | Problem and code evidence | Impact | Recommended fix | Difficulty | Expected benefit |
|---|---|---|---|---|---|
| **CRITICAL** | CPU-bound vision runtime: live API used ~293% CPU, yet CUDA unavailable and Compose has no GPU device request. `DetectionSettings.half_precision` defaults false. | Inference competes with API, voice, JPEG work and DB work; multi-camera capacity is poor. | First enable NVIDIA Container Toolkit/device reservation on a GPU host; verify model device at startup. Then benchmark FP16 at fixed accuracy/latency gates. | Medium | Largest throughput and tail-latency improvement on NVIDIA hardware. |
| **CRITICAL** | `FrameIngestionService._persist_frame_observations` opens a SQLAlchemy session per processed frame and performs a create-or-get operation for every track and association. | Inference worker waits on PostgreSQL round trips; dense scenes multiply writes and may create camera latency. | Put observation/event persistence behind a bounded, idempotent writer queue or batch insert worker. Keep alert decision in-memory and expose persistence lag/degradation. | Medium | Major tail-latency reduction; predictable load as cameras scale. |
| **HIGH** | `MultiModelDetector.detect` serially calls general YOLO, optional weapon YOLO, and sampled YOLOE in the same camera worker. | CPU time rises sharply when the open-vocabulary detector is enabled; one global worker serializes cameras by default. | Instrument each pass. Run YOLOE only on a gated crop/candidate schedule, never as an always-on parallel detector until benchmarks justify it. | Medium | High CPU reduction without removing general detection. |
| **HIGH** | `aegis/api/routes/cameras.py` sends camera previews as JSON data URLs (`frame_to_data_url`) on every WS interval; base64 expands JPEG payload by about one-third. | More CPU allocation, bandwidth, GC, and DOM image churn; every connected viewer gets a copy. | Keep JPEG binary. Serve latest preview by HTTP with ETag/cache-busting or send binary WS frames plus a compact JSON metadata channel. | Medium | 25–35% less image transport payload, smoother multi-viewer preview. |
| **HIGH** | High-risk snapshot JPEG encoding/writing and event persistence occur in the inference worker (`_save_event_snapshot`, `_persist_event`). | An alert burst raises vision latency exactly during an incident. | Use a bounded evidence job queue; copy/retain only required frame references and write asynchronously with an explicit failed/deferred status. | Medium | Better incident-time responsiveness and isolation. |
| **HIGH** | The active cadence gate skips the entire `process_frame`; therefore detection, tracker update, motion, and risk all run only at inference cadence. | It is frame dropping, not independent detector/tracker scheduling. With a low cadence, motion detail and tracker aging degrade. | Split capture/lightweight motion/tracker prediction from detector cadence. Use timestamps rather than assumed FPS for all temporal thresholds. | High | Lower detector cost while preserving temporal quality. |
| **HIGH** | ByteTrack is configured with `frame_rate=30` and a 30-frame lost buffer while the active manager can process 1–10 FPS (and is currently tuned lower). | Lost-track duration and ID persistence can be wrong in wall-clock time, especially after adaptive rate changes. | Derive tracker age from measured processing FPS or choose time-based expiry at the integration layer; benchmark before retuning thresholds. | Low–Medium | Fewer premature/overlong tracks and better risk histories. |
| **HIGH** | Global `/ws` sends full tracks, events, statistics and status every 500 ms per client; `ConnectionManager.broadcast` awaits sends while holding its lock. | Fan-out cost grows with clients; a slow socket can delay shared broadcasts. | Use revisioned deltas, per-client bounded outbound queues, slow-client drop policy, and separate event priority from telemetry. | Medium | Better dashboard scale and failure isolation. |
| **MEDIUM** | Full frame copies occur for latest source frame (`frame.copy()`), `get_frame()` returns another copy, and browser input decodes base64 JPEG to NumPy. | Expected safety copies, but expensive at 1080p/30 FPS. | Measure copy time first; use immutable latest-frame ownership or a small buffer pool only where profiling proves it matters. | Medium | Moderate CPU/RAM improvement; avoid unsafe premature optimization. |
| **MEDIUM** | `ByteTrackTracker._track_metadata` is retained by ID and is not pruned when tracks die; `_emitted_detection_events` is a process-lifetime set. | Long-running cameras can accumulate metadata/event keys. | Prune metadata after tracker expiry and use TTL/LRU maps keyed by `(camera, epoch, track/event)`. Export size gauges. | Low | Prevents slow memory growth. |
| **MEDIUM** | Per-camera camera event WS maintains an unbounded `sent_event_ids` set for each long-lived connection. | Gradual client memory growth. | Use a capped LRU/TTL event-ID set and resync cursor on reconnect. | Low | Predictable long-lived client memory. |
| **MEDIUM** | RTSP uses OpenCV `VideoCapture` with timeouts/buffer hint and reconnect loop. It lacks packet timestamps, decode telemetry, codec control, and verified hardware decode. | Some cameras will have recoverability/latency issues that cannot be diagnosed. | Pilot the already-installed PyAV for one RTSP source; compare time-to-first-frame, reconnect, frame-age and CPU before migration. | Medium | Better diagnostics and potentially lower latency/reliability gains. |
| **MEDIUM** | Metrics endpoint exposes only vehicle-enrichment Prometheus metrics; camera health does not publish decode/inference/tracking/risk/WS latency. | No way to prove improvements or tune adaptive logic. | Add lightweight stage timers and gauges first; do not add a monitoring stack until metrics are useful. | Low–Medium | Enables data-driven tuning and a strong demo screen. |
| **MEDIUM** | `RiskRecorder` keeps raw BGR frames and copies them into both the ring buffer and recording list. It is not live-wired. | If enabled naively at 720p/30, a 5-second raw buffer is roughly 400 MB per camera before recording duplication. | Do not wire it as-is. Design an encoded-packet ring buffer or a bounded JPEG/keyframe fallback with explicit forensic tiering. | High | Enables pre/post-event evidence without memory collapse. |
| **LOW** | `BaseCameraSource.get_frame()` copies data even though the active manager passes frame directly from capture callback. | API/legacy callers may pay a copy unnecessarily. | Retain for thread safety unless profiling identifies a live caller; document ownership. | Low | Small. |
| **LOW** | Readiness validates model files/importability, not model warmup/device/latency. | A “ready” service can still suffer first-inference delay or run on CPU unexpectedly. | Add an optional warmup/readiness phase with deadline and device report. | Low | Cleaner deployment diagnosis. |

## 4. Detection, tracking, and temporal intelligence

### Current tracker position

The active path is `supervision.ByteTrack`: a fast, detection-driven, IoU/motion tracker with per-camera isolation. It is the correct baseline for the current CPU-constrained demo. The repository includes a DeepSORT wrapper, but that wrapper belongs to an inactive legacy pipeline. It is not evidence that ReID is active in production.

ByteTrack will struggle with extended occlusion, similar-looking people crossing, re-entry after leaving view, and moving cameras. The current metadata restoration also uses per-frame class plus IoU matching, so crowded same-class scenes should be specifically evaluated.

### Tracker recommendation

Keep ByteTrack as the default until a labelled benchmark proves a measurable failure mode. Evaluate in this order:

1. **Current ByteTrack, correctly time-calibrated** — baseline; lowest CPU/GPU cost.
2. **Ultralytics BoT-SORT without ReID** — candidate if camera motion compensation or association quality reduces ID switches.
3. **BoT-SORT with ReID, only for selected cameras or escalated scenes** — candidate for sustained occlusion/re-entry; higher GPU/memory/maintenance cost.
4. **Deep OC-SORT / TrackTrack** — only after the above show a gap and licensing/runtime support are validated.

Do not select a tracker from marketing claims. Use sequences representing: crossings, partial/full occlusion, dense queues, rapid running, people leaving/re-entering, low light, and camera shake. Score HOTA/IDF1/ID switches/fragmentation plus end-to-end p50/p95 latency and GPU memory. Maintain one deterministic scene set for the competition demo and one realistic stress set.

**No tracker benchmark is claimed in this audit.** The repository has tests but no labelled MOT corpus, ground-truth annotations, or reproducible benchmark harness for the listed candidates. Producing comparative accuracy numbers without those inputs would be misleading. The first roadmap item below establishes that harness.

### Adaptive inference design

The existing manager already has a fixed per-camera inference cadence and latest-frame coalescing. Evolve it into a measured controller, not a collection of frame-skip constants:

| Scene state | Detector target | Light path | Exit condition |
|---|---:|---|---|
| Calm | 5–8 FPS | capture health + low-cost frame-difference/motion score | sustained movement, new object candidate, zone entry |
| Normal | 10–15 FPS | tracker/risk/history at capture or motion cadence | threat/rapid proximity/high risk trend |
| Escalated | 20–30 FPS if hardware supports it | detector + tracker + evidence jobs prioritized | sustained quiet period and confidence decay |

Use an EWMA of **measured frame age and inference time**, and never increase target FPS beyond current service capacity. Keep a maximum queue age; if an input is older than that threshold, drop it and increment a metric. The scheduler should be per camera, with a global budget so one noisy stream cannot starve voice/API traffic.

### Motion and pose

Motion analysis currently comes from tracked bounding-box history; it is useful but will miss short interactions when detector cadence is low. Add lightweight frame-difference or sparse optical-flow only as a trigger/quality signal, not a violence classifier. It can detect scene motion, sudden acceleration proxy, camera shake, and whether to increase detector cadence.

Pose is currently explicitly unavailable in the model capability response. If added, use the existing Ultralytics ecosystem first and run pose **only** for selected person crops after a temporal-risk or close-proximity trigger. Pose may contribute observable features (fall-like orientation change, arm velocity, ground posture), but must never independently emit “violence.”

Recommended fusion is evidence based:

```text
temporal risk = calibrated base risk
              + persistent threat/weapon evidence
              + tracked proximity / decreasing distance
              + measured motion acceleration or interaction signal
              + optional pose cue
              + zone context
              - confidence/quality penalties
```

Every term must record source, timestamp, subject IDs, duration, and missing-evidence status. This aligns with the repository’s existing reason codes and avoids claims about intent or guilt.

### Temporal confidence and false-positive control

`SituationIntelligence` already smooths score decay and retains short track state; alert policy requires confirmed signals and uses cooldowns. Improve this with wall-clock temporal windows (1, 3, 5, 10 seconds) rather than processed-frame counts:

- promote only after a minimum persistence duration and signal diversity;
- use hysteresis: higher threshold to enter than to remain in an elevated state;
- decay score when evidence expires, with a visible reason;
- keep candidate detections separate from verified operational alerts;
- calibrate thresholds per camera/zone only from labelled evaluation data;
- measure false positives per camera-hour and alert precision/recall, not only detector mAP.

## 5. Event deduplication, incidents, and evidence

The active path has meaningful safeguards: alert cooldown keys, an in-memory detection-event set, idempotent durable event IDs, and `IncidentCorrelationService` that merges compatible events. This is already closer to the desired “Incident #A102” behavior than repetitive one-frame notifications.

Improve it by formalizing an incident state machine:

```text
candidate -> active -> acknowledged / under_review -> resolved / false_positive
                  |             |
                  +--- updates--+--- merged observations, timeline, evidence
```

Use camera ID, source epoch, stable person IDs, spatial proximity, event family, and a time window to update an existing incident. Store event updates as a timeline rather than duplicating alert text. Keep the existing durable IDs; do not invent a second correlation identity scheme.

### Evidence tiers

| Tier | Intended use | Suggested form |
|---|---|---|
| Thumbnail | timeline/list UI | 320 px WebP/JPEG, generated asynchronously |
| Preview | operator modal/dashboard | 720 px JPEG/WebP, HTTP/binary delivery |
| Forensic original | review/export | original-resolution JPEG/keyframe or retained stream packet; immutable metadata/checksum |

The high-risk snapshot is currently a full-frame JPEG written synchronously at quality 85. It is appropriate as a fail-safe keyframe but should be moved off the vision worker. Never replace the forensic original with an aggressively compressed thumbnail.

### Pre/post-event video buffer

The repository has a `RiskRecorder` with a five-second raw-frame circular buffer and asynchronous `VideoWriter`, but no active call from `FrameIngestionService`. Do not simply connect it: raw BGR buffering and duplicate copies are too memory-intensive at realistic resolutions.

Preferred design:

1. RTSP/FFmpeg/PyAV source owns a small **encoded packet** ring, timestamped by presentation time.
2. Incident start pins 5–10 seconds before trigger, continues through incident, then retains 5–10 seconds after stabilization.
3. A bounded mux/write worker creates a clip without re-encoding where codec/container permits; otherwise it uses controlled, timestamp-correct transcode.
4. If encoded packets are unavailable, use a lower-FPS JPEG fallback with an explicit `evidence_quality=degraded` marker.
5. Evidence writer failures must not block inference; expose pending/failed clip status to the dashboard.

## 6. Video, image, and frontend transport

### Current behavior

- Source previews are JPEG-encoded once at a throttled rate and retained as bytes.
- Camera WebSockets wrap those bytes into base64 data URLs inside JSON.
- Browser webcam capture draws a camera frame onto Canvas, calls `toDataURL('image/jpeg', 0.72)`, and POSTs it every 200 ms (maximum 5 FPS) while a request is not pending.
- The dashboard uses `<img>` for received data URLs and REST/WS schemas for tracks/events.

### Recommendations

1. Preserve the current 640-pixel, 5-FPS browser capture as a demo-safe fallback, but provide a binary upload path (`Blob`/`ArrayBuffer`) before increasing any browser FPS.
2. For remote previews, test HTTP latest-image endpoints with conditional requests versus binary WS. Keep JSON only for metadata/detections.
3. Keep JPEG initially. Benchmark WebP at thumbnails/previews; AVIF is generally unsuitable for low-latency live preview due to encode cost and latency variability.
4. Add client-side frame replacement: discard an older image decode if a newer frame arrives; never queue stale images in React state.
5. Send detection deltas keyed by frame ID rather than repeating the complete current state to every dashboard client.

## 7. Library and technology assessment

| Library/technology | Recommendation | Why | Cost / maintenance / licensing notes |
|---|---|---|---|
| **PyAV** | Pilot for RTSP ingest; it is already pinned in `requirements.txt`. | Packet timestamps, FFmpeg codec controls, encoded ring-buffer path, and richer reconnect diagnostics are measurable benefits. | Moderate integration work. Keep OpenCV fallback until pilot proves better time-to-first-frame/reconnect/frame age. LGPL/GPL implications depend on FFmpeg build/distribution; verify packaging. |
| **FFmpeg process** | Consider only behind a source abstraction after PyAV pilot. | Mature decoding, remuxing and hardware paths. | Operational process supervision and cross-platform packaging burden. |
| **GStreamer** | Not now. | Powerful for large multi-camera/media deployments. | High platform/plugin complexity; unjustified before PyAV benchmark shows a need. |
| **TurboJPEG** | Benchmark-only optional dependency. | Could lower JPEG encode CPU for preview/evidence. | Native binary dependency; do not add unless profiling shows `cv2.imencode` is material. |
| **WebP** | Use for thumbnails/preview after browser/network test. | Better size at comparable visual quality. | Encode cost; retain JPEG/original evidence. |
| **AVIF** | Do not use for live preview. | Excellent storage compression, but poor fit for low-latency encode path. | High encode latency/operational variability. |
| **Ultralytics pose model** | Conditional secondary signal; no new framework initially. | Reuses the existing model ecosystem and integration patterns. | GPU cost and model licence terms must be checked for intended deployment. |
| **BoT-SORT/ReID** | Benchmark candidate, not default migration. | May help occlusion and re-entry. | ReID adds GPU latency/memory, model licensing and calibration burden. |
| **ONNX Runtime/TensorRT** | Defer until GPU pass-through and baseline profiling are fixed. | Potentially high benefit on supported NVIDIA deployment. | Build/version/hardware coupling; benchmark against current PyTorch FP16 first. |
| **Redis Streams** | Do not introduce for the local demo yet. | Redis is available, but an event broker will not make inference faster by itself. | Adds worker/retry/ordering semantics. Consider when moving vision to separate processes/nodes. |
| **WebRTC/HLS** | Do not migrate previews now. | Their benefits are real at scale, but the dashboard needs compact operational previews, not broadcast streaming. | Adds signaling/media server or segment-latency complexity. |

## 8. GPU and compute roadmap

Before model conversions, fix deployment topology:

1. Run on an NVIDIA-capable host with a compatible driver and NVIDIA Container Toolkit.
2. Add an explicit Compose GPU reservation/device request and a startup diagnostic reporting GPU name, CUDA availability, model device, precision, and memory.
3. Establish CPU FP32 baseline and GPU FP32 baseline at the same model/input/confidence/camera scene.
4. Test GPU FP16; reject it if confidence/ID/risk outcomes regress beyond a defined tolerance.
5. Test batching only across contemporaneous cameras and only with a maximum wait budget (for example 10–20 ms). Do not trade incident latency for throughput blindly.
6. Evaluate ONNX/TensorRT only after PyTorch GPU FP16 metrics show inference is the dominant remaining stage.

`torch.compile`, pinned memory, and CUDA streams are optimizations to evaluate after the above. They are not substitutes for exposing a GPU to the container.

## 9. Observability and camera health

The existing health surface has the right operational states—online, reconnecting, error/offline—and reports source frame statistics. Extend it with a small internal metrics layer before adding dashboards/infrastructure.

Minimum metrics, labelled by **camera ID only where cardinality is controlled**:

| Metric | Type | Purpose |
|---|---|---|
| `camera_capture_fps`, `camera_decode_fps` | gauge | distinguish source failure from pipeline saturation |
| `frame_age_ms` at inference start | histogram | enforce newest-frame real-time behavior |
| `inference_latency_ms` by model stage | histogram | size GPU/CPU budget and adaptive schedule |
| `tracking_latency_ms`, `risk_latency_ms`, `evidence_enqueue_ms` | histogram | identify non-model hot paths |
| `camera_inflight`, `persistence_queue_depth`, `evidence_queue_depth` | gauge | backpressure visibility |
| `frames_dropped_total` by reason | counter | distinguish cadence drops, stale drops, decode failures |
| `active_tracks`, `tracker_metadata_entries` | gauge | detect leaks/scene load |
| `ws_clients`, `ws_payload_bytes`, `ws_send_latency_ms` | gauge/histogram | dashboard scale visibility |
| `gpu_utilization`, `gpu_memory_bytes` | gauge | validate actual GPU use |

The existing Prometheus endpoint can export these metrics. Keep it protected as it is now; do not label metrics with person IDs, event IDs, URLs, or textual reasons.

## 10. Reliability and isolation design

Maintain these boundaries:

- **Capture:** one source failure changes only that source’s state/reconnect loop.
- **Vision:** one camera task failure must release its in-flight flag, record a stage error, and not stop other cameras.
- **Persistence/evidence:** bounded asynchronous jobs; failure marks evidence pending/failed but does not block alert publication or detector loop.
- **WebSocket:** each client owns a bounded output queue; slow/disconnected clients are dropped without delaying other clients.
- **Model sidecars:** YOLOE, pose, OCR, semantic/vehicle enrichment must have their own budgets and circuit breakers; general person detection must remain available when a sidecar fails.
- **Lifecycle:** every reset explicitly clears only its camera-scoped tracker/history/risk state and increments source epoch, which the active code already begins to do.

## 11. Competition-impact improvements

### Both high engineering and demo impact

- A truthful **camera health and latency panel**: online/degraded/offline, source FPS, inference FPS, frame age, GPU/CPU mode, and dropped-frame reason.
- A single persistent **incident timeline** that shows candidate → verified → operator state, subjects, reason codes, and elapsed duration rather than repeated alerts.
- **Pre/event/post clip evidence** with a clear “recording/pending/ready” status.
- Stable person IDs and short trajectory traces, demonstrated on a prepared crossing/occlusion video.
- Explainable multi-signal risk card: observed threat evidence, proximity, motion, zone, persistence and uncertainty—not a claim of intent.
- Adaptive-inference visual: operator sees the system increase review cadence when risk rises, alongside measured latency.

### High demo impact with lower engineering risk

- Use a known good prerecorded RTSP/uploaded sequence as fallback for live demonstrations.
- Present verified model capabilities truthfully: “candidate,” “confirmed,” and unavailable sidecars should be visibly distinct.
- Add a one-screen demo telemetry overlay sourced from real counters, not simulated numbers.

## 12. Performance benchmarks to run

Run each test after a warmup, for at least 10 minutes per configuration, recording p50/p95/p99 and maximum frame age. Keep model weights, scene, resolution, confidence thresholds, and host fixed.

| Benchmark | Matrix | Acceptance decision |
|---|---|---|
| End-to-end camera capacity | 1, 2, 4, 8 cameras; 720p and 1080p; calm/dense clips | no unbounded latency; p95 frame age stays within operator target |
| Per-stage latency | general YOLO, weapon, YOLOE, tracker, risk, persistence, snapshot | optimize the largest measured contributors only |
| GPU enablement | CPU FP32 vs GPU FP32 vs GPU FP16 | adopt only if accuracy and p95 latency meet gates |
| Adaptive inference | fixed 5/10/15 FPS vs scene controller | lower compute with no missed labelled incident window |
| Tracker | ByteTrack vs BoT-SORT (then optional ReID) on labelled sequences | select on IDF1/HOTA/ID switches *and* p95 latency |
| RTSP decode | OpenCV/FFmpeg vs PyAV pilot | choose based on reconnect, time-to-first-frame, frame age, CPU |
| Preview transport | data URL JSON vs binary WS vs HTTP JPEG/WebP | choose lowest bytes/CPU with acceptable visual latency |
| Persistence soak | dense tracks + event burst + DB delay injection | vision remains live; queue stays bounded; evidence status truthful |
| Incident accuracy | labelled normal/loitering/running/zone/threat interactions | report alert precision, recall, duplicate rate and mean time-to-alert |

## 13. Prioritized implementation roadmap

| Priority | Improvement | Benefit | Complexity | Risk | Demo Impact |
|---|---|---|---|---|---|
| P0 | Add per-stage timing, frame-age, drop-reason, queue-depth and device metrics | Makes every later decision evidence based | Low–Medium | Low | High |
| P0 | Enable/verify NVIDIA GPU pass-through where hardware is available | Removes current CPU bottleneck | Medium | Medium | High |
| P0 | Add tracker/inference/transport benchmark harness and labelled demo clips | Prevents speculative replacements | Medium | Low | High |
| P1 | Move observations, event persistence and snapshot writes to bounded workers | Protects inference latency during dense scenes/incidents | Medium | Medium | High |
| P1 | Calibrate ByteTrack wall-clock ageing to measured cadence | More stable IDs and temporal evidence | Low–Medium | Medium | High |
| P1 | Compact preview transport (binary or HTTP latest image) and WS deltas | Reduces bandwidth/GC and viewer scale cost | Medium | Low | Medium |
| P1 | Pilot PyAV for one RTSP source with concrete success criteria | Better timestamps/reconnect path and enables encoded buffer | Medium | Medium | Medium |
| P2 | Build encoded pre/post-event evidence buffer and incident timeline clips | Operationally valuable evidence and excellent demo | High | Medium | Very high |
| P2 | Adaptive inference controller with global compute budget | Lower cost while preserving escalation responsiveness | High | Medium | High |
| P2 | Evaluate BoT-SORT/ReID only from benchmark results | Addresses demonstrated identity failures | Medium–High | Medium | Medium |
| P3 | Add gated person-crop pose cues | Improves multi-signal evidence in selected scenes | Medium–High | High | High |
| P3 | Remove or quarantine inactive legacy pipeline implementations | Reduces maintenance/configuration mistakes | Medium | Medium | Low |

## Top 10 recommended changes

1. Instrument the existing active pipeline before changing algorithms.
2. Make GPU availability a deployment gate; the current container is CPU-bound despite a CUDA build.
3. Move per-track SQL writes and JPEG snapshot work off the vision worker with bounded, observable queues.
4. Reconcile ByteTrack time settings with real processed FPS and measure identity quality on representative clips.
5. Replace base64 JSON preview images with a compact binary/HTTP delivery experiment.
6. Create a reproducible benchmark harness for end-to-end latency, trackers, detector cadence, and false positives.
7. Pilot PyAV only for RTSP after defining a measurable success criterion; retain OpenCV fallback.
8. Implement an encoded pre/post-event evidence buffer instead of wiring the existing raw-frame recorder directly.
9. Use adaptive inference with a global compute budget and wall-clock temporal windows.
10. Add pose only as a gated, secondary, explainable signal after the above foundations are measured.

## Decisions explicitly not recommended now

- Do not rewrite the active camera manager around a new framework.
- Do not replace ByteTrack with a ReID tracker without labelled evidence of a material ID problem.
- Do not migrate all preview video to WebRTC, HLS, GStreamer, or AVIF for a competition demo.
- Do not use pose, optical flow, weapon candidates, or a single frame to classify violence or infer intent.
- Do not add Redis Streams, TensorRT, or a new observability platform before their measured bottleneck and operational ownership are clear.

## Audit evidence locations

- Active camera manager and cadence/coalescing: `aegis/camera/manager.py`
- Active source capture, preview JPEG, reconnects: `aegis/camera/base.py`
- Active ingestion/detection/risk/events/persistence: `aegis/video/camera_sources.py`
- General/multi-model detection: `aegis/detection/yolo_detector.py`, `aegis/detection/multi_model_detector.py`
- Active tracker: `aegis/tracking/bytetrack_tracker.py`
- Temporal situation reasoning: `aegis/risk/situation_intelligence.py`
- Incident correlation and repositories: `aegis/intelligence/incident_correlation.py`, `aegis/database/repositories.py`
- Recorder prototype: `aegis/recording/risk_recorder.py`
- API/preview/global WebSockets: `aegis/api/routes/cameras.py`, `aegis/api/websocket.py`
- Frontend browser/preview transport: `frontend/src/components/cameras/browser-webcam-capture.tsx`, `frontend/src/components/cameras/camera-preview.tsx`
- Runtime/deployment configuration: `docker-compose.yml`, `aegis/settings.py`, `requirements.txt`

