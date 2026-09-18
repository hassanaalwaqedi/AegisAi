"""
AegisAI camera source API.

Production camera management, browser frame ingestion, uploaded video
processing, and camera-scoped WebSocket streams.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from aegis.api.security import (
    WEBSOCKET_AUTH_PROTOCOL,
    verify_api_key,
    verify_websocket_auth,
    websocket_subprotocol_token,
)
from aegis.camera import (
    CameraConfig,
    CameraConnectionStatus,
    CameraSourceFactory,
    CameraSourceType,
    MultiCameraPipelineManager,
    frame_to_data_url,
)
from aegis.camera.connection_tests import (
    CameraConnectionTestResult,
    get_connection_test_store,
    result_for_invalid_url,
)
from aegis.camera.utils import build_rtsp_url


router = APIRouter()
cameras_router = APIRouter(prefix="/cameras", tags=["cameras"])
camera_ingestion_router = APIRouter(prefix="/camera", tags=["camera-ingestion"])
videos_router = APIRouter(prefix="/videos", tags=["videos"])

UPLOAD_DIR = Path("data/uploads")
UPLOAD_INDEX_PATH = UPLOAD_DIR / "videos.json"
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}


_camera_manager: Optional[MultiCameraPipelineManager] = None


def camera_preview_interval_seconds() -> float:
    """Bound preview delivery without changing the detection pipeline."""
    raw_value = os.getenv("AEGIS_CAMERA_STREAM_FPS", "30")
    try:
        frames_per_second = float(raw_value)
    except (TypeError, ValueError):
        frames_per_second = 30.0
    return 1.0 / max(1.0, min(frames_per_second, 30.0))


def get_camera_manager() -> MultiCameraPipelineManager:
    global _camera_manager
    if _camera_manager is None:
        _camera_manager = MultiCameraPipelineManager()
    return _camera_manager


def set_camera_manager(manager: MultiCameraPipelineManager) -> None:
    global _camera_manager
    _camera_manager = manager


class CameraCreateRequest(BaseModel):
    camera_id: str = Field(..., min_length=1, max_length=80)
    source_type: CameraSourceType
    name: Optional[str] = Field(default=None, max_length=160)
    location: Optional[str] = Field(default=None, max_length=200)
    enabled: bool = True
    url: Optional[str] = None
    device_index: Optional[int] = Field(default=None, ge=0)
    video_id: Optional[str] = None
    upload_path: Optional[str] = None
    auto_start: bool = False
    # Guided RTSP registration fields.  ``url`` remains available for the
    # advanced mode and existing API clients.
    rtsp_protocol: Optional[str] = None
    rtsp_host: Optional[str] = Field(default=None, max_length=255)
    rtsp_port: Optional[int] = Field(default=None, ge=1, le=65535)
    rtsp_path: Optional[str] = Field(default=None, max_length=1024)
    rtsp_username: Optional[str] = Field(default=None, max_length=255)
    rtsp_password: Optional[str] = Field(default=None, max_length=1024)
    connection_test_id: Optional[str] = Field(default=None, max_length=128)
    allow_unverified_save: bool = False
    connection_timeout: float = Field(default=5.0, gt=0, le=60)
    max_retries: int = Field(default=10, ge=0, le=100)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not value.strip():
            return None
        return value

    def to_config(self) -> CameraConfig:
        url = self.url
        if self.source_type == CameraSourceType.RTSP_STREAM and self.rtsp_host:
            url = build_rtsp_url(
                protocol=self.rtsp_protocol or "rtsp",
                host=self.rtsp_host,
                port=self.rtsp_port or 554,
                stream_path=self.rtsp_path or "",
                username=self.rtsp_username,
                password=self.rtsp_password,
            )
        return CameraConfig(
            camera_id=self.camera_id,
            source_type=self.source_type,
            name=self.name,
            location=self.location,
            enabled=self.enabled,
            url=url,
            device_index=self.device_index,
            upload_path=self.upload_path,
            video_id=self.video_id,
            connection_timeout=self.connection_timeout,
            max_retries=self.max_retries,
            metadata=self.metadata,
        )


class CameraUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, max_length=160)
    location: Optional[str] = Field(default=None, max_length=200)
    enabled: Optional[bool] = None
    url: Optional[str] = None
    device_index: Optional[int] = Field(default=None, ge=0)
    connection_timeout: Optional[float] = Field(default=None, gt=0, le=60)
    max_retries: Optional[int] = Field(default=None, ge=0, le=100)
    metadata: Optional[Dict[str, Any]] = None


class BrowserFrameRequest(BaseModel):
    camera_id: str = Field(..., min_length=1, max_length=80)
    frame: str = Field(..., min_length=32)


class CameraZoneOverlay(BaseModel):
    """A persisted camera zone in source-frame pixel coordinates."""

    zone_id: str
    name: str
    type: str
    bounds: List[float]
    description: str = ""
    active: bool = True


class CameraHeatmapCell(BaseModel):
    """An occupancy cell calculated from actual recent track positions."""

    x: float
    y: float
    width: float
    height: float
    count: int
    intensity: float


class CameraOverlayResponse(BaseModel):
    camera_id: str
    frame_width: Optional[int] = None
    frame_height: Optional[int] = None
    zones: List[CameraZoneOverlay]
    heatmap: List[CameraHeatmapCell]
    heatmap_samples: int
    generated_at: str


class ProcessVideoRequest(BaseModel):
    camera_id: Optional[str] = Field(default=None, min_length=1, max_length=80)


def _http_error(status_code: int, message: str, detail: Optional[Any] = None) -> HTTPException:
    payload: Dict[str, Any] = {"message": message}
    if detail is not None:
        payload["detail"] = detail
    return HTTPException(status_code=status_code, detail=payload)


def _record_camera_configuration_audit(
    action: str,
    camera_id: str,
    *,
    actor: Optional[str],
    changed_fields: Optional[List[str]] = None,
) -> None:
    """Audit camera configuration changes without storing source URLs."""
    from aegis.audit import record_audit

    record_audit(
        action,
        actor_id=(str(actor or "").strip()[:160] or "api-key-operator"),
        resource_type="camera",
        resource_id=camera_id,
        details={"changed_fields": sorted(changed_fields or [])},
    )


def _read_upload_index() -> Dict[str, Any]:
    if not UPLOAD_INDEX_PATH.exists():
        return {"videos": {}}
    try:
        return json.loads(UPLOAD_INDEX_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        raise _http_error(500, "Video upload index is unreadable.", str(exc)) from exc


def _write_upload_index(index: Dict[str, Any]) -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_INDEX_PATH.write_text(json.dumps(index, indent=2), encoding="utf-8")


def _get_video_record(video_id: str) -> Dict[str, Any]:
    index = _read_upload_index()
    record = index.get("videos", {}).get(video_id)
    if not record:
        raise _http_error(404, f"Uploaded video {video_id} was not found.")
    path = Path(record["path"])
    if not path.exists():
        raise _http_error(410, f"Uploaded video {video_id} is no longer available on disk.")
    return record


def _positive_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _detection_observed_at(item: Dict[str, Any]) -> Optional[datetime]:
    raw_value = item.get("last_seen") or item.get("timestamp")
    if not raw_value:
        return None
    try:
        observed_at = datetime.fromisoformat(str(raw_value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if observed_at.tzinfo is None:
        return observed_at.replace(tzinfo=timezone.utc)
    return observed_at.astimezone(timezone.utc)


def _current_camera_detections(
    detections: List[Dict[str, Any]],
    *,
    now: Optional[datetime] = None,
    max_age_seconds: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Return one fresh detection per object from the newest processed frame."""
    candidates = detections
    if max_age_seconds is not None:
        current_time = now or datetime.now(timezone.utc)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)
        candidates = [
            item
            for item in detections
            if (observed_at := _detection_observed_at(item)) is None
            or (current_time - observed_at).total_seconds() <= max_age_seconds
        ]

    latest_frame = max(
        (_positive_int(item.get("frame_number") or item.get("frame_id")) for item in candidates),
        default=0,
    )
    current_frame = (
        [
            item
            for item in candidates
            if _positive_int(item.get("frame_number") or item.get("frame_id")) == latest_frame
        ]
        if latest_frame
        else candidates
    )
    unique: Dict[str, Dict[str, Any]] = {}
    for index, item in enumerate(current_frame):
        track_id = str(item.get("track_id") or "").strip()
        if track_id:
            identity = f"track:{track_id}"
        else:
            bbox = item.get("bbox")
            identity = f"detection:{item.get('class_name')}:{bbox}:{index}"
        unique[identity] = item
    return list(unique.values())


