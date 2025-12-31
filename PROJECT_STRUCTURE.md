# AegisAI – Project Structure Documentation

**Document Type:** Technical Architecture Guide  
**Version:** 5.0.0  
**Date:** December 30, 2024  
**Purpose:** Help technical reviewers, judges, and new developers understand the project organization

---

## 1. Project Structure Overview

### 1.1 Directory Hierarchy

```
AegisAI/
├── aegis/                    # Core Python package (all AI/ML logic)
│   ├── detection/            # Phase 1: YOLOv8 object detection
│   ├── tracking/             # Phase 1: DeepSORT multi-object tracking
│   ├── analysis/             # Phase 2: Motion, behavior, crowd analysis
│   ├── risk/                 # Phase 3: Risk scoring engine
│   ├── alerts/               # Phase 4: Alert generation system
│   ├── api/                  # Phase 4: REST API (FastAPI)
│   ├── semantic/             # Phase 5: Grounding DINO integration
│   ├── db/                   # Database persistence layer
│   ├── video/                # Video I/O utilities
│   ├── visualization/        # Rendering and annotations
│   ├── dashboard/            # Legacy HTML dashboard
│   ├── intelligence/         # NLQ and advanced intelligence
│   └── core/                 # Core utilities and base classes
├── frontend/                 # Next.js React dashboard
├── tests/                    # pytest test suite
│   ├── unit/                 # Unit tests
│   ├── integration/          # Integration tests
│   └── security/             # Security tests
├── deploy/                   # Production deployment configs
├── docs/                     # Additional documentation
├── data/                     # Runtime data (database, exports)
├── models/                   # Downloaded model weights
├── main.py                   # Application entry point
├── config.py                 # Configuration dataclasses
└── requirements.txt          # Python dependencies
```

### 1.2 Why This Structure?

| Principle | Implementation |
|-----------|----------------|
| **Separation of Concerns** | Each phase has dedicated directory |
| **Single Responsibility** | Max ~300 lines per file |
| **Dependency Inversion** | Modules depend on abstractions (dataclasses) |
| **Horizontal Scaling** | Each module can be replaced independently |
| **Test Isolation** | Tests mirror source structure |

### 1.3 Scalability & Maintainability

- **New features** → Add new directory under `aegis/`
- **New model** → Implement interface in existing detection/semantic module
- **New output** → Add router in `aegis/api/routes/`
- **Configuration** → Add dataclass in `config.py`

---

## 2. Root-Level Files

| File | Purpose | When Loaded | Why It Exists |
|------|---------|-------------|---------------|
| `main.py` | Application entry point | `python main.py` | CLI interface, pipeline orchestration |
| `config.py` | All configuration dataclasses | Imported by main.py | Centralized, type-safe configuration |
| `requirements.txt` | Python dependencies | `pip install -r` | Reproducible environment |
| `.env.example` | Environment template | Copied to `.env` | Security (secrets not in code) |
| `.env` | Actual environment values | Auto-loaded by dotenv | Runtime configuration |
| `Dockerfile` | Container build | `docker build` | Reproducible deployment |
| `docker-compose.yml` | Multi-container orchestration | `docker-compose up` | Development/testing stack |
| `.gitignore` | Git exclusions | Every commit | Keep repo clean |
| `.dockerignore` | Docker exclusions | `docker build` | Smaller images |

### 2.1 main.py (44KB, ~1160 lines)

**Responsibility**: Command-line interface and pipeline orchestration.

**Key Functions**:
```python
parse_arguments()      # CLI argument parsing
build_config()         # Configuration construction
run_perception_pipeline()  # Main processing loop
main()                 # Entry point
```

**Why Large**: Orchestrates all 5 phases conditionallY. Size justified by complexity.

### 2.2 config.py (12KB, ~363 lines)

**Responsibility**: Type-safe configuration management.

**Dataclasses Defined**:
- `DetectionConfig` - YOLO settings
- `TrackingConfig` - DeepSORT settings
- `AnalysisConfig` - Behavior thresholds
- `RiskConfig` - Risk weights and thresholds
- `AlertConfig` - Alert generation settings
- `APIConfig` - Server configuration
- `SemanticConfig` - Grounding DINO settings
- `DatabaseConfig` - Persistence settings
- `AegisConfig` - Master container

---

## 3. Core Modules Breakdown

### 3.1 aegis/detection/

**Responsibility**: Object detection using YOLOv8.

