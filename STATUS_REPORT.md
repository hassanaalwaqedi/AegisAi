# AegisAI — Current Engineering Status

**Reviewed:** 2026-09-29
**Scope:** Repository inspection, not a completed field evaluation or fresh production audit.

## What exists

AegisAI is an operator-assistance prototype. It connects camera sources, detects and tracks objects, derives contextual risk signals, persists events and evidence, and exposes REST/WebSocket data to a Next.js dashboard. Optional semantic search and Gemini-based text/voice workflows depend on their configuration and services. Risk scores prioritize human review; they do not establish intent or authorize an automated response.

The current implementation uses Ultralytics YOLO components and ByteTrack-compatible tracking as its principal lightweight path. DeepSORT remains in the repository as another tracking component. The backend uses FastAPI and SQLAlchemy; SQLite is the local default, with PostgreSQL and Redis deployment paths documented. The frontend is a Next.js application.

## Evidence available in this repository

| Area | Evidence | What it does not prove |
| --- | --- | --- |
| Functional implementation | Backend modules, frontend pages, API routes, and unit/integration tests | Reliability at a real site |
| Build and test automation | `.github/workflows/ci.yml` runs backend tests and a Docker build | The current working tree passed CI; frontend build/test is not in that workflow |
| Performance tooling | `scripts/benchmark_general_detectors.py` measures detector latency and resource use | End-to-end alert latency or multi-camera capacity |
| Evaluation data | `data/evaluation/README.md` describes two unique unlabeled local clips | Precision, recall, or threat-detection accuracy |
| API protection | API-key checks, rate limiting, a server-side dashboard proxy, and WebSocket token checks | Per-user authorization or production access governance |

## Highest-priority gaps

1. **Validation:** Build an independent, annotated evaluation set with benign lookalikes and relevant positive cases. Report precision, recall, missed events, false alerts per camera-hour, and confidence intervals where practical.
2. **Performance:** Measure camera-to-visible-alert latency, p50/p95, dropped frames, memory, and throughput on named hardware at 1, 2, and more camera streams. Detector-only FPS is insufficient.
3. **Data lifecycle:** The active schema still needs a complete initial Alembic migration. The README currently requires manual `create_tables()` for a fresh database. Test clean install, upgrade, restart, retention, and recovery.
4. **Identity and permissions:** Add real operator sessions, role-based access control, and access audits for sensitive evidence. A shared backend API key is not a per-user identity model.
5. **Release gate:** Run frontend lint, tests, and build in CI, and make relevant security checks fail the workflow when they detect a blocking issue.
6. **Documentation consistency:** Treat this file and the README as current operational references. `PROJECT_REPORT.md` and `TECHNICAL_REPORT.md` contain historical phases and estimates; verify claims against code and measured results before presenting them as current.

## Demo claim boundary

Safe claim: **“We built an end-to-end operator-assistance prototype that turns camera observations into reviewable events and contextual risk signals.”**

Do not claim a field-validated threat-detection accuracy, universal real-time FPS, autonomous enforcement, production security, or reliable cross-camera identity tracking without corresponding measurements and implementation evidence.

For evaluator questions and suggested answers, see the [Arabic presentation Q&A](docs/PRESENTATION_QA_AR.md) and [English presentation Q&A](docs/PRESENTATION_QA.md).