def _normalise_camera_zones(raw_zones: Any) -> List[CameraZoneOverlay]:
    """Validate persisted metadata before returning it to an overlay client."""
    if not isinstance(raw_zones, list):
        return []

    zones: List[CameraZoneOverlay] = []
    for index, raw_zone in enumerate(raw_zones):
        if not isinstance(raw_zone, dict):
            continue
        raw_bounds = raw_zone.get("bounds")
        if not isinstance(raw_bounds, list) or len(raw_bounds) != 4:
            continue
        try:
            x1, y1, x2, y2 = [float(value) for value in raw_bounds]
        except (TypeError, ValueError):
            continue
        if x2 <= x1 or y2 <= y1:
            continue
        zones.append(
            CameraZoneOverlay(
                zone_id=str(raw_zone.get("id") or raw_zone.get("zone_id") or f"zone-{index + 1}"),
                name=str(raw_zone.get("name") or f"Zone {index + 1}"),
                type=str(raw_zone.get("type") or "RESTRICTED").upper(),
                bounds=[x1, y1, x2, y2],
                description=str(raw_zone.get("description") or ""),
                active=bool(raw_zone.get("active", True)),
            )
        )
    return zones


def _build_camera_heatmap(
    detections: List[Dict[str, Any]],
    frame_width: int,
    frame_height: int,
) -> List[CameraHeatmapCell]:
    """Aggregate recent track centres into a compact source-frame grid."""
    if frame_width <= 0 or frame_height <= 0:
        return []

    columns = min(12, max(4, round(frame_width / 80)))
    rows = min(9, max(3, round(frame_height / 80)))
    cell_width = frame_width / columns
    cell_height = frame_height / rows
    counts: Dict[tuple[int, int], int] = {}

    for detection in detections:
        bbox = detection.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4:
            continue
        try:
            x1, y1, x2, y2 = [float(value) for value in bbox]
        except (TypeError, ValueError):
            continue
        center_x = min(max((x1 + x2) / 2, 0.0), frame_width - 0.001)
        center_y = min(max((y1 + y2) / 2, 0.0), frame_height - 0.001)
        column = min(int(center_x / cell_width), columns - 1)
        row = min(int(center_y / cell_height), rows - 1)
        counts[(column, row)] = counts.get((column, row), 0) + 1

    if not counts:
        return []

    peak = max(counts.values())
    return [
        CameraHeatmapCell(
            x=column * cell_width,
            y=row * cell_height,
            width=cell_width,
            height=cell_height,
            count=count,
            intensity=round(count / peak, 3),
        )
        for (column, row), count in sorted(counts.items())
    ]


