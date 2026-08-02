# Intelligence Page Capability Audit

**Scope:** source-level audit of the current `/intelligence` page, related FastAPI routes, AI orchestration, pipeline, persistence, WebSockets, and tests.  
**Assessment:** Advanced Prototype / Pre-Production.  
**Method:** traced frontend render paths to network clients, FastAPI handlers, state/persistence code, and test coverage. This is not a production-load or model-quality validation.

## Executive finding

The page is a compelling visual prototype, but it is not yet a dependable intelligence copilot. It mixes real read paths with hard-coded operational claims, derived-but-uncalibrated values, decorative controls, and a text-generation path whose citations, confidence, and proposed actions are not verified after the LLM responds.

The strongest implemented foundations are: camera/frame ingestion, active in-memory API state, YOLO/tracking/risk components, a transparent live-evidence semantic query engine, and a read-only AI context collector. The largest blockers are the absence of a typed unified context contract, no Intelligence-page WebSocket consumer, no investigation workflow or audit trail, unsafe browser-key guidance, and UI states that report capabilities rather than their actual availability.

## 1. Repository audit

### 1.1 Intelligence page truth table

| UI component | Current frontend source | API / data source | Real / partial / mock / broken | Evidence | Required action |
| --- | --- | --- | --- | --- | --- |
| Page shell and “AI Security OS” label | `frontend/src/app/intelligence/page.tsx`, `IntelligencePage` | None | Mock/decorative | Static strings and animation-only layout. | Label as prototype until status/capability data is attached. |
| Header clock | `IntelligencePage`, `currentTime` effect | Browser clock | Real, local only | Updates every 60 seconds with `new Date()`; not a service freshness timestamp. | Keep as local time, but add separately sourced `context.generated_at` and per-source freshness. |
| Cameras Online | `StatBar`; `useCoreStatus` | `GET /api/ai/metrics` -> `ai_system_metrics` -> `get_camera_status` | **Broken for online count; partial total** | `aegis/ai/tools.py:get_camera_status` instantiates `CameraRegistry` and checks `getattr(config, "status", "")`; `aegis/camera/types.py:CameraConfig` has no `status` field. Configured cameras are therefore counted as non-online. | Source runtime status from `CameraManager` / `CameraRuntimeStatus`, return `online`, `offline`, `stale`, and freshness in a typed contract. |
| Active Incidents | `StatBar`; `useCoreStatus` maps `alerts_today` to `activeIncidents` | `GET /api/ai/metrics` -> `get_active_alerts` | Partial / mislabeled | `get_active_alerts` reads the in-memory `AlertingStage` event deque and filters `type == "risk_alert"`; `/metrics` calls this “alerts_today”. There is no Incident model/workflow and no date filter. | Rename to “active risk alerts” until an incident model/state machine exists; do not call it incidents or daily count. |
| System Health | `useCoreStatus` | `GET /api/ai/metrics` -> `get_system_health` | Partial, misleading presentation | `useCoreStatus` converts only DB/pipeline string values into arbitrary 98/85/60 percentages. `StatBar` always says “All Systems Normal.” `get_system_health` does perform DB, Redis, pipeline, and model checks. | Return component checks and a computed documented health policy from backend; render degraded reasons rather than a fixed reassuring subtitle. |
| Officers Online | `useCoreStatus` | None | Mock/unavailable | Set to `0` with comment “No officer tracking yet.” No identity, shift, or staffing source is wired. | Remove the card or render “Not available” until a separately authorised operations/staff system exists. |
| AI Confidence badge | `StatBar`; `useCoreStatus` | Derived from pipeline string, not AI evidence | Mock | Hard-coded initial `92`; subsequently `92` when pipeline is “running”, else `70`; badge always says “High.” `AIOrb` receives `confidence` but does not use it. | Remove global AI confidence. For each answer show retrieval coverage, evidence count/freshness, and calibrated model confidence only when validated. |
| AI assistant greeting and external-link icon | `SuggestionsPanel` | None | Mock/broken | “Hello Hassan” is hard-coded. `ExternalLink` is an icon, not a link or button action. | Use authenticated display name or neutral greeting; remove/implement the link. |
| AI suggestions | `useAISuggestions`; `SuggestionsPanel` | `GET /api/ai/suggestions` | Partial, with mock fallback | Server derives offline-camera, risk-alert, and health suggestions through `aegis/ai/tools.py`; but it always pads with “Export daily report” and “Search security events”. Client also replaces empty server data with hard-coded prompts. Clicking sidebar suggestions directly calls chat and TTS, bypassing chat history and `onAction`. | Return only evidence-backed suggestions with evidence refs and capability/availability; remove client and server default suggestions, or visibly label non-executable examples. |
| Suggestion “Export daily report” | `aegis/ai/routes.py:ai_suggestions`; click handler in `SuggestionsPanel` | Chat only | Broken claim | `generate_incident_report` only constructs a dictionary; no report file/export action is exposed by this flow. | Remove until a reviewed report endpoint and operator confirmation exist. |
| AI activity feed | `useIntelligenceFeed`; `ActivityFeed` | Polls `GET /api/ai/context` every 15 seconds | Partial with synthetic fallback | Context reads alerts/recent events. When empty, client injects “System Status ... timestamp: Now”; errors are silently swallowed. Feed IDs use `Date.now()`, and “View all” has no handler. | Subscribe to typed event stream, show source ID/timestamp/camera and empty/offline states; remove synthetic feed row and implement or remove “View all.” |
| Chat input and answer display | `CommandBar`; `sendChatMessage` | `POST /api/ai/chat` -> `ai_chat` -> `AIOrchestrator.process` | Partial | Real request/response path exists and the server collects read-only system context. Messages live only in React state; `ChatRequest.conversation_id` is unused and no history is sent despite `AIOrchestrator.process` reading a non-schema `history` attribute. `sources` returned by the API are not shown. | Persist auditable conversation turns; display clickable, permission-checked evidence citations; enforce context and conversation schemas. |
| LLM grounding and citations | `aegis/ai/prompts.py`, `AIOrchestrator._parse_response` | Gemini or `FallbackProvider` | Partial, not enforceably grounded | Prompt instructs the LLM to use verified context, but `_parse_response` accepts LLM-provided answer, source list, actions, and confidence without server-side citation validation. There is no retrieval coverage check. | Generate citations from retrieved records server-side; reject/label unsupported claims; return “insufficient evidence” when evidence is absent. |
| Chat confidence in message bubbles | `CommandBar.processResponse` | `ChatResponse.confidence` | Mock / uncalibrated | `AIOrchestrator._parse_response` defaults missing LLM confidence to `0.85`; no calibration or test validates it. Fallback returns `0.3` or provider returns `0`. | Replace with evidence-quality fields; only expose model confidence after calibration and evaluation. |
| Chat actions | `handleAction` in `IntelligencePage` | LLM `actions` from `/api/ai/chat` | Unsafe/partial | Frontend executes `navigate` with `window.location.href = action.target`; no action allowlist validates target. `open_panel` only sets a visual selected node. The server accepts arbitrary LLM action objects in `_parse_response`. | Server-side action registry with typed parameters, RBAC, audit event, and confirmation policy. Initially allow only read-only navigation. |
| Conversation history | `CommandBar` local `messages` | None | Mock/local-only | Last six messages are rendered only in browser memory; no reload persistence, no `NLQRepository` use, no conversation ID. | Store operator-owned, retention-controlled conversations and tool invocations; support erase/export policy. |
| Voice microphone | `CommandBar.toggleVoice`; `sendVoiceCommand` | Browser `SpeechRecognition` / `webkitSpeechRecognition`; `POST /api/ai/voice` | Partial prototype | It runs continuous browser recognition, sends final transcript, and browser TTS reads response. No wake word, no explicit hands-free toggle, no silence timeout, no explicit permission/privacy policy, no shortcut/emergency stop state model. Browser speech recognition may be cloud-backed. | Do not market as hands-free. Implement the design in section 4 before enabling persistent listening. |
| Voice backend path | `aegis/ai/routes.py:ai_voice` | `VoiceRequest.text` -> `AIOrchestrator.process` | Partial/broken voice specialization | `VoiceRequest.audio_base64` is unused; only transcript is read. `ai_voice` does not pass `voice_mode=True`, so `VOICE_SYSTEM_PROMPT` is unused by this endpoint. | Use a command-session API and pass a typed transcript; keep audio local by default; validate intents/actions. |
| TTS toggle | `CommandBar.speak` and volume button | Browser `speechSynthesis` | Real browser feature, not operational evidence | Speech can read arbitrary model text; selected voice availability varies by browser. `SuggestionsPanel` separately speaks text and does not respect `CommandBar` voice-enabled state. | Make speaking a user preference at page scope and speak only the reviewed answer summary/citations state. |
| Static command chips | `CommandBar.SUGGESTIONS` | Chat endpoint | Mock examples with unsafe implication | Includes “Generate incident report”; all four bypass `handleSubmit` and invoke chat directly. | Replace with evidence-driven suggested read queries, or label as examples and route through one guarded submit path. |
| AEGIS Intelligence Core orb | `AIOrb` | Derived UI status only | Decorative | Canvas particles use `Math.random()` locally; labels and rings have no backend interaction. | Retain as visual identity only if explicitly labelled “visual system map,” not a core status/control. |
| Investigation node | `AGENT_NODES` -> `NodeOrbit` | None | Mock | Constant `{ id: "investigation", status: "active" }`; click only changes CSS state. No investigation route/model. | Disable/link to a future workspace only after Phase 2. |
| Search & Semantic node | `AGENT_NODES`; `NodeOrbit` | None from this page | Partial capability, mock connection | `/semantic/query` and `SemanticQueryEngine.search` exist elsewhere, but this node never calls or navigates to them. | Link to `/semantic` and surface `GET /semantic/stats` availability/freshness. |
| Tracking & Behaviour node | `AGENT_NODES`; `NodeOrbit` | None from this page | Partial capability, mock connection | Tracking/risk code exists (`TrackingStage`, `RiskScoringStage`, `RiskEngine`), but node status is constant and opens no track evidence. | Link to typed tracks/investigation view; display pipeline stage health, not `active`. |
| Risk Assessment node | `AGENT_NODES`; `NodeOrbit` | None from this page | Partial capability, mock connection | `RiskEngine.compute_risk` is deterministic and emits factor explanations; no Intelligence UI exposes factors, weights, model version, or calibration. | Expose explanation/evidence records and model/rule version per risk result. |
| Cameras Management node | `AGENT_NODES`; `NodeOrbit` | None from this page | Partial capability, mock connection | Camera routes and `/ws/cameras/{id}/...` exist, but node is a non-navigating visual state. | Navigate to `/cameras`, show real runtime counts and stale feeds. |
| Incident Management node | `AGENT_NODES`; `NodeOrbit` | None | Mock/unavailable | Alerts exist; no incident aggregate, owner, lifecycle, notes, or evidence bundle is implemented. | Rename to Alerts or hide; build incident domain in Phase 2. |
| Analytics & Insights node | `AGENT_NODES`; `NodeOrbit` | None | Partial capability, mock connection | `/statistics` reports current state and analytics page exists; node has no integration. Insight persistence models exist but no live Intelligence workflow uses them. | Link to `/analytics` and expose only returned metrics/data freshness. |
| Automation & Workflows node | `AGENT_NODES`; `NodeOrbit` | None | Mock/unavailable | No workflow engine/action registry is wired to the page. | Mark unavailable; later implement approved, auditable workflow proposals only. |
| Patrol & Maps node | `AGENT_NODES`; `NodeOrbit` | None | Mock/unavailable | Constant status `idle`; no map, dispatch, or patrol backend/UI found. | Remove from the core until a separate authorised module exists. |
| Knowledge Graph node | `AGENT_NODES`; `NodeOrbit` | None | Mock/unavailable | No graph model, graph API, or graph UI path found. | Remove or label planned; do not claim graph reasoning. |
| Footer system resources | `SystemHealthBar`; `useSystemHealth` | `GET /api/ai/metrics` every 10 seconds | Partial, with misleading initial state | Initial metrics display `...` with `status: "healthy"`; API returns camera/DB/pipeline/GPU/Redis/alert fields but no timestamps. “Updated now” is static. | Initial state must be loading/unknown, then include per-check timestamp and error/degraded reason. |
| GPU footer metric | `useSystemHealth`; `get_gpu_usage` | `torch.cuda` runtime check | Partial | Actual availability/memory is returned when CUDA works, otherwise `N/A`; no sampling timestamp or error reason reaches UI. | Preserve actual values but add freshness and unavailable reason. |
| “Active,” “High,” “All Systems Normal,” “Updated now,” and real-time visual signals | `AIOrb`, `StatBar`, footer; animations | Mixed / mostly local | Mock or overstated | Most labels are static or derived from a coarse poll. Intelligence page opens no WebSocket even though `/ws` exists. | Replace with source-backed state labels: `live`, `stale`, `degraded`, `offline`, or `unavailable`, each with timestamp. |

