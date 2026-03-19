# AegisAI - Smart City Risk Intelligence System


 Project Overview
AegisAIis a production-ready Smart City Risk Intelligence System that transforms raw video feeds into actionable, explainable risk intelligence.

### System Phases

| Phase | Name | Status | Description |
|-------|------|--------|-------------|
| 1 | Perception | ✅ Complete | YOLOv8 detection + DeepSORT tracking |
| 2 | Analysis | ✅ Complete | Motion & behavior analysis |
| 3 | Risk | ✅ Complete | Explainable risk scoring |
| 4 | Response | ✅ Complete | REST API + Dashboard + Alerts |

---

## 🚀 Quick Start

### Installation

```bash
# Clone and setup
cd AegisAI
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

### Basic Usage

```bash
# Process video with full pipeline
python main.py --input video.mp4 --output out.mp4 --enable-risk

# Start with API server
python main.py --input 0 --output cam.mp4 --enable-api

# API server standalone
uvicorn aegis.api.app:app --reload
```

---

## 🔐 Security & API Authentication

**New in Sprint 1:** API endpoints require authentication.

### Configure API Key

```bash
# Option 1: Environment variable
export AEGIS_API_KEY="your-secret-key"

# Option 2: .env file
cp .env.example .env
# Edit .env and set AEGIS_API_KEY
```

### Make Authenticated Requests

```bash
curl -H "X-API-Key: your-secret-key" http://localhost:8080/status
```

See [SECURITY.md](SECURITY.md) for full security documentation.

---

## 🧪 Running Tests

```bash
# Run all tests
pytest -v

# Run unit tests only
pytest tests/unit/ -v

# Run integration tests
pytest tests/integration/ -v

# Run with coverage
pytest --cov=aegis --cov-report=html
```

### Test Structure

```
tests/
├── conftest.py              # Shared fixtures
├── unit/
│   ├── test_risk_engine.py
│   ├── test_alert_manager.py
│   ├── test_motion_analyzer.py
│   └── test_behavior_analyzer.py
└── integration/
    ├── test_api_endpoints.py
    └── test_pipeline_flow.py
```

---

## 🐳 Docker

### Build

```bash
docker build -t aegisai .
```

### Run

```bash
# API server only
docker run -p 8080:8080 -e AEGIS_API_KEY="your-key" aegisai

# With mounted data
docker run -p 8080:8080 \
  -v $(pwd)/data:/app/data \
  -e AEGIS_API_KEY="your-key" \
  aegisai
```

---

## 📡 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/status` | GET | System health |
| `/events` | GET | Risk events |
| `/tracks` | GET | Active tracks |
| `/statistics` | GET | Crowd & risk stats |
| `/dashboard` | GET | Live UI |
| `/docs` | GET | OpenAPI docs (debug mode) |

---

## 💻 Command-Line Options

| Flag | Description |
|------|-------------|
| `--input`, `-i` | Video path or camera index |
| `--output`, `-o` | Output video path |
| `--enable-analysis` | Enable Phase 2 |
| `--enable-risk` | Enable Phase 3 |
| `--enable-alerts` | Enable alert generation |
| `--enable-api` | Start REST API server |
| `--api-port` | API server port (default: 8080) |

---

## 📁 Project Structure

```
AegisAI/
├── aegis/
│   ├── detection/       # YOLOv8
│   ├── tracking/        # DeepSORT
│   ├── analysis/        # Motion & behavior
│   ├── risk/            # Risk scoring
│   ├── alerts/          # Alert system
│   ├── api/             # REST API
│   └── dashboard/       # Frontend UI
├── tests/               # Test suite
├── config.py            # Configuration
├── main.py              # Entry point
├── Dockerfile           # Container build
├── SECURITY.md          # Security guide
└── requirements.txt     # Dependencies
```

---

## 📝 Documentation

- [PROJECT_REPORT.md](PROJECT_REPORT.md) - Full technical report
- [SECURITY.md](SECURITY.md) - API security guide
- [GAP_ANALYSIS.md](GAP_ANALYSIS.md) - Engineering assessment

---

## 🙏 Acknowledgments

- [Ultralytics](https://ultralytics.com/) - YOLOv8
- [DeepSORT](https://github.com/levan92/deep_sort_realtime) - Tracking
- [FastAPI](https://fastapi.tiangolo.com/) - REST API