@cameras_router.get("")
async def list_cameras(_: bool = Depends(verify_api_key)):
    manager = get_camera_manager()
    cameras = manager.list_cameras()
    return {"count": len(cameras), "cameras": cameras}


@cameras_router.get("/{camera_id}/overlays", response_model=CameraOverlayResponse)
async def get_camera_overlays(
    camera_id: str,
    history_limit: int = Query(default=600, ge=1, le=1000),
    _: bool = Depends(verify_api_key),
):
    """Return configured zones and heatmap cells calculated from real tracks."""
    manager = get_camera_manager()
    camera = manager.get_camera(camera_id)
    if camera is None:
        raise _http_error(404, f"Camera {camera_id} was not found.")

    runtime = camera.get("runtime") or {}
    width = _positive_int(runtime.get("width"))
    height = _positive_int(runtime.get("height"))
    metadata = camera.get("metadata") or {}
    zones = _normalise_camera_zones(metadata.get("zones") or metadata.get("restricted_zones") or [])
    detections = manager.get_camera_detections(camera_id, limit=history_limit)
    heatmap = _build_camera_heatmap(detections, width, height)

    return CameraOverlayResponse(
        camera_id=camera_id,
        frame_width=width or None,
        frame_height=height or None,
        zones=zones,
        heatmap=heatmap,
        heatmap_samples=sum(cell.count for cell in heatmap),
        generated_at=datetime.utcnow().isoformat(),
    )