### 1.2 Backend and data-path observations

1. **The active API state is real but process-local.** `aegis/api/state.py:APIState` keeps tracks, a maximum-100 event deque, status, and statistics under a lock. `aegis/video/camera_sources.py` calls `update_track`, `update_status`, `update_statistics`, and `add_event`. This supports live service output but does not by itself survive restart.
2. **The current pipeline composition is present.** `aegis/pipeline/startup.py:create_pipeline` wires detection, tracking, risk scoring, and alerting stages. `RiskScoringStage.process` calls `RiskEngine.compute_frame_risks`; `RiskEngine` uses explicit weights, thresholds, zone context, and temporal adjustment. Unit tests in `tests/unit/test_risk_engine.py` cover deterministic scoring and explanations.
3. **Alert persistence as wired is broken.** `aegis/pipeline/alerting.py:_persist_event` imports `aegis.database.repositories.EventRepository` then calls `repo.create_event(...)`. That repository defines `create(...)`, not `create_event(...)`; the exception is caught and only debug-logged. Thus this pipeline path does not persist high-risk events through that repository.
4. **The AI fallback event query also has a session defect.** `aegis/ai/tools.py:get_recent_events` passes `get_db_session()` directly to `EventRepository`; `aegis/database/connection.py:get_db_session` is a context manager and must be entered with `with`. The repository receives a context-manager object rather than a `Session`, errors, and returns `[]`. Pipeline-buffer data may mask this while running.
5. **There are parallel persistence stacks.** `aegis/database/models.py` and `aegis/db/models.py` define overlapping Event/Alert/track models against different bases/connection modules. `aegis/db/repository.py` contains `create_event`, while the pipeline imports `aegis.database.repositories`. This ambiguity is a material production risk until one schema/repository is selected and migration-tested.
6. **The semantic evidence engine is a real, conservative rule/query matcher.** `aegis/semantic/query_engine.py:SemanticQueryEngine.search` evaluates current tracks, events, and statistics and returns evidence strings, camera IDs, timestamps, and track/event identifiers when supplied. Tests in `tests/unit/test_semantic_query_engine.py` verify it does not fabricate a red-backpack result and requires a person-weapon association. Its `semantic_confidence` is a deterministic match heuristic, not calibrated visual/model confidence.
7. **The `/semantic` route is usable but terminology is inconsistent.** `aegis/api/routes/semantic.py` exposes live evidence results; route comments still claim Grounding DINO. `aegis/api/app.py:_initialize_semantic_state` initialises `SemanticQueryEngine`, whereas the query engine explicitly says it is separate from Grounding DINO. Product copy must distinguish evidence search from open-vocabulary visual detection.
8. **WebSockets exist but are not an event model for Intelligence yet.** `aegis/api/websocket.py:websocket_endpoint` sends the entire `APIState` snapshot every 500 ms; `broadcast_event` and `broadcast_alert` are defined but source search found no caller. Camera frame/events WebSockets in `aegis/api/routes/cameras.py` poll manager buffers. The Intelligence page uses REST polling only. The generic and camera WebSocket handlers call `accept()` without authentication.
9. **AI endpoint tests are absent.** Repository tests cover risk, semantic matching, some pipeline components, API auth/CORS, and input validation. Source search found no direct tests for `/api/ai/chat`, `/api/ai/voice`, `/api/ai/context`, `/api/ai/metrics`, suggestions, action validation, conversation retention, or WebSocket authorization.

