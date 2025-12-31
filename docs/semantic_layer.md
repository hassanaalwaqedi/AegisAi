# AegisAI Semantic Layer

**Phase 5: Language-Guided Scene Understanding**

Transform AegisAI from a system that *sees objects* into a system that *understands situations*.

---

## Overview

The Semantic Layer integrates Grounding DINO language-guided detection with the existing YOLOv8 + DeepSORT perception pipeline. This enables natural language queries like:

- "person carrying a backpack near entrance"
- "vehicle stopped in no-parking zone"
- "someone running away from restricted area"

### Why Combine YOLO + DINO?

| Aspect | YOLOv8 | Grounding DINO | Combined |
|--------|--------|----------------|----------|
| **Speed** | ~30+ FPS | ~2-5 FPS | Real-time |
| **Classes** | Fixed (COCO) | Open vocabulary | Best of both |
| **Context** | None | Language prompts | Situational awareness |
| **Use Case** | Continuous detection | On-demand analysis | Hybrid intelligence |

**Result**: YOLO runs continuously for real-time detection, while DINO is invoked only when needed for deeper semantic understanding.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Video Frame Input                        │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  PHASE 1: PERCEPTION (Real-time, every frame)                │
│  ┌─────────────┐    ┌─────────────────┐                      │
│  │  YOLOv8     │───▶│  DeepSORT       │──▶ Tracks            │
│  │  Detection  │    │  Tracking       │                      │
│  └─────────────┘    └─────────────────┘                      │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  PHASE 2-4: ANALYSIS & RISK (Every frame)                    │
│  Motion Analysis ─▶ Behavior Detection ─▶ Risk Scoring       │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  PHASE 5: SEMANTIC (On-demand, trigger-based)                │
│                                                              │
│  ┌─────────────────┐    ┌─────────────────┐                  │
│  │ Semantic        │───▶│ DINO Engine     │                  │
│  │ Trigger         │    │ (Async)         │                  │
│  └─────────────────┘    └────────┬────────┘                  │
│                                  │                           │
│  ┌─────────────────┐    ┌────────▼────────┐                  │
│  │ Prompt Manager  │    │ Semantic        │                  │
│  │ (Cache)         │    │ Fusion          │──▶ Intelligence  │
│  └─────────────────┘    └─────────────────┘                  │
└──────────────────────────────────────────────────────────────┘
```

---

## When DINO is Triggered

**CRITICAL**: DINO does NOT run on every frame. It is triggered only by:

### 1. User Query
When a user submits a natural language prompt via CLI or API:
```bash
python main.py --enable-semantic --semantic-prompt "person with bag"
```

### 2. Risk Threshold Exceeded
When a track's risk score exceeds the configured threshold (default: 0.6):
```python
# config.semantic.risk_threshold_trigger = 0.6
```

### 3. Behavior Change
When a tracked object exhibits concerning behavior:
- Loitering (stationary for extended period)
- Sudden speed change
- Direction reversal
- Erratic motion

### 4. Zone Violation
When a track enters a restricted zone (future enhancement).

---

## Output Format

The semantic layer outputs `UnifiedObjectIntelligence` combining all perception layers:

```json
{
    "track_id": 5,
    "base_class": "Person",
    "confidence": 0.92,
    "semantic_label": "person with bag",
    "semantic_confidence": 0.87,
    "matched_phrase": "person carrying a backpack near entrance",
    "risk_score": 0.72,
    "timestamp": 12.5,
    "bbox": [120, 100, 280, 380],
    "behaviors": ["LOITERING"]
}
```

---

## Configuration

### Environment Variables (.env)

```bash
SEMANTIC_ENABLED=true
SEMANTIC_BOX_THRESHOLD=0.35
SEMANTIC_TEXT_THRESHOLD=0.25
SEMANTIC_RISK_TRIGGER_THRESHOLD=0.6
SEMANTIC_CACHE_TTL=60
SEMANTIC_MAX_CONCURRENT=2
```

### CLI Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--enable-semantic` | Enable semantic layer | false |
| `--semantic-prompt` | Initial query | None |
| `--semantic-risk-threshold` | Auto-trigger threshold | 0.6 |

---

## API Endpoints

### Submit Query
```http
POST /semantic/query
Content-Type: application/json
X-API-Key: your-api-key

{
    "prompt": "person with bag near restricted area",
    "priority": 10
}
```

### Get Results
```http
GET /semantic/results
X-API-Key: your-api-key
```

### List Active Prompts
```http
GET /semantic/prompts
X-API-Key: your-api-key
```

### Remove Query
```http
DELETE /semantic/query/{prompt_id}
X-API-Key: your-api-key
```

---

## Performance

### Real-time Preservation

The semantic layer preserves real-time FPS through:

1. **Event-driven triggers**: No per-frame DINO inference
2. **Async execution**: ThreadPoolExecutor for non-blocking inference
3. **Result caching**: LRU cache with TTL for repeated queries
4. **Concurrent limit**: Max 2 parallel DINO requests by default

### Benchmark (Typical)

| Metric | Without Semantic | With Semantic |
|--------|------------------|---------------|
| FPS | ~28-32 | ~26-30 |
| Latency | ~35ms | ~38ms |
| Memory | ~2GB | ~4GB (with DINO) |

*DINO inference runs async, so main loop impact is minimal.*

---

## Installation

### Requirements

```bash
pip install groundingdino-py torch torchvision
```

### Model Weights

1. Download Grounding DINO weights:
```bash
mkdir weights
wget https://github.com/IDEA-Research/GroundingDINO/releases/download/v0.1.0-alpha/groundingdino_swint_ogc.pth -O weights/groundingdino_swint_ogc.pth
```

2. Set environment variables:
```bash
export DINO_CONFIG_PATH="GroundingDINO/groundingdino/config/GroundingDINO_SwinT_OGC.py"
export DINO_WEIGHTS_PATH="weights/groundingdino_swint_ogc.pth"
```

---

## Usage Example

```bash
# Full pipeline with semantic layer
python main.py \
    --input camera.mp4 \
    --output result.mp4 \
    --enable-analysis \
    --enable-risk \
    --enable-semantic \
    --semantic-prompt "person with a bag near restricted area"
```

Console output:
```
[SEMANTIC] Track 5: 'person with bag' (0.87 conf) -> Risk: 0.72
```

---

## Fallback Mode

If Grounding DINO is not installed, the system runs in **fallback mode**:
- No semantic detection performed
- All other phases continue normally
- Warning logged at startup

Enable debug mode for simulated detections:
```bash
export AEGIS_DEBUG=true
```