@cameras_router.post("")
async def create_camera(
    request: CameraCreateRequest,
    x_aegis_actor: Optional[str] = Header(default=None),
    _: bool = Depends(verify_api_key),
):
    manager = get_camera_manager()
    try:
        config = request.to_config()
        verified_test = get_connection_test_store().verified_result(
            request.connection_test_id, config
        )
        requires_verified_test = config.source_type == CameraSourceType.RTSP_STREAM
        explicitly_disabled_unverified = (
            request.allow_unverified_save and not config.enabled and not request.auto_start
        )
        if requires_verified_test and not verified_test and not explicitly_disabled_unverified:
            raise _http_error(
                409,
                "A successful RTSP connection test is required before saving an active camera. "
                "Choose Save as disabled to keep an unverified configuration.",
            )
        created = manager.create_camera(
            config,
            auto_start=request.auto_start,
            connection_verified=bool(verified_test),
            connection_test=(verified_test.to_persisted_summary() if verified_test else None),
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise _http_error(400, str(exc)) from exc
    except Exception as exc:
        raise _http_error(500, "Camera could not be created.", str(exc)) from exc
    _record_camera_configuration_audit("camera.created", request.camera_id, actor=x_aegis_actor)
    return created


@cameras_router.post("/test-connection")
async def test_camera_connection(request: CameraCreateRequest, _: bool = Depends(verify_api_key)):
    try:
        config = request.to_config()
        result = CameraSourceFactory().test_connection_details(config)
    except ValueError as exc:
        result = result_for_invalid_url(request.url, str(exc))
    except Exception as exc:
        result = CameraConnectionTestResult(
            ok=False,
            status="failed",
            error_category="connection_failed",
            error_message="Camera connection test could not complete.",
        )

    payload = result.to_public_dict()
    if "config" in locals():
        payload["test_id"] = get_connection_test_store().record(config, result)
    return payload


@cameras_router.get("/{camera_id}")
async def get_camera(camera_id: str, _: bool = Depends(verify_api_key)):
    camera = get_camera_manager().get_camera(camera_id)
    if camera is None:
        raise _http_error(404, f"Camera {camera_id} was not found.")
    return camera


@cameras_router.patch("/{camera_id}")
async def update_camera(
    camera_id: str,
    request: CameraUpdateRequest,
    x_aegis_actor: Optional[str] = Header(default=None),
    _: bool = Depends(verify_api_key),
):
    changes = request.model_dump(exclude_unset=True)
    try:
        updated = get_camera_manager().update_camera(camera_id, changes)
    except KeyError as exc:
        raise _http_error(404, f"Camera {camera_id} was not found.") from exc
    except ValueError as exc:
        raise _http_error(400, str(exc)) from exc
    except Exception as exc:
        raise _http_error(500, "Camera could not be updated.", str(exc)) from exc
    _record_camera_configuration_audit(
        "camera.configuration_updated",
        camera_id,
        actor=x_aegis_actor,
        changed_fields=list(changes),
    )
    return updated


@cameras_router.delete("/{camera_id}")
async def delete_camera(
    camera_id: str,
    x_aegis_actor: Optional[str] = Header(default=None),
    _: bool = Depends(verify_api_key),
):
    deleted = get_camera_manager().delete_camera(camera_id)
    if not deleted:
        raise _http_error(404, f"Camera {camera_id} was not found.")
    _record_camera_configuration_audit("camera.deleted", camera_id, actor=x_aegis_actor)
    return {"message": f"Camera {camera_id} deleted."}


@cameras_router.post("/{camera_id}/start")
async def start_camera(camera_id: str, _: bool = Depends(verify_api_key)):
    try:
        return get_camera_manager().start_camera(camera_id)
    except KeyError as exc:
        raise _http_error(404, f"Camera {camera_id} was not found.") from exc


@cameras_router.post("/{camera_id}/stop")
async def stop_camera(camera_id: str, _: bool = Depends(verify_api_key)):
    try:
        return get_camera_manager().stop_camera(camera_id)
    except KeyError as exc:
        raise _http_error(404, f"Camera {camera_id} was not found.") from exc


@cameras_router.get("/{camera_id}/status")
async def get_camera_status(camera_id: str, _: bool = Depends(verify_api_key)):
    try:
        manager = get_camera_manager()
        status = manager.get_status(camera_id)
        recent_detections = manager.get_camera_detections(camera_id, limit=200)
        detections = _current_camera_detections(
            recent_detections,
            max_age_seconds=5.0,
        )
        events = manager.get_camera_events(camera_id, limit=20)
        stats = manager.ingestion.get_stats()
        registry = manager.get_object_registry(camera_id)
        return {
            **status,
            "active_detections_count": len(detections),
            "people_count": sum(1 for item in detections if str(item.get("class_name", "")).lower() == "person"),
            "vehicles_count": sum(1 for item in detections if str(item.get("class_name", "")).lower() in {"car", "truck", "bus", "motorcycle", "bicycle"}),
            "weapons_count": sum(1 for item in detections if item.get("is_weapon")),
            "weapon_associations_count": sum(1 for item in detections if item.get("association_type") in {"near", "overlap", "contained"}),
            "critical_associations_count": sum(1 for item in detections if item.get("verification_status") == "critical"),
            "object_registry": registry,
            "object_registry_count": len(registry),
            "pipeline": {
                "recent_detections": len(recent_detections),
                "recent_events": len(events),
                "frames_processed": stats.get("frames_processed", 0),
                "total_detections": stats.get("total_detections", 0),
                "model": stats.get("model", {}),
            },
        }
    except KeyError as exc:
        raise _http_error(404, f"Camera {camera_id} was not found.") from exc


@cameras_router.get("/{camera_id}/snapshot")
async def get_camera_snapshot(camera_id: str, _: bool = Depends(verify_api_key)):
    try:
        snapshot = get_camera_manager().get_snapshot(camera_id)
    except KeyError as exc:
        raise _http_error(404, f"Camera {camera_id} was not found.") from exc

    if not snapshot:
        raise _http_error(404, "No camera frame is available yet.")
    return Response(content=snapshot, media_type="image/jpeg")


@cameras_router.get("/{camera_id}/events")
async def get_camera_events(
    camera_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    _: bool = Depends(verify_api_key),
):
    if get_camera_manager().get_camera(camera_id) is None:
        raise _http_error(404, f"Camera {camera_id} was not found.")
    events = get_camera_manager().get_camera_events(camera_id, limit=limit)
    return {"count": len(events), "events": events}


@cameras_router.get("/{camera_id}/detections")
async def get_camera_detections(
    camera_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    _: bool = Depends(verify_api_key),
):
    if get_camera_manager().get_camera(camera_id) is None:
        raise _http_error(404, f"Camera {camera_id} was not found.")
    detections = get_camera_manager().get_camera_detections(camera_id, limit=limit)
    return {"count": len(detections), "detections": detections}


@router.websocket("/ws/cameras/{camera_id}/frames")
async def camera_frames_websocket(websocket: WebSocket, camera_id: str):
    if not await verify_websocket_auth(websocket):
        return
    await websocket.accept(
        subprotocol=WEBSOCKET_AUTH_PROTOCOL if websocket_subprotocol_token(websocket) else None
    )
    manager = get_camera_manager()
    preview_interval = camera_preview_interval_seconds()
    try:
        while True:
            camera = manager.get_camera(camera_id)
            if camera is None:
                await websocket.send_json({
                    "type": "error",
                    "camera_id": camera_id,
                    "message": f"Camera {camera_id} was not found.",
                    "timestamp": datetime.utcnow().isoformat(),
                })
                await asyncio.sleep(2.0)
                continue

            snapshot = manager.get_snapshot(camera_id)
            if snapshot:
                # Embed the latest detections with every frame so that the
                # client always renders boxes that belong to the same capture
                # moment — eliminating stale-detection misalignment.
                detections = manager.get_camera_detections(camera_id, limit=80)
                await websocket.send_json({
                    "type": "frame",
                    "camera_id": camera_id,
                    "status": camera["runtime"]["status"],
                    "timestamp": datetime.utcnow().isoformat(),
                    "frame": frame_to_data_url(snapshot),
                    "detections": detections,
                })
            else:
                await websocket.send_json({
                    "type": "status",
                    "camera_id": camera_id,
                    "status": camera["runtime"]["status"],
                    "error_message": camera["runtime"].get("error_message"),
                    "timestamp": datetime.utcnow().isoformat(),
                })
            await asyncio.sleep(preview_interval)
    except WebSocketDisconnect:
        return


@router.websocket("/ws/cameras/{camera_id}/events")
async def camera_events_websocket(websocket: WebSocket, camera_id: str):
    if not await verify_websocket_auth(websocket):
        return
    await websocket.accept(
        subprotocol=WEBSOCKET_AUTH_PROTOCOL if websocket_subprotocol_token(websocket) else None
    )
    manager = get_camera_manager()
    sent_event_ids: set[str] = set()
    try:
        while True:
            if manager.get_camera(camera_id) is None:
                await websocket.send_json({
                    "type": "error",
                    "camera_id": camera_id,
                    "message": f"Camera {camera_id} was not found.",
                    "timestamp": datetime.utcnow().isoformat(),
                })
                await asyncio.sleep(2.0)
                continue

            events = manager.get_camera_events(camera_id, limit=50)
            new_events = []
            for event in events:
                event_id = str(event.get("event_id") or event.get("id") or f"{event.get('timestamp')}-{event.get('status')}")
                if event_id not in sent_event_ids:
                    sent_event_ids.add(event_id)
                    new_events.append(event)

            if new_events:
                await websocket.send_json({
                    "type": "events",
                    "camera_id": camera_id,
                    "timestamp": datetime.utcnow().isoformat(),
                    "events": new_events,
                })
            else:
                # There is no event payload to publish.  Send only a
                # heartbeat/status so an idle camera is never represented as
                # a stream of fabricated "live events".
                camera = manager.get_camera(camera_id) or {}
                runtime = camera.get("runtime") or {}
                await websocket.send_json({
                    "type": "heartbeat",
                    "camera_id": camera_id,
                    "status": runtime.get("status"),
                    "timestamp": datetime.utcnow().isoformat(),
                })
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        return


@camera_ingestion_router.post("/browser-frame")
async def ingest_browser_frame(request: BrowserFrameRequest, _: bool = Depends(verify_api_key)):
    try:
        return get_camera_manager().ingest_browser_frame(request.camera_id, request.frame)
    except KeyError as exc:
        raise _http_error(404, f"Camera {request.camera_id} was not found.") from exc
    except ValueError as exc:
        raise _http_error(400, str(exc)) from exc
    except Exception as exc:
        raise _http_error(500, "Browser frame could not be processed.", str(exc)) from exc


@videos_router.post("/upload")
async def upload_video(file: UploadFile = File(...), _: bool = Depends(verify_api_key)):
    original_name = Path(file.filename or "upload").name
    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_VIDEO_EXTENSIONS:
        raise _http_error(400, f"Unsupported video extension {extension or '(none)'}.")

    video_id = uuid.uuid4().hex
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    destination = UPLOAD_DIR / f"{video_id}{extension}"

    try:
        with destination.open("wb") as output:
            shutil.copyfileobj(file.file, output)
    except Exception as exc:
        raise _http_error(500, "Uploaded video could not be saved.", str(exc)) from exc
    finally:
        await file.close()

    size_bytes = destination.stat().st_size
    record = {
        "video_id": video_id,
        "filename": original_name,
        "content_type": file.content_type,
        "size_bytes": size_bytes,
        "path": str(destination),
        "uploaded_at": datetime.utcnow().isoformat(),
    }

    index = _read_upload_index()
    index.setdefault("videos", {})[video_id] = record
    _write_upload_index(index)

    return {
        "video_id": video_id,
        "filename": original_name,
        "content_type": file.content_type,
        "size_bytes": size_bytes,
        "uploaded_at": record["uploaded_at"],
    }


@videos_router.post("/{video_id}/process")
async def process_video(video_id: str, request: ProcessVideoRequest, _: bool = Depends(verify_api_key)):
    record = _get_video_record(video_id)
    try:
        return get_camera_manager().process_uploaded_video(
            video_id=video_id,
            upload_path=record["path"],
            camera_id=request.camera_id,
        )
    except ValueError as exc:
        raise _http_error(400, str(exc)) from exc
    except Exception as exc:
        raise _http_error(500, "Uploaded video could not be processed.", str(exc)) from exc


router.include_router(cameras_router)
router.include_router(camera_ingestion_router)
router.include_router(videos_router)