| File | Purpose |
|------|---------|
| `__init__.py` | Exports `YOLODetector`, `Detection` |
| `yolo_detector.py` | YOLOv8 wrapper with lazy loading |

**Inputs**: Video frames (numpy arrays)  
**Outputs**: `List[Detection]` with bbox, confidence, class_name

**Communication**: Outputs consumed by `aegis/tracking/`

### 3.2 aegis/tracking/

**Responsibility**: Multi-object tracking with persistent IDs.

| File | Purpose |
|------|---------|
| `__init__.py` | Exports `DeepSORTTracker`, `Track` |
| `deepsort_tracker.py` | DeepSORT integration |

**Inputs**: `List[Detection]` from detection module  
**Outputs**: `List[Track]` with stable `track_id`

**Communication**: Outputs consumed by `aegis/analysis/`

### 3.3 aegis/analysis/

**Responsibility**: Behavioral analysis of tracked objects.

| File | Purpose |
|------|---------|
| `__init__.py` | Package exports |
| `track_history.py` | Per-track position history |
| `motion_analyzer.py` | Speed, direction, acceleration |
| `behavior_analyzer.py` | Loitering, running, erratic motion |
| `crowd_analyzer.py` | Density mapping, hotspots |
| `track_analysis.py` | Combined TrackAnalysis dataclass |

**Inputs**: `List[Track]` from tracking module  
**Outputs**: `List[TrackAnalysis]` with motion state and behaviors

**Communication**: Outputs consumed by `aegis/risk/`

### 3.4 aegis/risk/

**Responsibility**: Context-aware, explainable risk scoring.

| File | Purpose |
|------|---------|
| `__init__.py` | Package exports |
| `risk_engine.py` | Multi-signal risk calculation |
| `zone_manager.py` | Restricted zone handling |
| `temporal_model.py` | Risk escalation/decay |
| `risk_types.py` | RiskScore, RiskLevel dataclasses |

**Inputs**: `List[TrackAnalysis]`, `CrowdMetrics`  
**Outputs**: `FrameRiskSummary` with per-track `RiskScore`

**Communication**: Outputs consumed by `aegis/alerts/` and `aegis/api/`

### 3.5 aegis/alerts/

**Responsibility**: Alert generation with cooldowns and deduplication.

| File | Purpose |
|------|---------|
| `__init__.py` | Package exports |
| `alert_manager.py` | Alert lifecycle management |
| `alert_types.py` | Alert, AlertLevel dataclasses |

**Inputs**: `FrameRiskSummary` from risk module  
**Outputs**: `List[Alert]` dispatched to console/file/API

### 3.6 aegis/api/

**Responsibility**: REST API and WebSocket endpoints.

| File | Purpose |
|------|---------|
| `__init__.py` | Package exports |
| `app.py` | FastAPI application factory |
| `state.py` | Thread-safe shared state |
| `security.py` | API key auth, rate limiting |
| `websocket.py` | WebSocket handler |
| `routes/` | Endpoint routers |

**Routes**:
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/status` | GET | System health |
| `/events` | GET | Recent risk events |
| `/tracks` | GET | Active tracks |
| `/statistics` | GET | Crowd metrics |
| `/semantic/query` | POST | Submit semantic prompt |
| `/semantic/results` | GET | Get semantic matches |

### 3.7 aegis/semantic/

**Responsibility**: Language-guided detection using Grounding DINO.

| File | Purpose |
|------|---------|
| `__init__.py` | Package exports |
| `dino_engine.py` | Grounding DINO wrapper (lazy loading) |
| `prompt_manager.py` | Prompt storage with LRU cache |
| `semantic_trigger.py` | Event-driven trigger logic |
| `semantic_fusion.py` | Fuse YOLO + DINO + risk |
| `async_executor.py` | Non-blocking ThreadPoolExecutor |

**Key Design**: DINO runs only on-demand (not per-frame) to preserve real-time FPS.

### 3.8 aegis/db/

**Responsibility**: Database persistence for events and alerts.

| File | Purpose |
|------|---------|
| `__init__.py` | Package exports |
| `database.py` | Engine/session factory (SQLite/PostgreSQL) |
| `models.py` | ORM models (Event, Alert, TrackSnapshot) |
| `repository.py` | CRUD operations with auto-cleanup |

### 3.9 aegis/video/

**Responsibility**: Video input/output abstraction.

| File | Purpose |
|------|---------|
| `__init__.py` | Package exports |
| `source.py` | VideoSource (file/camera abstraction) |
| `writer.py` | VideoWriter with codec handling |

### 3.10 aegis/visualization/

**Responsibility**: Rendering annotations on frames.

| File | Purpose |
|------|---------|
| `__init__.py` | Package exports |
| `renderer.py` | Draw boxes, trails, risk overlays |

---

## 4. AI & Model Layer

### 4.1 Where YOLO is Loaded

```
aegis/detection/yolo_detector.py
└── YOLODetector._load_model()
    └── ultralytics.YOLO(model_path)