## 2. Capability truth map

| Claimed intelligence capability | What currently works | Inputs | Output | Reliability / limitations | Missing pieces |
| --- | --- | --- | --- | --- | --- |
| Camera ingestion and management | Camera configuration, runtime manager APIs, browser-frame ingestion, camera stream/event WebSockets are implemented. | Configured devices/RTSP/HTTP/browser frames/uploaded video. | Runtime status, snapshots, camera events/detections. | Runtime manager state is distinct from `CameraRegistry`; Intelligence metrics use the registry incorrectly for online status. Camera WebSockets are unauthenticated. | Unified runtime contract, stale-feed policy, auth, monitoring, durable history. |
| Detection | Pipeline has `DetectionStage`; route-level detection buffers exist. | Frames and YOLO weights. | Detections and aggregate stats. | Availability depends on initialized/running pipeline; routes return empty when it is absent. | Model/version telemetry, calibration/quality monitoring, persisted evidence policy. |
| Tracking and behaviour | Tracking, motion/behaviour analysis, object registry fields exist. | Detection tracks/history. | Active tracks with risk-related evidence fields. | APIState tracks are in-memory; action/pose capabilities are explicitly false in `SystemStatus`. Behaviour is not identity or intent inference. | Durable track history tied to recordings, quality tests with real video, operator review UX. |
| Risk assessment | `RiskEngine` produces weighted, explained risk scores; `RiskScoringStage` uses it. | Motion, behaviour flags, crowd metrics, zones, temporal state. | Score, risk level, explanatory factors. | Unit-tested deterministic rules; no calibration/evaluation dataset is shown. UI hides factors and weights. | Versioned configuration, calibration, explanation API, review/override/audit flow. |
| Alerts | Alerting stage creates in-memory event/alert objects and `AlertManager` routes support read/acknowledge. | Risk-stage messages. | Buffered alerts and alert manager summaries. | Different managers/buffers can diverge; high-risk DB persistence path is broken. “Incident” is not implemented. | One durable alert/incident model, ownership, lifecycle, evidence bundle, audited acknowledgement. |
| Persisted operational data | Models/repositories for events, alerts, tracks, recordings, telemetry, and AI-related records exist. | SQLAlchemy SQLite/PostgreSQL. | Potential durable data. | Two overlapping model/repository stacks; audit found broken call/session paths; no end-to-end persistence test for Intelligence context. | Choose one persistence layer, migrations, transactional writes, retention/recovery tests. |
| Semantic evidence search | `SemanticQueryEngine` searches active tracks/events/current statistics; `/semantic/query` and `/semantic/results` work against state when enabled. | Operator prompt plus live APIState evidence. | Evidence matches with IDs, timestamps, risk and evidence text. | Conservative lexical/concept matcher; results are volatile/in-memory, no recording citations; generated match confidence is heuristic. | Durable index, recording/frame refs, authorisation filtering, retrieval evaluation, UI link from Intelligence. |
| AI chat | Authenticated chat reaches `AIOrchestrator`, collects read context, uses Gemini when configured or a safe fallback. | Text message, live context, basic keyword intent. | Structured text, LLM-proposed actions/sources/confidence. | Prompt-only grounding; no citation validation, no conversation persistence, no model evaluation, no RBAC. | Retrieval-backed answers, source validator, action allowlist, audit log, safety/evaluation gates. |
| AI suggestions | Some suggestions are derived from health/camera/alert tools. | Camera config, alert buffer, health checks. | Up to six suggestion strings. | Defaults are generic and may imply unsupported reports/search; no cited evidence or action availability. | Typed recommendation contract with reason/evidence/action policy. |
| Real-time intelligence | `/ws` emits APIState snapshots; event bus and camera sockets exist. | Process-local state and camera buffers. | JSON snapshots/frames/events. | Page does not subscribe; generic socket is unauthenticated and snapshot-based; broadcast helpers unused. | Authenticated event envelope, resume/cursor, backpressure, subscriptions, frontend reconnect/freshness UX. |
| Voice assistant | Browser speech recognition transcript -> voice endpoint -> browser synthesis. | Microphone via browser service and transcript. | Text answer spoken in browser. | No wake word, command session, privacy boundary, confirmation, fallback, or tests; audio is not handled by backend. | Privacy-first local wake word, STT strategy, state machine, intent allowlist, confirmation/audit. |
| Investigation/knowledge/patrol/automation | No working end-to-end capability found for these core labels. | N/A | N/A | Visual nodes are constants and clicks only update UI selection. | Separate product domains and APIs; do not claim them meanwhile. |

