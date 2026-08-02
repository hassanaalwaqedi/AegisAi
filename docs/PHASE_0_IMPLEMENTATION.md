# Intelligence Phase 0 implementation

## Scope

Phase 0 changes `/intelligence` from a decorative status screen into a
source-fresh operational view. It does **not** add investigations, incident
management, automation, patrol/maps, knowledge graphs, or hands-free voice.
Risk scoring and detection decisions are unchanged.

## Intelligence context contract

The authenticated endpoint is:

```text
GET /api/intelligence/context
X-API-Key: <server-side credential>
```

It returns the Pydantic `IntelligenceContext` schema version `1.0`, serialized
with camel-case field names. The companion frontend Zod schema rejects an
invalid or incompatible response instead of inventing a replacement value.

The response includes:

- `generatedAt`, `contextId`, and `refreshAfterSeconds` for snapshot freshness.
- Timed API, database, Redis, event-stream, pipeline, detection-model, and
  persistence checks, with `live`, `stale`, `degraded`, `offline`, or
  `unavailable` states and reasons.
- Runtime camera counts and items from `MultiCameraPipelineManager`, including
  separate online, offline, stale, and unavailable runtime states. A zero is
  returned only when the runtime manager actually returned no cameras.
- The current in-memory operational event/track state only when its source is
  available, with evidence references and timestamps. Every context evidence
  reference is checked against the same server-side camera, event, or track
  snapshot used to build the response. A reference is emitted only after its
  identity, camera association, and source timestamp match, and includes
  `serverValidated: true` plus `validatedAt`. `activeCount` is named and
  rendered as **Active Risk Alerts**; it is not called incidents.
- Semantic, AI provider/chat, push-to-talk, and hands-free capability states.
  An unimplemented capability is explicitly unavailable.
- Suggestions only when an observed offline/stale camera or a runtime risk
  alert supplies a reason, evidence reference, and a route that exists.

Phase 0 deliberately uses bounded REST polling from the server-provided refresh
policy. It does not make the existing unauthenticated WebSocket surface an
Intelligence data source.

## Runtime and persistence decision

The active operational path was traced as:

```text
MultiCameraPipelineManager -> FrameIngestionService -> APIState
                                             -> aegis.database repositories
```

The detection-model health check follows this active camera-ingestion path when
it has created a detector. The separate Redis worker pipeline remains a worker
health check; an intentionally idle worker detector cannot override a loaded
camera-ingestion detector.

`aegis.database` is therefore the one persistence stack used by the context,
the camera ingestion flow, and `AlertingStage`. The overlapping `aegis.db` and
the legacy singular `aegis.database.repository` path were not merged into the
new context; they are not active sources for this view.

The alert persistence call now enters `get_db_session()` and calls the active
`EventRepository.create(...)` method. `aegis.ai.tools.get_recent_events` also
enters its context-managed database session before constructing a repository.
Write attempts are recorded in process-local persistence telemetry. A failed
write remains non-blocking for frame processing but appears as a timed,
degraded `persistence` check and a degraded reason in the context.

The active SQLAlchemy model retains the physical `events.metadata` column, but
uses `event_metadata` as its Python attribute because `metadata` is reserved by
SQLAlchemy. The selected schema supports the configured SQLite path and keeps
PostgreSQL JSONB through a dialect variant.

## Frontend behaviour

The dashboard consumes only `useIntelligenceContext`, rather than combining
independent metrics, suggestion, and feed polls. It has explicit loading,
offline/error, stale, degraded, empty, and unavailable states. Timestamps use
the contract's source time (for example, `Updated 12 seconds ago`).

Provider reachability is shown as capability state, but operational chat is
disabled until evidence grounding is live. A context whose source citations
cannot be checked is degraded and omits those references rather than presenting
them as Intelligence evidence.

The screen does not render a fixed health percentage, global AI confidence,
fixed "High" badge, "All Systems Normal", synthetic activity, generic report
or event-search suggestions, or a fabricated staffing count. The orb is
labelled as a visual system map. Supported nodes link only to Cameras,
Analytics, Semantic Search, Tracking, and Risk pages; unsupported nodes are
non-interactive and visibly planned/unavailable with a reason.

## Browser credential handling

The browser no longer reads a privileged `NEXT_PUBLIC_*` API key. Browser API
calls go through `frontend/src/app/api/backend/[...path]/route.ts`; that
server-side route reads only `AEGIS_API_URL` and `AEGIS_API_KEY`. The frontend
and root environment examples and the README document those server-only names.

This proxy prevents key bundling but is not a replacement for a production
dashboard session, RBAC, and audit model. Those controls remain a later phase.

## Validation

Backend regression coverage exercises pipeline/database/Redis failures, no
cameras, offline/stale/unavailable camera states, persistence failure, both
session-management regressions, the versioned schema, and the authenticated
endpoint. Frontend tests cover loading, unavailable, stale, degraded, and
empty/no-synthetic-data rendering.

Run the focused checks from the repository root:

```powershell
pytest tests/unit/test_intelligence_context.py -q
Set-Location frontend
npm test
npx tsc --noEmit
npm run build
```

At implementation time, the focused backend suite passed **58 tests** and the
frontend suite passed **7 tests**; the frontend TypeScript check and production
build also passed.

## Migration and remaining limits

No schema migration is required for an existing Phase 0 database: the SQL
column name remains `events.metadata`. Code using the active ORM model must use
`Event.event_metadata` as its Python attribute. A fresh database does require
one explicit initialization because no initial Alembic migration for the active
`aegis.database` schema is currently supplied:

```powershell
python -c "from aegis.database.connection import create_tables; create_tables()"
```

Run this after setting `DATABASE_URL` and before starting a deployment that
needs durable event writes.

Known remaining limitations:

- Live events/tracks and persistence telemetry are process-local and do not
  create a durable investigation history.
- Active Risk Alerts are runtime alerts, not an incident lifecycle.
- Semantic evidence remains live-evidence search; it is not a knowledge graph.
- Context citations are validated against their in-process source snapshot;
  cross-process, immutable evidence storage and cryptographic audit trails are
  not implemented in Phase 0.
- Push-to-talk remains browser transcript input; hands-free voice is not
  implemented.
- Intelligence still polls. Authenticated event streaming, session/RBAC,
  durable evidence retrieval, and audited actions are future work.