```

**Lazy Loading**: Model loaded on first `detect()` call, not at import.

### 4.2 Where Grounding DINO is Integrated

```
aegis/semantic/dino_engine.py
└── DinoEngine._load_model()
    └── groundingdino.load_model()
```

**Fallback Mode**: If groundingdino not installed, system continues without semantic features.

### 4.3 Model Abstraction

| Model | Interface | Output Dataclass |
|-------|-----------|------------------|
| YOLOv8 | `detector.detect(frame)` | `Detection` |
| DeepSORT | `tracker.update(detections, frame)` | `Track` |
| Grounding DINO | `dino_engine.infer(frame, prompt)` | `SemanticDetection` |

**Design Pattern**: All models return standardized dataclasses, enabling swap-out.

### 4.4 Inference Triggering

| Model | Trigger | Frequency |
|-------|---------|-----------|
| YOLO | Every frame | 30 FPS |
| DeepSORT | Every frame | 30 FPS |
| Grounding DINO | Event-driven | On-demand |

**DINO Triggers**:
1. User submits semantic query
2. Risk score exceeds threshold
3. Behavior change detected (loitering, erratic)

---

## 5. Execution Flow

### 5.1 Application Start

```
python main.py --input 0 --output out.mp4 --enable-risk --enable-api
        │
        ▼
    parse_arguments()
        │
        ▼
    build_config()  →  AegisConfig
        │
        ▼
    run_perception_pipeline()
```

### 5.2 Frame Processing Loop

```
┌─────────────────────────────────────────────────────────────┐
│  for frame in video_source:                                 │
│      │                                                      │
│      ▼                                                      │
│  ┌─────────────┐                                            │
│  │ PHASE 1     │  detector.detect(frame)                    │
│  │ Detection   │  tracker.update(detections, frame)         │
│  └──────┬──────┘                                            │
│         │ List[Track]                                       │
│         ▼                                                   │
│  ┌─────────────┐                                            │
│  │ PHASE 2     │  motion_analyzer.analyze(track)            │
│  │ Analysis    │  behavior_analyzer.analyze(track)          │
│  └──────┬──────┘  crowd_analyzer.analyze(frame)             │
│         │ List[TrackAnalysis]                               │
│         ▼                                                   │
│  ┌─────────────┐                                            │
│  │ PHASE 3     │  risk_engine.compute_frame_risks()         │
│  │ Risk        │                                            │
│  └──────┬──────┘                                            │
│         │ FrameRiskSummary                                  │
│         ▼                                                   │
│  ┌─────────────┐                                            │
│  │ PHASE 4     │  alert_manager.process_risks()             │
│  │ Response    │  api_server.state.update()                 │
│  └──────┬──────┘                                            │
│         │                                                   │
│         ▼                                                   │
│  ┌─────────────┐                                            │
│  │ PHASE 5     │  semantic_trigger.check_triggers()         │
│  │ Semantic    │  semantic_executor.submit() [async]        │
│  └─────────────┘                                            │
│                                                             │
│  renderer.render(frame, tracks, risks)                      │
│  writer.write(annotated_frame)                              │
└─────────────────────────────────────────────────────────────┘
```

### 5.3 Decision Points

| Stage | Decision |
|-------|----------|
| Detection | Confidence > threshold? Keep detection |
| Tracking | Track confirmed? Include in output |
| Behavior | Stationary > N frames? Mark loitering |
| Risk | Score > threshold? Escalate temporal risk |
| Alert | Score > min_level AND cooldown passed? Generate alert |
| Semantic | Trigger event detected? Submit DINO inference |

---

## 6. Configuration & Environment

### 6.1 Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `AEGIS_API_KEY` | API authentication | Required |
| `AEGIS_API_HOST` | Server bind address | `127.0.0.1` |
| `AEGIS_API_PORT` | Server port | `8080` |
| `AEGIS_DEBUG` | Enable debug mode | `false` |
| `DATABASE_URL` | Database connection | `sqlite:///data/aegis.db` |
| `SEMANTIC_ENABLED` | Enable DINO | `false` |