## 3. Gap analysis and prioritised roadmap

### Phase 0 — Truth and reliability

#### P0.1: Introduce one typed, source-fresh `IntelligenceContext`

- **Priority:** P0.
- **User value:** operators can tell what is current, unavailable, stale, or degraded.
- **Likely files/services:** new `aegis/intelligence/context_service.py`; `aegis/api/routes/intelligence_context.py`; `aegis/ai/context.py`; `frontend/src/lib/ai-api.ts`; `frontend/src/hooks/useIntelligence.ts`.
- **Backend/data-model changes:** versioned response described in section 5; source timestamps, data provenance, degraded reasons, capability flags; use `CameraManager` runtime state rather than config registry for online counts.
- **Frontend UX:** replace arbitrary score/status copy with check-level state, timestamp, and empty/error/offline panels.
- **Tests required:** contract tests for no pipeline, no database, Redis fallback, offline cameras, stale data, and schema compatibility.
- **Definition of done / acceptance criteria:** one endpoint supplies every Intelligence statistic; no UI metric defaults to “healthy” or numeric data without a source; every displayed value has `observed_at` or is explicitly unavailable.
- **Implementation risk:** medium; it crosses existing duplicated state/persistence paths.

#### P0.2: Remove or accurately label non-functional claims

- **Priority:** P0.
- **User value:** prevents operators acting on a false impression of automation, incident handling, or certainty.
- **Likely files/services:** `frontend/src/app/intelligence/page.tsx`, `hooks/useIntelligence.ts`, `components/intelligence/{NodeOrbit,CommandBar,ActivityFeed}.tsx`.
- **Backend/data-model changes:** none except capability flags from P0.1.
- **Frontend UX:** remove/disable Investigation, Incident Management, Knowledge Graph, Patrol & Maps, Automation, “Hello Hassan,” “All Systems Normal,” fixed “High,” report default suggestions, and inert buttons until backed.
- **Tests required:** component tests asserting unavailable states and no placeholder fallback data; accessibility tests for disabled control explanations.
- **Definition of done / acceptance criteria:** every interaction either uses a named endpoint/action or is visibly marked unavailable; zero hard-coded operational status/confidence/suggestion values remain.
- **Implementation risk:** low technical risk, high product-communication value.

#### P0.3: Repair persistence and unify repositories

- **Priority:** P0.
- **User value:** evidence does not disappear or conflict after restarts.
- **Likely files/services:** `aegis/pipeline/alerting.py`, `aegis/ai/tools.py`, `aegis/database/*`, `aegis/db/*`, `alembic/*`.
- **Backend/data-model changes:** select one SQLAlchemy base/models/repository layer; replace the invalid `create_event` call; use `with get_db_session() as session`; add camera ID/evidence/ref fields and transaction boundaries.
- **Frontend UX:** distinguish live buffer from persisted record; show persistence failure/degraded status.
- **Tests required:** integration test processes a risk event, restarts/recreates state, then retrieves the same event/alert/track evidence; migration tests for SQLite and PostgreSQL.
- **Definition of done / acceptance criteria:** persisted high-risk event, alert acknowledgement, and referenced recording are retrievable by stable IDs; failures are surfaced and measured.
- **Implementation risk:** high because duplicate schema paths may contain legacy callers.

#### P0.4: Establish authenticated event delivery

