"""
AegisAI - Health Check Endpoints

Provides /healthz (liveness) and /readyz (readiness) endpoints
for container orchestration (Docker, Kubernetes).

- /healthz: Is the process alive? Always returns 200 if the server is running.
- /readyz: Is the service ready to accept traffic? Checks database and model availability.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Response

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/healthz", include_in_schema=False)
async def liveness() -> dict:
    """
    Liveness probe — returns 200 if the API process is alive.

    Used by Docker HEALTHCHECK and Kubernetes livenessProbe.
    Should NOT check external dependencies (DB, Redis) —
    those belong in the readiness probe.
    """
    return {
        "status": "alive",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/readyz", include_in_schema=False)
async def readiness(response: Response) -> dict:
    """
    Readiness probe — returns 200 only when the service can handle requests.

    Checks:
    - Database connectivity
    - Model availability (optional)

    Used by Kubernetes readinessProbe and load balancer health checks.
    """
    checks: dict[str, dict] = {}
    all_healthy = True

    # Check database
    try:
        from aegis.database.connection import check_connection
        db_ok = check_connection()
        checks["database"] = {
            "status": "ok" if db_ok else "error",
            "message": "Connected" if db_ok else "Connection failed",
        }
        if not db_ok:
            all_healthy = False
    except Exception as exc:
        checks["database"] = {"status": "skip", "message": f"Not configured: {exc}"}

    # Check YOLO model availability
    try:
        from pathlib import Path
        model_path = Path("yolo11n.pt")
        model_exists = model_path.exists()
        if not model_exists:
            # Try yolov8n.pt fallback
            model_path = Path("yolov8n.pt")
            model_exists = model_path.exists()
        checks["yolo_model"] = {
            "status": "ok" if model_exists else "warning",
            "message": f"Found {model_path.name}" if model_exists else "No model file found",
        }
    except Exception as exc:
        checks["yolo_model"] = {"status": "skip", "message": str(exc)}

    # Check Redis event bus
    try:
        from aegis.core.events import get_event_bus
        bus_health = get_event_bus().health_check()
        checks["redis"] = {
            "status": "ok" if bus_health["connected"] else "warning",
            "message": bus_health["mode"],
        }
    except Exception as exc:
        checks["redis"] = {"status": "skip", "message": str(exc)}

    if not all_healthy:
        response.status_code = 503

    return {
        "status": "ready" if all_healthy else "not_ready",
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