### 6.2 Configuration Hierarchy

```
CLI Arguments (highest priority)
        │
        ▼
Environment Variables (.env)
        │
        ▼
Dataclass Defaults (lowest priority)
```

### 6.3 Changing Config Without Code Changes

```bash
# Via CLI
python main.py --confidence 0.6 --enable-semantic

# Via environment
export AEGIS_API_KEY="new-key"
export SEMANTIC_ENABLED=true

# Via .env file
echo "AEGIS_DEBUG=true" >> .env
```

---

## 7. Extensibility Guide

### 7.1 Adding a New Model

1. Create wrapper in `aegis/<module>/new_model.py`
2. Implement standard interface returning dataclass
3. Add to `aegis/<module>/__init__.py` exports
4. Add config dataclass in `config.py`
5. Add CLI argument in `main.py` if needed

### 7.2 Adding a New Risk Rule

1. Edit `aegis/risk/risk_engine.py`
2. Add signal to `_calculate_base_score()`
3. Add weight to `RiskWeights` dataclass
4. Add to explanation generation

### 7.3 Adding a New Output

1. Create route in `aegis/api/routes/new_route.py`
2. Add router to `aegis/api/routes/__init__.py`
3. Register in `aegis/api/app.py`
4. Update API documentation

### 7.4 Adding a New Trigger for Semantic Layer

1. Edit `aegis/semantic/semantic_trigger.py`
2. Add new `TriggerType` enum value
3. Implement check in `check_triggers()`

---

## 8. File Responsibility Table

| File/Folder | Responsibility | Criticality |
|-------------|----------------|-------------|
| `main.py` | Entry point, CLI, orchestration | Critical |
| `config.py` | All configuration dataclasses | Critical |
| `aegis/detection/` | YOLOv8 object detection | Critical |
| `aegis/tracking/` | DeepSORT multi-object tracking | Critical |
| `aegis/analysis/` | Motion and behavior analysis | High |
| `aegis/risk/` | Explainable risk scoring | High |
| `aegis/alerts/` | Alert generation | Medium |
| `aegis/api/` | REST API and WebSocket | High |
| `aegis/semantic/` | Grounding DINO integration | Medium |
| `aegis/db/` | Database persistence | Medium |
| `aegis/video/` | Video I/O | High |
| `aegis/visualization/` | Rendering | Medium |
| `frontend/` | Next.js dashboard | Medium |
| `tests/` | Test suite | High |
| `deploy/` | Production configs | Medium |
| `requirements.txt` | Dependencies | Critical |
| `.env.example` | Environment template | High |

---

## 9. Technical Quality Notes

### 9.1 File Size Philosophy

| Target | Rationale |
|--------|-----------|
| ~300 lines max per file | Easy to review, test, maintain |
| Single responsibility | Each file does one thing well |
| Horizontal over vertical | More files > longer files |

**Exception**: `main.py` (1160 lines) orchestrates all phases—complexity justified.

### 9.2 Coding Standards

| Standard | Implementation |
|----------|----------------|
| **Type Hints** | All function signatures typed |
| **Dataclasses** | Standardized data contracts |
| **Docstrings** | Module, class, and function level |
| **Logging** | Structured module loggers |
| **Error Handling** | Graceful degradation on missing modules |

### 9.3 Competition & Production Suitability

| Quality | Evidence |
|---------|----------|
| **Modularity** | Each phase independently testable |
| **Explainability** | Every risk score has factors |
| **Documentation** | Multiple comprehensive reports |
| **Security** | API auth, rate limiting, HTTPS |
| **Deployment** | Docker, nginx, Docker Compose |
| **Testing** | Unit, integration, security tests |

---

## Appendix: Module Dependency Graph

```
                    main.py
                       │
         ┌─────────────┼─────────────┐
         │             │             │
         ▼             ▼             ▼
    config.py    aegis/video    aegis/visualization
         │             │             │
         └──────┬──────┘             │
                │                    │
                ▼                    │
         aegis/detection ────────────┤
                │                    │
                ▼                    │
         aegis/tracking ─────────────┤
                │                    │
                ▼                    │
         aegis/analysis ─────────────┤
                │                    │
                ▼                    │
           aegis/risk ───────────────┤
                │                    │
         ┌──────┴──────┐             │
         ▼             ▼             │
    aegis/alerts   aegis/api ────────┘
         │             │
         ▼             ▼
      aegis/db    aegis/semantic
```

---

**End of Project Structure Documentation**