- **Priority:** P0.
- **User value:** faster, trustworthy live updates without stale polling and without exposing operational data.
- **Likely files/services:** `aegis/api/websocket.py`, `aegis/api/routes/cameras.py`, `aegis/core/events.py`, frontend query/socket hooks.
- **Backend/data-model changes:** authenticated WebSocket handshake/session, event envelope (`event_id`, `type`, `occurred_at`, `source`, `schema_version`), subscriptions/cursors, Redis stream consumer bridge, no full-state 500 ms broadcasts.
- **Frontend UX:** connection state, last event time, reconnection/replay indicator, offline fallback to bounded polling.
- **Tests required:** auth rejection, reconnect/cursor replay, event order/deduplication, backpressure, no cross-user subscription leakage.
- **Definition of done / acceptance criteria:** Intelligence consumes signed/authenticated event events; no generic socket exposes data without authentication; UI renders stale state after defined timeout.
- **Implementation risk:** high concurrency/security risk; ship read-only event types first.

#### P0.5: Secure browser/API integration and add failure tests

- **Priority:** P0.
- **User value:** protects operator and camera data while making failures visible.
- **Likely files/services:** `frontend/src/lib/config.ts`, `.env.example`, `aegis/api/security.py`, API test suite.
- **Backend/data-model changes:** production session/JWT or same-origin gateway; remove requirement for privileged `NEXT_PUBLIC_*` API keys; rate limits/audit context for AI endpoints.
- **Frontend UX:** explicit unauthenticated/forbidden/degraded messages and sign-in/session state.
- **Tests required:** no production browser key configuration, endpoint authorisation, WebSocket authorisation, client error state, API contract validation.
- **Definition of done / acceptance criteria:** no privileged secret is exposed to the browser in production; all `/api/ai/*` and WebSocket calls are authenticated and tested.
- **Implementation risk:** medium; deployment topology decisions are required.

### Phase 1 — Intelligence foundation

#### P1.1: Build evidence-grounded retrieval and citations

- **Priority:** P0 for safety, P1 sequencing after P0 data contract.
- **User value:** answers point to records an operator can inspect.
- **Likely files/services:** `aegis/ai/{context,orchestrator,tools,schemas}.py`, semantic service, event/track/recording repositories, new evidence API.
- **Backend/data-model changes:** retrieve authorised events, alerts, tracks, detections, recordings and health snapshots by stable IDs; create citation objects with camera ID, timestamp, recording/frame URL, freshness, and permission scope.
- **Frontend UX:** citation chips open evidence panels; “insufficient evidence” state; show answer provenance rather than a global confidence score.
- **Tests required:** retrieval precision/recall fixtures, citation resolver test, prohibited unsupported-answer tests, authorisation filtering test.
- **Definition of done / acceptance criteria:** every factual AI answer has one or more resolvable citations or explicitly says evidence is insufficient; server rejects fabricated citation IDs.
- **Implementation risk:** high data quality and access-control risk.

#### P1.2: Replace free-form actions with audited read tools

- **Priority:** P0 safety / P1 delivery.
- **User value:** operators can use assistance without LLM-controlled navigation or system changes.
- **Likely files/services:** `aegis/ai/orchestrator.py`, new `aegis/ai/action_registry.py`, `schemas.py`, frontend action renderer, audit model/migration.
- **Backend/data-model changes:** typed tool/action union for `get_context`, `open_evidence`, `filter_events`, `open_camera`, and `draft_report`; RBAC check and audit record for each invocation.
- **Frontend UX:** actions are labelled proposals with cited impact; read actions may execute, sensitive actions require confirmation.
- **Tests required:** allowlist/denylist, target validation, RBAC, audit persistence, adversarial LLM action payloads.
- **Definition of done / acceptance criteria:** no raw LLM action target reaches `window.location`; every tool call is server-authorised and audit logged.
- **Implementation risk:** medium.

#### P1.3: Make semantic search an evidence service

- **Priority:** P1.
- **User value:** quick search of verified operational evidence without overstating computer vision semantics.
- **Likely files/services:** `aegis/semantic/query_engine.py`, semantic routes, repositories/index job, `frontend/src/app/semantic`, Intelligence links.
- **Backend/data-model changes:** persist searchable evidence, attach recording/frame references, result source/freshness fields, query audit records, and a clear `live_evidence` capability state.
- **Frontend UX:** expose Search & Semantic node as a route to semantic search; show evaluated scope, citations, no-match, engine-disabled, and stale-data states.
- **Tests required:** time-window/camera filters, durable evidence fixture, citation preservation, multilingual/unknown-term false-positive tests.
- **Definition of done / acceptance criteria:** a semantic result always identifies its stored event/track/statistics source and never implies a visual attribute that the evidence does not contain.
- **Implementation risk:** medium; performance/index design must be bounded.

### Phase 2 — Investigation intelligence

#### P2.1: Create the investigation and incident domain

- **Priority:** P1.
- **User value:** turns alerts into operator-owned investigations rather than decorative “incident management.”
- **Likely files/services:** new `aegis/investigations/*`, migrations/models, alert/event/recording routes, `frontend/src/app/investigations/*`.
- **Backend/data-model changes:** `Incident`, `Investigation`, `EvidenceLink`, `OperatorNote`, owner/status/timeline/retention fields; link only operator-selected alerts/tracks/events/recordings.
- **Frontend UX:** timeline, related tracks, camera/recording evidence, notes, evidence bundle, explicit ownership/status; no automatic escalation.
- **Tests required:** lifecycle transitions, RBAC, evidence link integrity, note audit history, retention/export permissions.
- **Definition of done / acceptance criteria:** an operator can create, review, annotate, and close an investigation with all shown evidence retrievable by stable ID.
- **Implementation risk:** high privacy, retention, and workflow-design risk.

#### P2.2: Expose explainable, versioned risk scoring

- **Priority:** P1.
- **User value:** operators can understand why a risk is ranked and assess whether data supports it.
- **Likely files/services:** `aegis/risk/*`, `pipeline/risk_scoring.py`, persistence models, events/tracks APIs, investigation UI.
- **Backend/data-model changes:** persist factor raw/weighted values, zone/temporal adjustments, thresholds, rules/model versions, input timestamps, calibration version, and verification state.
- **Frontend UX:** expandable “why this risk” panel with factors, limitations, source data, stale/unsupported notices, and no person-level conclusions beyond observed evidence.
- **Tests required:** deterministic explanation snapshot tests, version migration, calibration-report checks, unsupported capability regression tests.
- **Definition of done / acceptance criteria:** every surfaced risk can render the exact inputs/weights/version that produced it; unsupported detection capabilities cannot generate stronger claims.
- **Implementation risk:** medium-high because record volume and model/rule versioning need design.

