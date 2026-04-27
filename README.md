# AegisAI — Smart City Risk Intelligence System

> Real-time AI-powered surveillance platform for threat detection, behavioral analysis, and risk intelligence.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Frontend (React SPA)          Firebase Hosting          │
│  ├── SOC Dashboard             or Nginx Container        │
│  ├── 7 Pages (Dashboard, Cameras, Alerts, Analytics...) │
│  └── WebSocket Real-time ────────────────────────┐      │
└──────────────────────────────────────────────────┬──────┘
                                                   │
                  REST API + WebSocket             │
                                                   ▼
┌─────────────────────────────────────────────────────────┐
│  Backend (FastAPI)             AWS EC2 / ECS             │
│  ├── 16 REST Routes + /ws endpoint                      │
│  ├── YOLOv8/v11 Detection Pipeline                      │
│  ├── ByteTrack Object Tracking                          │
│  ├── Risk Intelligence Engine                           │
│  ├── Alert Management System                            │
│  ├── Gemini AI (NLQ Interface)                          │
│  ├── Edge/Cloud Hybrid Architecture                     │
│  └── PostgreSQL + Redis                                 │
└─────────────────────────────────────────────────────────┘
```

## Quick Start (Local Development)

### Prerequisites
- Python 3.10+
- Node.js 18+
- Redis (optional for dev)

### 1. Backend
```bash
# Clone and install
git clone https://github.com/your-org/AegisAI.git
cd AegisAI

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt

# Copy environment config
cp .env.example .env
# Edit .env with your AEGIS_API_KEY and GEMINI_API_KEY

# Start API server
python -m uvicorn aegis.api.app:app --host 0.0.0.0 --port 8080
```

### 2. Frontend
```bash
cd frontend

# Install dependencies
npm install

# Start dev server (proxies API to localhost:8080)
npm run dev
# → opens http://localhost:5173
```

### 3. Docker (Full Stack)
```bash
# Build and start all services
docker-compose up --build

# API:      http://localhost:8080
# Frontend: http://localhost:3000
```

## Deployment

### Frontend → Firebase Hosting
```bash
cd frontend

# Set production API URL
echo "VITE_API_URL=https://api.aegisai.com" > .env.production

# Build and deploy
npm run deploy
```

### Backend → AWS
```bash
# Build Docker image
docker build -t aegisai:latest .

# Push to ECR
aws ecr get-login-password | docker login --username AWS --password-stdin <account>.dkr.ecr.<region>.amazonaws.com
docker tag aegisai:latest <account>.dkr.ecr.<region>.amazonaws.com/aegisai:latest
docker push <account>.dkr.ecr.<region>.amazonaws.com/aegisai:latest

# Deploy with ECS or EC2
```

### Required AWS Services
| Service | Purpose |
|---------|---------|
| EC2 / ECS | Run API container |
| RDS PostgreSQL | Database |
| ElastiCache Redis | Caching |
| ALB | HTTPS + WebSocket |
| S3 | Recordings storage |
| Route 53 | DNS |
| ACM | SSL certificate |

## API Authentication

All API requests require an `X-API-Key` header:
```bash
curl -H "X-API-Key: your-key" http://localhost:8080/status
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `AEGIS_API_KEY` | Yes | API authentication key |
| `DATABASE_URL` | No | PostgreSQL URL (default: SQLite) |
| `REDIS_URL` | No | Redis URL |
| `GEMINI_API_KEY` | No | Google Gemini for NLQ |
| `AEGIS_DEBUG` | No | Enable /docs endpoint |

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run smoke tests only
pytest tests/unit/test_api_smoke.py -v
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| AI/ML | YOLOv8/v11, ByteTrack, Grounding DINO |
| Backend | FastAPI, SQLAlchemy, Redis |
| Frontend | React 19, TypeScript, Recharts, Zustand |
| Infra | Docker, PostgreSQL, Nginx, Firebase |

## License

Proprietary — All rights reserved.
