# Aegis Creator and Project Knowledge

`system_knowledge` is the source of truth for Aegis creator and project facts. AI responses must retrieve these records from the active `aegis.database` SQLAlchemy persistence stack; they must not be hard-coded in prompts, frontend components, or endpoint-specific rules.

## Migration and seed

Run migrations in the deployment environment, then seed the approved records:

```powershell
alembic upgrade head
python -m aegis.knowledge.seed
```

The seed is transactional and idempotent. It reports `inserted`, `updated`, `skipped`, and `failed`. A normal run never replaces a record once it exists, including an administrator-edited version. To deliberately supersede every official record with a new version:

```powershell
python -m aegis.knowledge.seed --force
```

Run these commands against the intended deployment database only. The migration was validated against an isolated SQLite database during development; it does not modify a production database by itself.

## Data model

`system_knowledge` stores a versioned record key, category, localised content (`content_ar`, `content_en`, `content_tr`), JSON structured data, visibility, priority, source attribution, active state, timestamps, and administrative attribution. `(key, version)` is unique. Only an active, non-deleted, public version is eligible for normal retrieval.

`system_knowledge_audit` is append-only. It records the actor, action, and before/after snapshots for creation, versions, activation changes, restores, and seed changes. Restoring a record creates a new version; it never rewrites history.

## Access control

Normal authenticated users can search only safe public projections:

`GET /api/system-knowledge/search?q=Who%20created%20Aegis%3F`

No public response contains database IDs, source paths, administrator identities, private content, or audit data.

Administrative routes are under `/api/admin/system-knowledge`. They require both `X-API-Key` and `X-Aegis-Admin-Key`. Set a distinct server-only value for `AEGIS_ADMIN_API_KEY`; if it is absent, admin access fails closed. Do not put either key in `NEXT_PUBLIC_*` configuration.

Admin operations include list/read/create, versioned update, activation/deactivation, history, audit history, and restore.

## AI retrieval

`SystemKnowledgeService` is the shared retrieval service for `/api/ai/chat`, `/api/ai/voice`, `/api/ai/context` capability metadata, and the Gemini Live allowlisted knowledge tool. It ranks active public records by category relevance, approved multilingual aliases, exact matches, and priority.

Arabic, English, and Turkish content is selected from the database. When a locale-specific field is absent, the controlled canonical English field is used as the configured fallback. Undocumented facts return the language-specific “not currently documented” response. Database retrieval failure returns an explicit unavailable response; Aegis does not fabricate a replacement answer.

The existing `/semantic` API remains live camera-evidence search. It is deliberately not mixed with creator/project knowledge, so an evidence result cannot override an official project fact.

## Initial approved records

The initial seed contains project identity, purpose, creator profile, creator contributions, architecture, computer-vision capability, AI-assistant capability, security principles, repository-verified technology, and known limitations. The technology record distinguishes implemented and configured-optional items based on source code, dependency files, configuration, and documentation inspected in this repository.