#### P2.3: Grounded summaries and reports

- **Priority:** P2.
- **User value:** speeds handoff while preserving operator control and evidence traceability.
- **Likely files/services:** AI orchestrator/tools, report service, investigation routes/UI, recording/export components.
- **Backend/data-model changes:** report draft/job model, cited evidence bundle, immutable generated-at/model/prompt-version metadata; no automatic sending/escalation.
- **Frontend UX:** preview, citation inspection, edit, operator approval, export/download; warnings for incomplete data.
- **Tests required:** citation completeness, generated-report access control, unsafe/unsupported content tests, export integrity.
- **Definition of done / acceptance criteria:** report is a labelled draft, contains citations for factual claims, and requires an operator to approve any export/share action.
- **Implementation risk:** high hallucination and data-handling risk.

### Phase 3 — Mature operator copilot

#### P3.1: RBAC and immutable auditing

- **Priority:** P0 security architecture / P2 implementation.
- **User value:** ensures only authorised personnel can query, inspect, export, or change operational data.
- **Likely files/services:** auth service/middleware, all API routes, WebSockets, AI action registry, audit database and admin UI.
- **Backend/data-model changes:** users/roles/permissions, session identity, tenant/site scope, append-only audit records for AI query/context/citations/actions/exports.
- **Frontend UX:** permission-aware controls and reasoned access-denied state.
- **Tests required:** role matrix, tenant isolation, audit tamper detection/retention, WebSocket scope tests.
- **Definition of done / acceptance criteria:** every intelligence request/action has actor, time, scope, evidence IDs, outcome, and correlation ID.
- **Implementation risk:** high; requires product/identity decisions.

#### P3.2: Observability, evaluation, and safety monitoring

- **Priority:** P1.
- **User value:** makes model/tool failures measurable before they harm trust.
- **Likely files/services:** telemetry, AI provider wrapper, semantic/risk test datasets, CI, alerting/metrics routes.
- **Backend/data-model changes:** structured traces for retrieval, tool calls, latency, denial, stale input, citation validation, and model/provider failures; redacted evaluation logs.
- **Frontend UX:** operator-visible freshness/degraded badges, not hidden failures.
- **Tests required:** golden AI answer suites, semantic retrieval benchmarks, voice intent tests, failure-injection, latency SLO tests.
- **Definition of done / acceptance criteria:** release gates report grounded-answer rate, citation validity, tool failure rate, stale-camera rate, and p95 latency against thresholds.
- **Implementation risk:** medium-high operational cost.

#### P3.3: Private deployment and governance controls

- **Priority:** P1.
- **User value:** makes the product feasible for regulated/operator-controlled environments.
- **Likely files/services:** deployment manifests, API gateway, frontend hosting, storage, database, documentation.
- **Backend/data-model changes:** TLS, secret manager, encrypted storage, retention/deletion schedules, deployment configuration, secure session auth, optional on-prem model/STT/TTS providers.
- **Frontend UX:** retention/camera/privacy policy visibility and operator consent indicators where required.
- **Tests required:** deployment security scans, backup/restore, retention deletion verification, secret-leak checks, offline/on-prem acceptance tests.
- **Definition of done / acceptance criteria:** no privileged browser secret, TLS everywhere, tested retention controls, documented data flows, and production auth/session management.
- **Implementation risk:** high deployment and compliance risk.

## 4. Privacy-aware hands-free “Hi, Aegis” design — do not implement yet

### Design position

The current continuous `SpeechRecognition` control is a development prototype, not hands-free mode. It must not be extended into ambient listening. Hands-free mode must be opt-in per operator/session, have a visible state and emergency stop, detect the wake phrase locally, and send no ambient audio/transcript to the backend until activation.

### Architecture

```mermaid
flowchart LR
    Operator[Authorised operator] --> Toggle[Explicit hands-free toggle]
    Toggle --> Permission[One-time browser microphone permission]
    Permission --> LocalWake[Local-only wake-word engine\n"Hi, Aegis"]
    LocalWake -->|wake word only| Ack[Local acknowledgement\n"How can I help?"]
    Ack --> CommandCapture[Bounded command capture\n8-10 s silence timeout]
    CommandCapture --> LocalSTT[Local/approved command STT]
    LocalSTT --> Intent[Client command-state event\nand request metadata]
    Intent --> SecureAPI[Authenticated FastAPI command endpoint]
    SecureAPI --> Allowlist[RBAC + intent/action allowlist]
    Allowlist --> Evidence[Evidence-grounded read tools\nand citations]
    Evidence --> Response[Text response + citations]
    Response --> Confirm{Sensitive/change\naction?}
    Confirm -->|yes, explicit confirmation| Approved[Audited approved action]
    Confirm -->|no / read-only| Display[Show result]
    Approved --> Display
    Display --> TTS[Local browser TTS or approved TTS]
    TTS --> LocalWake
    CommandCapture -->|stop or timeout| LocalWake
    Operator --> Stop[Emergency stop / keyboard shortcut]
    Stop --> Off[Microphone off; cancel STT/TTS]
```

### State machine

| State | Entry condition | Permitted behaviour | Exit |
| --- | --- | --- | --- |
| `off` | Default, logout, emergency stop | No microphone capture, no wake processing. | Explicit enable. |
| `permission_required` | Operator enables hands-free first time | Show purpose, local-only wake-word guarantee, browser permission prompt. | Grant -> `wake_listening`; deny/error -> `error`. |
| `wake_listening` | Permission granted and local engine loaded | Local audio processing only; display “Wake listening.” No network audio/transcript. | Wake match -> `acknowledging`; stop -> `off`; engine error -> `error`. |
| `acknowledging` | Wake match confidence above engine threshold | Play short local acknowledgement once. | TTS ends -> `command_listening`. |
| `command_listening` | Acknowledgement complete | Capture/transcribe only command window. Reset 8–10 second silence timer on recognised speech. | Final transcript -> `processing`; silence/stop -> `wake_listening`; recognition failure -> `error`. |
| `processing` | Transcript received | Send authenticated text plus session/correlation ID; do not send ambient audio. | Read response -> `speaking` or `wake_listening`; confirmation needed -> `awaiting_confirmation`; error -> `error`. |
| `awaiting_confirmation` | Proposed sensitive/change action | Read/show exact action, scope, impact, and evidence. Accept only explicit affirmative confirmation in a short window. | Confirm -> `processing`; reject/timeout -> `wake_listening`. |
| `speaking` | Response approved for speech | Local TTS; screen always displays answer/citations. | Completion -> `wake_listening`; stop -> `off`. |
| `error` | Permission, engine, STT, network, or policy failure | Show recoverable reason; never silently continue listening. | Retry -> appropriate prior state; stop -> `off`. |

