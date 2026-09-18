"""
AegisAI - Health Check Endpoints

Provides /healthz (liveness) and /readyz (readiness) endpoints
for container orchestration (Docker, Kubernetes).

- /healthz: Is the process alive? Always returns 200 if the server is running.
- /readyz: Is the service ready to accept traffic? Checks database and model availability.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Response

from aegis.api.security import api_authentication_readiness

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

    # A missing API credential must never be treated as a runnable production
    # service. Liveness remains independent so an orchestrator can report the
    # configuration problem rather than restart-looping a healthy process.
    auth_ok, auth_message = api_authentication_readiness()
    checks["api_authentication"] = {
        "status": "ok" if auth_ok else "error",
        "message": auth_message,
    }
    if not auth_ok:
        all_healthy = False

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
        checks["database"] = {"status": "error", "message": f"Database status unavailable: {type(exc).__name__}"}
        all_healthy = False

    # Check detector files without instantiating models or triggering network
    # downloads. A configured-but-missing model is unavailable, not healthy.
    try:
        from pathlib import Path
        from config import DetectionConfig

        detector_config = DetectionConfig()
        base_model_path = Path(detector_config.model_path)
        base_model_available = base_model_path.is_file()
        checks["base_detector"] = {
            "status": "ok" if base_model_available else "error",
            "message": (
                f"Base detector weights available: {base_model_path.name}"
                if base_model_available
                else f"Base detector weights unavailable: {base_model_path}"
            ),
        }
        if not base_model_available:
            all_healthy = False

        weapon_model_path = Path(detector_config.weapon_model_path)
        weapon_model_available = weapon_model_path.is_file()
        checks["weapon_detector"] = {
            "status": "ok" if weapon_model_available else "warning",
            "message": (
                f"Custom weapon detector weights available: {weapon_model_path.name}"
                if weapon_model_available
                else f"Custom weapon detector unavailable: {weapon_model_path}"
            ),
        }
    except Exception as exc:
        checks["base_detector"] = {"status": "error", "message": "Detector configuration could not be read"}
        checks["weapon_detector"] = {"status": "warning", "message": "Weapon detector status could not be read"}
        all_healthy = False

    # Tracking has no weight file but must be importable for the detection path
    # to produce stable identities and temporal risk.
    try:
        from aegis.tracking.bytetrack_tracker import ByteTrackTracker  # noqa: F401
        checks["tracking"] = {"status": "ok", "message": "Tracking implementation is available"}
    except Exception:
        checks["tracking"] = {"status": "error", "message": "Tracking implementation is unavailable"}
        all_healthy = False

    checks["evidence_persistence"] = {
        "status": checks.get("database", {}).get("status", "error"),
        "message": (
            "Database-backed event and alert persistence is available"
            if checks.get("database", {}).get("status") == "ok"
            else "Database-backed evidence persistence is unavailable"
        ),
    }

    # The evidence database alone is insufficient if snapshots cannot be
    # written.  This is a required part of high-risk alert evidence.
    snapshot_root = Path("data/output/snapshots")
    try:
        snapshot_root.mkdir(parents=True, exist_ok=True)
        storage_available = snapshot_root.is_dir() and os.access(snapshot_root, os.W_OK)
        checks["evidence_storage"] = {
            "status": "ok" if storage_available else "error",
            "message": (
                f"Snapshot storage writable: {snapshot_root}"
                if storage_available
                else f"Snapshot storage is not writable: {snapshot_root}"
            ),
        }
        if not storage_available:
            all_healthy = False
    except Exception as exc:
        checks["evidence_storage"] = {"status": "error", "message": f"Snapshot storage unavailable: {type(exc).__name__}"}
        all_healthy = False

    # Camera sources are live runtime state, not a static registry.  Zero
    # configured cameras is a warning rather than a fabricated healthy feed.
    try:
        from aegis.api.routes.cameras import get_camera_manager

        cameras = get_camera_manager().list_cameras()
        online = sum(
            1
            for camera in cameras
            if (camera.get("runtime") or {}).get("status") == "online"
            and bool((camera.get("runtime") or {}).get("running"))
        )
        checks["camera_sources"] = {
            "status": "ok" if cameras else "warning",
            "message": f"{online} live camera source(s) of {len(cameras)} configured",
        }
    except Exception as exc:
        checks["camera_sources"] = {"status": "error", "message": f"Camera runtime unavailable: {type(exc).__name__}"}
        all_healthy = False

    # WebSocket support is an internal API capability.  An idle client count
    # is normal; failure to load the secured manager is not.
    try:
        from aegis.api.websocket import manager

        checks["websocket"] = {
            "status": "ok",
            "message": f"Secured WebSocket service available ({manager.client_count} client(s) connected)",
        }
    except Exception as exc:
        checks["websocket"] = {"status": "error", "message": f"WebSocket service unavailable: {type(exc).__name__}"}
        all_healthy = False

    # An LLM provider is optional for the deterministic operator fallback,
    # but health must say when provider-backed chat/voice is unavailable.
    try:
        from aegis.settings import get_settings

        configured_key = str(getattr(get_settings().gemini, "api_key", "") or os.getenv("GEMINI_API_KEY", "")).strip()
        checks["agent_provider"] = {
            "status": "ok" if configured_key else "warning",
            "message": "Gemini provider configured" if configured_key else "Gemini provider unavailable; verified local fallback only",
        }
    except Exception as exc:
        checks["agent_provider"] = {"status": "warning", "message": f"Agent provider status unavailable: {type(exc).__name__}"}

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

    has_warning = any(check.get("status") == "warning" for check in checks.values())
    if not all_healthy:
        response.status_code = 503

    return {
        # Warnings are intentionally visible as a distinct state: the API can
        # serve authenticated traffic, but one or more non-blocking
        # capabilities (for example custom weapon weights or an LLM provider)
        # are unavailable.  Critical errors remain a 503/not_ready result.
        "status": "not_ready" if not all_healthy else "degraded" if has_warning else "ready",
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