### Intent/action allowlist and confirmation policy

| Intent | Initial allowed action | Confirmation | Notes |
| --- | --- | --- | --- |
| Health/status | Read current health/context | No | Cite source timestamps. |
| Camera availability | List/open already authorised camera status | No | Do not expose unscoped camera feeds. |
| Evidence search | Search/open cited events, tracks, recordings | No | Scope by permission and retention policy. |
| Risk explanation | Show existing score/factors/evidence | No | Never convert score into an accusation/identity claim. |
| Draft summary/report | Generate private draft with citations | No for draft; **yes** for export/share | Must state incomplete evidence. |
| Alert acknowledgement | Propose acknowledgement | **Yes** | Record actor, alert ID, rationale, timestamp. |
| Camera start/stop/configuration | Propose exact change | **Yes**, preferably typed UI confirmation | Require appropriate role and audit event. |
| Delete/clear/export/retention actions | Not voice-executable initially | **Typed UI confirmation and elevated permission** | No destructive voice-only action. |
| Dispatch/enforcement/person identification | Not allowed | N/A | Out of scope; operator remains decision maker. |

### Technology and compatibility choice

- **Development fallback:** Web Speech API only through explicit push-to-talk. It is browser/vendor dependent and can process audio remotely; it must never satisfy the local wake-word privacy requirement.
- **Production wake word:** evaluate a local WebAssembly/browser engine such as Picovoice Porcupine Web, subject to licensing, offline package size, language/accent testing, CPU use, and false activation evaluation. A locally hosted open-source WASM option is acceptable only after equivalent privacy/quality review.
- **Command STT:** prefer local/on-device STT when deployment permits. If streaming STT is required, establish a command-only, authenticated, encrypted channel after wake activation and disclose the provider. Do not stream while in `wake_listening`.
- **TTS:** browser `speechSynthesis` is acceptable as a local fallback, with text always displayed. A backend TTS provider requires explicit data-flow review and should receive only the approved response text.
- **Real-time state events:** use an authenticated WebSocket or Server-Sent Event channel for command state/progress only; command audio/transcript follows the selected STT design and normal API authorization.
- **Fallback:** Firefox/Safari/unsupported hardware exposes push-to-talk text/command mode with an explanation; it never silently falls back to ambient remote recognition.

### Latency targets

| Segment | Target p95 | Rationale |
| --- | ---: | --- |
| Local wake-word recognition | < 250 ms after phrase end | Feels immediate without streaming ambience. |
| Acknowledgement start | < 500 ms | Confirms activation before command speech. |
| Final command transcription | < 1.5 s for a short command | Keeps turn-taking usable. |
| Read-only intent + evidence response | < 2.5 s | Context and indexed evidence should be bounded. |
| Time to first spoken answer | < 3.5 s | Includes command completion, tool, and local TTS start. |

### Threat and privacy model

- Microphone is **off by default** and hands-free is explicit, visible, and session-scoped.
- Wake listening uses local PCM processing only. Do not persist or transmit wake-listening audio, false activations, or ambient transcripts.
- Transmit only an activated command transcript, its correlation ID, and minimal device/session metadata over TLS; retain it under the same policy as AI queries.
- Protect against prompt injection by never treating transcribed text as authority: intent parser, typed tool schema, RBAC, allowlist, and confirmation are enforced server-side.
- Protect against replay/CSRF/session theft with authenticated secure sessions, nonce/correlation IDs, rate limits, and short command-session expiry.
- Treat voice recognition as a convenience interface, not identity authentication. Do not infer identity, emotion, demographic attributes, or intent beyond bounded command routing.
- Provide keyboard controls: proposed `Alt+Shift+A` toggles hands-free only after focus-safe policy review; `Escape` is the immediate stop/cancel control. Show an always-visible Off/Wake listening/Command listening/Processing/Speaking/Error badge.

### Proposed interfaces and endpoints

```ts
type VoiceCommandState =
  | "off"
  | "permission_required"
  | "wake_listening"
  | "acknowledging"
  | "command_listening"
  | "processing"
  | "awaiting_confirmation"
  | "speaking"
  | "error";

interface VoiceCommandRequest {
  sessionId: string;
  correlationId: string;
  transcript: string;
  locale: string;
  source: "push_to_talk" | "wake_word";
  contextVersion?: string;
}

interface EvidenceCitation {
  kind: "event" | "alert" | "track" | "detection" | "recording" | "health";
  id: string;
  cameraId?: string;
  observedAt: string;
  label: string;
}

interface VoiceCommandResponse {
  correlationId: string;
  state: "complete" | "confirmation_required" | "insufficient_evidence" | "error";
  displayText: string;
  speechText?: string;
  citations: EvidenceCitation[];
  proposedAction?: ProposedAction;
  freshness: { generatedAt: string; stale: boolean; reasons: string[] };
}

interface ProposedAction {
  type: "open_evidence" | "draft_report" | "acknowledge_alert" | "camera_configuration";
  parameters: Record<string, string>;
  confirmationRequired: boolean;
}
```

Proposed FastAPI surface (all session-authenticated, role-scoped, rate-limited, and audit logged):

```text
POST /api/intelligence/voice/commands          # transcript only; returns VoiceCommandResponse
POST /api/intelligence/voice/commands/{id}/confirm
POST /api/intelligence/voice/sessions          # creates short-lived command session
DELETE /api/intelligence/voice/sessions/{id}   # emergency/revocation cleanup
GET  /api/intelligence/voice/capabilities      # local-fallback policy/config; no secret keys
WS   /ws/intelligence/voice                    # authenticated command-progress events, no ambient audio
```

## 5. Recommended `IntelligenceContext` contract

The Intelligence page should make one typed request and then subscribe to typed deltas. Counts must state whether they are live, persisted, stale, unavailable, or zero.

```ts
type Availability = "live" | "stale" | "degraded" | "offline" | "unavailable";

interface Freshness {
  observedAt: string;
  expiresAt?: string;
  status: Availability;
  reason?: string;
}

interface EvidenceRef {
  kind: "event" | "alert" | "track" | "detection" | "recording" | "statistics";
  id: string;
  cameraId?: string;
  occurredAt?: string;
  recordingId?: string;
  frameTimestamp?: string;
  label: string;
}

interface HealthCheck {
  name: "api" | "database" | "redis" | "pipeline" | "model" | "event_stream";
  status: Availability;
  observedAt: string;
  detail?: string;
}

interface IntelligenceContext {
  schemaVersion: "1.0";
  contextId: string;
  generatedAt: string;
  refreshAfterSeconds: number;
  overall: {
    status: Availability;
    degradedReasons: string[];
    checks: HealthCheck[];
  };
  cameras: {
    totalConfigured: number;
    online: number;
    offline: number;
    stale: number;
    items: Array<{
      cameraId: string;
      name?: string;
      runtime: Availability;
      lastFrameAt?: string;
      freshness: Freshness;
    }>;
  };
  alerts: {
    activeCount: number;
    items: Array<{
      alertId: string;
      level: "LOW" | "CANDIDATE_MEDIUM" | "MEDIUM" | "HIGH" | "CRITICAL";
      acknowledged: boolean;
      evidence: EvidenceRef[];
      freshness: Freshness;
    }>;
  };
  incidents: {
    capability: Availability;
    reason?: string;
    activeCount?: number;
  };
  events: Array<{
    eventId: string;
    riskScore?: number;
    riskLevel?: string;
    summary: string;
    evidence: EvidenceRef[];
    freshness: Freshness;
  }>;
  tracks: Array<{
    trackId: string;
    cameraId?: string;
    className: string;
    riskScore?: number;
    verificationStatus?: "confirmed" | "candidate" | "unsupported" | "unknown";
    evidence: EvidenceRef[];
    freshness: Freshness;
  }>;
  detections: { recentCount: number; freshness: Freshness };
  semantic: {
    capability: Availability;
    mode?: "live_evidence";
    reason?: string;
    activeQuery?: string;
    evidence: EvidenceRef[];
    freshness: Freshness;
  };
  pipeline: { running: boolean; stages: Array<{ name: string; status: Availability; observedAt: string }>; freshness: Freshness };
  ai: {
    chat: Availability;
    providerConfigured: boolean;
    evidenceGrounding: Availability;
    voice: { pushToTalk: Availability; handsFree: Availability; reason?: string };
  };
}
```

The backend should derive this from runtime camera state, APIState, durable repositories, pipeline telemetry, and capability checks. It must never replace an unavailable source with a fabricated zero/healthy value. The response needs a Pydantic model, JSON schema, contract tests, and a matching generated TypeScript type or shared schema.

## 6. Scorecard and recommended order

### Maturity score: **27 / 100**

| Area | Score | Why |
| --- | ---: | --- |
| Data truthfulness | 35 | Real read paths exist, but the page shows fixed confidence/status, a broken camera-online count, synthetic suggestions/feed rows, and mislabeled incident counts. |
| Real-time capability | 25 | WebSockets/event bus exist, but Intelligence polls REST and sockets lack auth/event wiring. |
| AI grounding | 30 | Context collection and conservative semantic engine are useful foundations; LLM citations/confidence/actions are accepted without verification. |
| Investigation workflow | 10 | Alerts/tracks exist, but no incident/investigation lifecycle, notes, timeline, or evidence bundle. |
| Voice readiness | 12 | Push-to-talk prototype only; no wake word, privacy boundary, confirmation, or tests. |
| Security | 28 | API-key checks, CORS, and rate limits exist; browser-visible key option, unauthenticated WebSockets, no RBAC/audit/session model block production readiness. |
| Observability | 35 | Health/pipeline/event-bus helpers and telemetry models exist; no unified freshness, AI/tool telemetry, quality monitoring, or UI degradation model. |
| Production readiness | 20 | Foundational code/tests exist, but duplicated persistence stacks, broken persistence paths, and unverified AI/voice controls are material blockers. |

### Five highest-impact changes

1. Ship P0.1 plus P0.2: one truthful `IntelligenceContext` and remove every hard-coded operational claim.
2. Repair and unify persistence (P0.3) so events, alerts, tracks, and recordings become stable evidence with test coverage.
3. Replace polling-only page updates with authenticated, typed event delivery and freshness handling (P0.4).
4. Gate AI behind evidence retrieval, server-validated citations, a typed read-action allowlist, and audit logs (P1.1/P1.2).
5. Build an operator-owned investigation workspace before adding “automation,” patrol, graph, or hands-free copilot branding (P2.1/P2.2).

### Recommended 30-day implementation order

| Week | Outcome |
| --- | --- |
| 1 | Freeze new Intelligence claims; implement capability inventory/flags, typed context endpoint, proper loading/error/stale states, remove fixed confidence and mock nodes. |
| 2 | Select one data model/repository stack; fix persistence failures; add end-to-end event/alert/track retention tests and health/freshness telemetry. |
| 3 | Implement authenticated event envelopes and frontend subscription/reconnect UX; add AI endpoint/action/citation contract tests. |
| 4 | Deliver read-only evidence retrieval and cited chat, then start the investigation domain design. Keep voice as explicit push-to-talk only while validating the hands-free design. |

## Audit conclusion

AegisAI should position the current Intelligence page as an **experimental operations view** until Phase 0 is complete. The system can assist authorised operators by presenting detected, tracked, and risk-scored evidence, but it must not imply that decorative modules, LLM confidence, continuous voice listening, incident management, knowledge graphs, patrol, or automation are operational. Operator review, explicit confirmation for impactful actions, truthful degraded states, and evidence citations are the path from visual prototype to a useful intelligence copilot.
