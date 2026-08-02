"""Source-fresh assembly of the Phase 0 Intelligence operational context.

The live operational data path is intentionally explicit:

``MultiCameraPipelineManager -> FrameIngestionService -> APIState``.

Durable event writes on that path use ``aegis.database``.  The legacy
``aegis.db`` models/repositories are not queried or combined here.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from aegis.intelligence.context_schemas import (
    AIContext,
    AlertsContext,
    Availability,
    CameraItem,
    CamerasContext,
    DetectionSummary,
    EvidenceRef,
    EventItem,
    Freshness,
    HealthCheck,
    IncidentsCapability,
    IntelligenceContext,
    IntelligenceSuggestion,
    OverallContext,
    PipelineContext,
    PipelineStageContext,
    RiskAlertItem,
    SemanticContext,
    TrackItem,
    VoiceCapability,
)


REFRESH_AFTER_SECONDS = 10
CAMERA_STALE_AFTER_SECONDS = 10
TRACK_STALE_AFTER_SECONDS = 15
STATISTICS_STALE_AFTER_SECONDS = 20
EVENT_STALE_AFTER_SECONDS = 60
MAX_CONTEXT_EVENTS = 20
MAX_CONTEXT_TRACKS = 20


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _default_state_getter() -> Any:
    from aegis.api.state import get_state

    return get_state()


def _default_camera_manager_getter() -> Any:
    # The cameras router owns the singleton used by actual frontend ingestion.
    from aegis.api.routes.cameras import get_camera_manager

    return get_camera_manager()


def _default_pipeline_getter() -> Any:
    from aegis.pipeline.startup import get_pipeline

    return get_pipeline()


def _default_event_bus_getter() -> Any:
    from aegis.core.events import get_event_bus

    return get_event_bus()


def _default_database_check() -> bool:
    from aegis.database.connection import check_connection

    return check_connection()


def _default_persistence_status_getter() -> Any:
    from aegis.database.persistence import get_persistence_status

    return get_persistence_status()


def _default_persistence_readiness_check() -> Tuple[bool, Optional[str]]:
    from aegis.database.persistence import check_event_persistence_ready

    return check_event_persistence_ready()


def _default_settings_getter() -> Any:
    from aegis.settings import get_settings

    return get_settings()


def _as_datetime(value: Any) -> Optional[datetime]:
    """Convert a source timestamp to UTC without inventing a replacement."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _string(value: Any) -> Optional[str]:
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def _number(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class _EvidenceValidator:
    """Validate evidence against the exact server snapshot used for a context.

    A citation is emitted only after its stable ID, optional camera association,
    and source timestamp match a record read from the current camera manager or
    API state.  This deliberately avoids validating against the response being
    assembled, which would merely prove that a field was copied into itself.
    """

    def __init__(self, validated_at: datetime) -> None:
        self._validated_at = validated_at
        self._camera_ids: set[str] = set()
        self._events: Dict[str, Dict[str, Any]] = {}
        self._tracks: Dict[str, Dict[str, Any]] = {}
        self._failures: List[str] = []

    def register_cameras(self, records: Sequence[Dict[str, Any]]) -> None:
        for record in records:
            if isinstance(record, dict):
                camera_id = _string(record.get("camera_id"))
                if camera_id:
                    self._camera_ids.add(camera_id)

    def register_events(self, records: Sequence[Dict[str, Any]]) -> None:
        for record in records:
            if not isinstance(record, dict):
                continue
            event_id = _string(record.get("event_id")) or _string(record.get("id"))
            if event_id:
                self._events[event_id] = record

    def register_tracks(self, records: Sequence[Dict[str, Any]]) -> None:
        for record in records:
            if not isinstance(record, dict):
                continue
            track_id = _string(record.get("track_id"))
            if track_id:
                self._tracks[track_id] = record

    @property
    def status(self) -> Availability:
        return Availability.LIVE if not self._failures else Availability.DEGRADED

    @property
    def reason(self) -> Optional[str]:
        if not self._failures:
            return None
        return "One or more evidence references could not be verified against the current server snapshot."

    def evidence(
        self,
        *,
        kind: str,
        item_id: str,
        label: str,
        camera_id: Optional[str] = None,
        occurred_at: Optional[datetime] = None,
        is_risk_alert: bool = False,
    ) -> Optional[EvidenceRef]:
        if not self._matches(kind, item_id, camera_id, occurred_at, is_risk_alert):
            self._failures.append(f"{kind}:{item_id}")
            return None
        return EvidenceRef(
            kind=kind,
            id=item_id,
            camera_id=camera_id,
            occurred_at=occurred_at,
            label=label,
            server_validated=True,
            validated_at=self._validated_at,
        )

    def _matches(
        self,
        kind: str,
        item_id: str,
        camera_id: Optional[str],
        occurred_at: Optional[datetime],
        is_risk_alert: bool,
    ) -> bool:
        if kind == "health":
            referenced_camera_id = item_id.partition(":")[2]
            return (
                item_id.startswith("camera:")
                and camera_id == referenced_camera_id
                and referenced_camera_id in self._camera_ids
            )

        source = self._events.get(item_id) if kind in {"event", "alert"} else self._tracks.get(item_id) if kind == "track" else None
        if source is None:
            return False
        if kind == "alert" and not is_risk_alert:
            return False
        source_camera_id = _string(source.get("camera_id"))
        if source_camera_id != camera_id:
            return False
        source_timestamp = _as_datetime(source.get("timestamp")) if kind in {"event", "alert"} else _as_datetime(source.get("last_updated")) or _as_datetime(source.get("last_seen"))
        return source_timestamp == occurred_at


class IntelligenceContextService:
    """Build one truthful snapshot for `/api/intelligence/context`.

    Providers are injectable so the failure contract is testable without a
    database, Redis server, model, or camera device.
    """

    def __init__(
        self,
        *,
        state_getter: Callable[[], Any] = _default_state_getter,
        camera_manager_getter: Callable[[], Any] = _default_camera_manager_getter,
        pipeline_getter: Callable[[], Any] = _default_pipeline_getter,
        event_bus_getter: Callable[[], Any] = _default_event_bus_getter,
        database_check: Callable[[], bool] = _default_database_check,
        persistence_status_getter: Callable[[], Any] = _default_persistence_status_getter,
        persistence_readiness_check: Callable[[], Tuple[bool, Optional[str]]] = _default_persistence_readiness_check,
        settings_getter: Callable[[], Any] = _default_settings_getter,
        now: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._state_getter = state_getter
        self._camera_manager_getter = camera_manager_getter
        self._pipeline_getter = pipeline_getter
        self._event_bus_getter = event_bus_getter
        self._database_check = database_check
        self._persistence_status_getter = persistence_status_getter
        self._persistence_readiness_check = persistence_readiness_check
        self._settings_getter = settings_getter
        self._now = now

    def build(self) -> IntelligenceContext:
        """Collect a source-fresh snapshot without masking source failures."""
        observed_at = self._normalized_now()
        evidence_validator = _EvidenceValidator(observed_at)
        checks, check_reasons, pipeline = self._collect_health_checks(observed_at)
        cameras, camera_reasons = self._collect_cameras(observed_at, evidence_validator)
        events, alerts, tracks, detections, runtime_reasons = self._collect_runtime_data(
            observed_at, evidence_validator
        )
        semantic, semantic_reasons = self._collect_semantic(observed_at)
        suggestions = self._build_suggestions(cameras, alerts, evidence_validator)
        ai, ai_reasons = self._collect_ai(evidence_validator)

        reasons = self._deduplicate(
            [*check_reasons, *camera_reasons, *runtime_reasons, *semantic_reasons, *ai_reasons]
        )
        overall = OverallContext(
            status=self._overall_status(checks, cameras, alerts, tracks, detections, semantic, ai),
            degraded_reasons=reasons,
            checks=checks,
        )

        return IntelligenceContext(
            context_id=str(uuid.uuid4()),
            generated_at=observed_at,
            refresh_after_seconds=REFRESH_AFTER_SECONDS,
            overall=overall,
            cameras=cameras,
            alerts=alerts,
            incidents=IncidentsCapability(
                capability=Availability.UNAVAILABLE,
                reason="Incident management is not implemented; risk alerts are not incidents.",
                active_count=None,
            ),
            events=events,
            tracks=tracks,
            detections=detections,
            semantic=semantic,
            pipeline=pipeline,
            ai=ai,
            suggestions=suggestions,
        )

    def _normalized_now(self) -> datetime:
        value = self._now()
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    def _collect_health_checks(
        self, observed_at: datetime
    ) -> Tuple[List[HealthCheck], List[str], PipelineContext]:
        checks: List[HealthCheck] = [
            HealthCheck(name="api", status=Availability.LIVE, observed_at=observed_at)
        ]
        reasons: List[str] = []

        try:
            database_connected = bool(self._database_check())
            if database_connected:
                checks.append(
                    HealthCheck(name="database", status=Availability.LIVE, observed_at=observed_at)
                )
            else:
                detail = "Database connection check returned unavailable."
                checks.append(
                    HealthCheck(
                        name="database",
                        status=Availability.OFFLINE,
                        observed_at=observed_at,
                        detail=detail,
                    )
                )
                reasons.append(detail)
        except Exception as exc:
            detail = f"Database health could not be checked: {exc}"
            checks.append(
                HealthCheck(
                    name="database",
                    status=Availability.UNAVAILABLE,
                    observed_at=observed_at,
                    detail=detail,
                )
            )
            reasons.append(detail)

        bus, bus_check, bus_reason = self._collect_event_bus_check(observed_at)
        checks.extend(bus_check)
        if bus_reason:
            reasons.append(bus_reason)

        pipeline, pipeline_checks, pipeline_reasons = self._collect_pipeline(observed_at)
        checks.extend(pipeline_checks)
        reasons.extend(pipeline_reasons)

        persistence_check, persistence_reason = self._collect_persistence_check(observed_at)
        checks.append(persistence_check)
        if persistence_reason:
            reasons.append(persistence_reason)

        # ``bus`` is intentionally read here so both Redis and event-stream
        # checks describe the same real source snapshot.
        del bus
        return checks, reasons, pipeline

    def _collect_event_bus_check(
        self, observed_at: datetime
    ) -> Tuple[Optional[Any], List[HealthCheck], Optional[str]]:
        try:
            bus = self._event_bus_getter()
            connected = bool(getattr(bus, "is_connected", False))
            if connected:
                return bus, [
                    HealthCheck(name="redis", status=Availability.LIVE, observed_at=observed_at),
                    HealthCheck(name="event_stream", status=Availability.LIVE, observed_at=observed_at),
                ], None

            detail = "Redis is unavailable; the event bus is using its process-local fallback."
            return bus, [
                HealthCheck(
                    name="redis",
                    status=Availability.DEGRADED,
                    observed_at=observed_at,
                    detail=detail,
                ),
                HealthCheck(
                    name="event_stream",
                    status=Availability.DEGRADED,
                    observed_at=observed_at,
                    detail="Event delivery is process-local while Redis is unavailable.",
                ),
            ], detail
        except Exception as exc:
            detail = f"Redis/event-stream health could not be checked: {exc}"
            return None, [
                HealthCheck(
                    name="redis",
                    status=Availability.UNAVAILABLE,
                    observed_at=observed_at,
                    detail=detail,
                ),
                HealthCheck(
                    name="event_stream",
                    status=Availability.UNAVAILABLE,
                    observed_at=observed_at,
                    detail=detail,
                ),
            ], detail

    def _collect_pipeline(
        self, observed_at: datetime
    ) -> Tuple[PipelineContext, List[HealthCheck], List[str]]:
        checks: List[HealthCheck] = []
        reasons: List[str] = []
        try:
            pipeline = self._pipeline_getter()
        except Exception as exc:
            detail = f"Pipeline health could not be checked: {exc}"
            checks.extend(
                [
                    HealthCheck(
                        name="pipeline",
                        status=Availability.UNAVAILABLE,
                        observed_at=observed_at,
                        detail=detail,
                    ),
                    HealthCheck(
                        name="model",
                        status=Availability.UNAVAILABLE,
                        observed_at=observed_at,
                        detail="Detection model status is unavailable because the pipeline could not be queried.",
                    ),
                ]
            )
            return (
                PipelineContext(
                    running=None,
                    stages=[],
                    freshness=self._freshness(observed_at, Availability.UNAVAILABLE, detail),
                ),
                checks,
                [detail],
            )

        if pipeline is None:
            detail = "Pipeline has not been initialized."
            checks.extend(
                [
                    HealthCheck(
                        name="pipeline",
                        status=Availability.UNAVAILABLE,
                        observed_at=observed_at,
                        detail=detail,
                    ),
                    HealthCheck(
                        name="model",
                        status=Availability.UNAVAILABLE,
                        observed_at=observed_at,
                        detail="Detection model is unavailable because no pipeline is initialized.",
                    ),
                ]
            )
            return (
                PipelineContext(
                    running=None,
                    stages=[],
                    freshness=self._freshness(observed_at, Availability.UNAVAILABLE, detail),
                ),
                checks,
                [detail],
            )

        running = bool(getattr(pipeline, "_running", False))
        pipeline_status = Availability.LIVE if running else Availability.OFFLINE
        pipeline_detail = None if running else "Pipeline is initialized but not running."
        checks.append(
            HealthCheck(
                name="pipeline",
                status=pipeline_status,
                observed_at=observed_at,
                detail=pipeline_detail,
            )
        )
        if pipeline_detail:
            reasons.append(pipeline_detail)

        stages: List[PipelineStageContext] = []
        raw_stages = list(getattr(pipeline, "_stages", []) or [])
        for stage in raw_stages:
            stage_name = _string(getattr(stage, "name", None)) or "unnamed"
            stage_running = bool(getattr(stage, "_running", False))
            errors = int(getattr(stage, "_errors", 0) or 0)
            if not stage_running:
                stage_status = Availability.OFFLINE
                detail = "Stage is not running."
            elif errors:
                stage_status = Availability.DEGRADED
                detail = f"Stage has reported {errors} processing error(s)."
            else:
                stage_status = Availability.LIVE
                detail = None
            stages.append(
                PipelineStageContext(
                    name=stage_name,
                    status=stage_status,
                    observed_at=observed_at,
                    detail=detail,
                )
            )
            if stage_status in {Availability.DEGRADED, Availability.OFFLINE} and detail:
                reasons.append(f"Pipeline {stage_name}: {detail}")

        detection_stage = next(
            (stage for stage in raw_stages if getattr(stage, "name", None) == "detection"),
            None,
        )
        active_ingestion_model = self._active_ingestion_model_status()
        if active_ingestion_model is not None:
            # Camera frames take the production path documented at the top of
            # this module: MultiCameraPipelineManager -> FrameIngestionService
            # -> APIState.  The optional Redis worker pipeline can be alive
            # while its private detector remains unused, so it must not make a
            # loaded, actively ingesting detector look unavailable.
            model_status, model_detail = active_ingestion_model
        elif detection_stage is None:
            model_status = Availability.UNAVAILABLE
            model_detail = "Detection stage is not present in the pipeline."
        elif not running or not bool(getattr(detection_stage, "_running", False)):
            model_status = Availability.OFFLINE
            model_detail = "Detection stage is not running."
        elif getattr(detection_stage, "_detector", None) is None:
            model_status = Availability.UNAVAILABLE
            load_error = _string(getattr(detection_stage, "_model_load_error", None))
            model_detail = (
                f"Detection model preload failed: {load_error}"
                if load_error
                else "Detection model has not loaded yet."
            )
        else:
            model_status = Availability.LIVE
            model_detail = None
        checks.append(
            HealthCheck(
                name="model",
                status=model_status,
                observed_at=observed_at,
                detail=model_detail,
            )
        )
        if model_detail:
            reasons.append(model_detail)

        return (
            PipelineContext(
                running=running,
                stages=stages,
                freshness=self._freshness(observed_at, pipeline_status, pipeline_detail),
            ),
            checks,
            reasons,
        )

    def _active_ingestion_model_status(
        self,
    ) -> Optional[Tuple[Availability, Optional[str]]]:
        """Return model health only when the active camera ingestion owns one.

        This intentionally returns ``None`` when no detector has been created
        by the camera runtime.  In that case the separate pipeline's own model
        state remains the only available source of truth.
        """
        try:
            manager = self._camera_manager_getter()
            ingestion = getattr(manager, "ingestion", None)
        except Exception:
            return None

        if ingestion is not None and getattr(ingestion, "_detector", None) is not None:
            return Availability.LIVE, None
        return None

    def _collect_persistence_check(
        self, observed_at: datetime
    ) -> Tuple[HealthCheck, Optional[str]]:
        try:
            telemetry = self._persistence_status_getter()
            snapshot = telemetry.snapshot() if hasattr(telemetry, "snapshot") else dict(telemetry)
            attempted = int(snapshot.get("attempted", 0) or 0)
            last_success = _as_datetime(snapshot.get("last_success_at"))
            last_failure = _as_datetime(snapshot.get("last_failure_at"))
            failure_reason = _string(snapshot.get("last_failure_reason"))
            source = _string(snapshot.get("last_source"))
            if attempted == 0:
                ready, readiness_reason = self._persistence_readiness_check()
                if ready:
                    detail = "Database-backed event persistence is ready; no risk-alert event has been written since this process started."
                    return (
                        HealthCheck(
                            name="persistence",
                            status=Availability.LIVE,
                            observed_at=observed_at,
                            detail=detail,
                        ),
                        None,
                    )
                detail = readiness_reason or "Database-backed event persistence readiness could not be verified."
                return (
                    HealthCheck(
                        name="persistence",
                        status=Availability.UNAVAILABLE,
                        observed_at=observed_at,
                        detail=detail,
                    ),
                    detail,
                )
            if last_failure and (last_success is None or last_failure >= last_success):
                detail = "Latest durable event write failed"
                if source:
                    detail += f" in {source}"
                if failure_reason:
                    detail += f": {failure_reason}"
                return (
                    HealthCheck(
                        name="persistence",
                        status=Availability.DEGRADED,
                        observed_at=last_failure,
                        detail=detail,
                    ),
                    detail,
                )
            return (
                HealthCheck(
                    name="persistence",
                    status=Availability.LIVE,
                    observed_at=last_success or observed_at,
                    detail=(f"Latest durable event write succeeded in {source}." if source else None),
                ),
                None,
            )
        except Exception as exc:
            detail = f"Persistence telemetry is unavailable: {exc}"
            return (
                HealthCheck(
                    name="persistence",
                    status=Availability.UNAVAILABLE,
                    observed_at=observed_at,
                    detail=detail,
                ),
                detail,
            )

    def _collect_cameras(
        self, observed_at: datetime, evidence_validator: _EvidenceValidator
    ) -> Tuple[CamerasContext, List[str]]:
        try:
            manager = self._camera_manager_getter()
            raw_cameras = manager.list_cameras()
            if not isinstance(raw_cameras, list):
                raise TypeError("Camera runtime manager returned a non-list camera payload")
            evidence_validator.register_cameras(raw_cameras)
        except Exception as exc:
            detail = f"Camera runtime state is unavailable: {exc}"
            return (
                CamerasContext(
                    total=None,
                    total_configured=None,
                    online=None,
                    offline=None,
                    stale=None,
                    unavailable=None,
                    items=[],
                    freshness=self._freshness(observed_at, Availability.UNAVAILABLE, detail),
                ),
                [detail],
            )

        items: List[CameraItem] = []
        online = offline = stale = unavailable = 0
        for raw_camera in raw_cameras:
            if not isinstance(raw_camera, dict):
                continue
            camera_id = _string(raw_camera.get("camera_id"))
            if not camera_id:
                # No stable runtime identifier means this source cannot be
                # safely presented as an actionable camera item.
                continue
            runtime = raw_camera.get("runtime") or {}
            if not isinstance(runtime, dict):
                runtime = {}
            raw_status_value = _string(runtime.get("status"))
            raw_status = raw_status_value.lower() if raw_status_value else ""
            last_frame_at = _as_datetime(runtime.get("last_frame_time"))
            camera_status, reason = self._camera_availability(
                raw_status, last_frame_at, observed_at
            )
            if camera_status == Availability.LIVE:
                online += 1
            elif camera_status == Availability.STALE:
                stale += 1
            elif camera_status == Availability.OFFLINE:
                offline += 1
            else:
                unavailable += 1
            items.append(
                CameraItem(
                    camera_id=camera_id,
                    name=_string(raw_camera.get("name")),
                    runtime=camera_status,
                    last_frame_at=last_frame_at,
                    freshness=self._freshness(
                        observed_at,
                        camera_status,
                        reason,
                        expires=(camera_status == Availability.LIVE),
                    ),
                )
            )

        total = len(items)
        summary_status = Availability.LIVE
        summary_reason = None
        if stale:
            summary_status = Availability.STALE
            summary_reason = f"{stale} camera runtime state(s) are stale."
        if offline:
            summary_status = Availability.DEGRADED
            summary_reason = f"{offline} camera runtime state(s) are offline or reconnecting."
        if unavailable:
            summary_status = Availability.DEGRADED
            summary_reason = f"{unavailable} camera runtime state(s) are unavailable or unrecognized."
        reasons = [summary_reason] if summary_reason else []
        return (
            CamerasContext(
                total=total,
                total_configured=total,
                online=online,
                offline=offline,
                stale=stale,
                unavailable=unavailable,
                items=items,
                freshness=self._freshness(observed_at, summary_status, summary_reason),
            ),
            reasons,
        )

    def _camera_availability(
        self,
        raw_status: str,
        last_frame_at: Optional[datetime],
        observed_at: datetime,
    ) -> Tuple[Availability, Optional[str]]:
        if not raw_status:
            return Availability.UNAVAILABLE, "Camera runtime manager did not provide a status."
        if raw_status == "online":
            if last_frame_at is None:
                return Availability.STALE, "Camera reports online but has no frame timestamp."
            age = (observed_at - last_frame_at).total_seconds()
            if age > CAMERA_STALE_AFTER_SECONDS:
                return (
                    Availability.STALE,
                    f"No frame received for {int(age)} seconds (stale after {CAMERA_STALE_AFTER_SECONDS}s).",
                )
            return Availability.LIVE, None
        if raw_status in {"connecting", "reconnecting"}:
            return Availability.OFFLINE, f"Camera is {raw_status}."
        if raw_status in {"offline", "error", "stopped"}:
            return Availability.OFFLINE, f"Camera runtime status is {raw_status}."
        return Availability.UNAVAILABLE, f"Camera runtime status {raw_status!r} is not recognized."

    def _collect_runtime_data(
        self, observed_at: datetime, evidence_validator: _EvidenceValidator
    ) -> Tuple[List[EventItem], AlertsContext, List[TrackItem], DetectionSummary, List[str]]:
        try:
            state = self._state_getter()
            raw_events = state.get_events(limit=MAX_CONTEXT_EVENTS)
            if not isinstance(raw_events, list):
                raise TypeError("Runtime event state returned a non-list payload")
            evidence_validator.register_events(raw_events)
            events = self._event_items(raw_events, observed_at, evidence_validator)
            alert_items = self._risk_alert_items(raw_events, observed_at, evidence_validator)
            alerts = AlertsContext(
                active_count=len(alert_items),
                items=alert_items,
                freshness=self._alert_collection_freshness(alert_items, observed_at),
            )
        except Exception as exc:
            detail = f"Live event state is unavailable: {exc}"
            event_freshness = self._freshness(observed_at, Availability.UNAVAILABLE, detail)
            events = []
            alerts = AlertsContext(active_count=None, items=[], freshness=event_freshness)
            runtime_reasons = [detail]
        else:
            runtime_reasons = []

        try:
            state = self._state_getter()
            raw_tracks = state.get_tracks()
            if not isinstance(raw_tracks, list):
                raise TypeError("Runtime track state returned a non-list payload")
            evidence_validator.register_tracks(raw_tracks)
            tracks = self._track_items(raw_tracks, observed_at, evidence_validator)
        except Exception as exc:
            detail = f"Live track state is unavailable: {exc}"
            tracks = []
            runtime_reasons.append(detail)

        try:
            state = self._state_getter()
            statistics = state.get_statistics()
            if not isinstance(statistics, dict) or not statistics:
                raise LookupError("No runtime detection statistics have been reported")
            count = statistics.get("active_detections_count")
            if not isinstance(count, int):
                raise TypeError("Runtime detection count is absent or invalid")
            stats_timestamp = _as_datetime(statistics.get("timestamp"))
            if stats_timestamp is None:
                status = Availability.UNAVAILABLE
                detail = "Runtime detection statistics have no source timestamp."
            elif (observed_at - stats_timestamp).total_seconds() > STATISTICS_STALE_AFTER_SECONDS:
                status = Availability.STALE
                detail = f"Runtime detection statistics are older than {STATISTICS_STALE_AFTER_SECONDS}s."
            else:
                status = Availability.LIVE
                detail = None
            detections = DetectionSummary(
                recent_count=count,
                freshness=self._freshness(stats_timestamp or observed_at, status, detail, expires=status == Availability.LIVE),
            )
            if detail:
                runtime_reasons.append(detail)
        except Exception as exc:
            detail = f"Runtime detection statistics are unavailable: {exc}"
            detections = DetectionSummary(
                recent_count=None,
                freshness=self._freshness(observed_at, Availability.UNAVAILABLE, detail),
            )
            runtime_reasons.append(detail)

        return events, alerts, tracks, detections, runtime_reasons

    def _event_items(
        self,
        raw_events: Sequence[Dict[str, Any]],
        generated_at: datetime,
        evidence_validator: _EvidenceValidator,
    ) -> List[EventItem]:
        items: List[EventItem] = []
        for raw in reversed(raw_events[-MAX_CONTEXT_EVENTS:]):
            if not isinstance(raw, dict):
                continue
            event_id = _string(raw.get("event_id")) or _string(raw.get("id"))
            if event_id is None:
                continue
            timestamp = _as_datetime(raw.get("timestamp"))
            camera_id = _string(raw.get("camera_id"))
            event_type = _string(raw.get("event_type")) or _string(raw.get("type"))
            summary = (
                _string(raw.get("description"))
                or _string(raw.get("explanation"))
                or _string(raw.get("message"))
                or event_type
            )
            if summary is None:
                # There is no source-provided description or event type to
                # display, so omit rather than inventing a placeholder row.
                continue
            evidence = evidence_validator.evidence(
                kind="event",
                item_id=event_id,
                camera_id=camera_id,
                occurred_at=timestamp,
                label=event_type or "runtime event",
            )
            items.append(
                EventItem(
                    event_id=event_id,
                    risk_score=_number(raw.get("risk_score")),
                    risk_level=_string(raw.get("risk_level")),
                    summary=summary,
                    evidence=[evidence] if evidence else [],
                    freshness=self._activity_freshness(timestamp, generated_at, "Event"),
                )
            )
        return items

    def _risk_alert_items(
        self,
        raw_events: Sequence[Dict[str, Any]],
        generated_at: datetime,
        evidence_validator: _EvidenceValidator,
    ) -> List[RiskAlertItem]:
        alerts: List[RiskAlertItem] = []
        for raw in reversed(raw_events[-MAX_CONTEXT_EVENTS:]):
            if not isinstance(raw, dict) or not self._is_risk_alert(raw):
                continue
            alert_id = _string(raw.get("event_id")) or _string(raw.get("id"))
            if alert_id is None:
                continue
            timestamp = _as_datetime(raw.get("timestamp"))
            camera_id = _string(raw.get("camera_id"))
            acknowledged = raw.get("acknowledged")
            evidence = evidence_validator.evidence(
                kind="alert",
                item_id=alert_id,
                camera_id=camera_id,
                occurred_at=timestamp,
                label="runtime risk alert",
                is_risk_alert=True,
            )
            alerts.append(
                RiskAlertItem(
                    alert_id=alert_id,
                    level=_string(raw.get("risk_level")) or _string(raw.get("severity")),
                    acknowledged=acknowledged if isinstance(acknowledged, bool) else None,
                    evidence=[evidence] if evidence else [],
                    freshness=self._activity_freshness(timestamp, generated_at, "Risk alert"),
                )
            )
        return alerts

    def _alert_collection_freshness(
        self, alerts: Sequence[RiskAlertItem], generated_at: datetime
    ) -> Freshness:
        """Keep the alert summary as fresh as its newest source record."""
        if not alerts:
            # The empty result is a real, freshly queried buffer state.
            return self._freshness(generated_at, Availability.LIVE, expires=True)
        return max(alerts, key=lambda item: item.freshness.observed_at).freshness

    def _activity_freshness(
        self,
        timestamp: Optional[datetime],
        generated_at: datetime,
        activity_name: str,
    ) -> Freshness:
        """Use the activity's source timestamp, never the snapshot time."""
        if timestamp is None:
            return self._freshness(
                generated_at,
                Availability.UNAVAILABLE,
                f"{activity_name} has no source timestamp.",
            )

        age_seconds = (generated_at - timestamp).total_seconds()
        expires_at = timestamp + timedelta(seconds=EVENT_STALE_AFTER_SECONDS)
        if age_seconds > EVENT_STALE_AFTER_SECONDS:
            return Freshness(
                observed_at=timestamp,
                expires_at=expires_at,
                status=Availability.STALE,
                reason=(
                    f"{activity_name} source timestamp is older than "
                    f"{EVENT_STALE_AFTER_SECONDS}s."
                ),
            )
        return Freshness(
            observed_at=timestamp,
            expires_at=expires_at,
            status=Availability.LIVE,
        )

    @staticmethod
    def _is_risk_alert(event: Dict[str, Any]) -> bool:
        event_type = (_string(event.get("type")) or _string(event.get("event_type")) or "").lower()
        if event_type == "risk_alert":
            return True
        # Older runtime records predate the explicit marker but only this
        # confirmed-alert producer sets ``confirmed_frames``.
        return (
            event.get("confirmed_frames") is not None
            and (_string(event.get("risk_level")) or "").upper() in {"HIGH", "CRITICAL"}
        )

    def _track_items(
        self,
        raw_tracks: Sequence[Dict[str, Any]],
        observed_at: datetime,
        evidence_validator: _EvidenceValidator,
    ) -> List[TrackItem]:
        items: List[TrackItem] = []
        for raw in raw_tracks[:MAX_CONTEXT_TRACKS]:
            if not isinstance(raw, dict):
                continue
            track_id = _string(raw.get("track_id"))
            class_name = _string(raw.get("class_name"))
            if not track_id or not class_name:
                continue
            last_updated = _as_datetime(raw.get("last_updated")) or _as_datetime(raw.get("last_seen"))
            if last_updated is None:
                status = Availability.UNAVAILABLE
                reason = "Track has no source timestamp."
                observed = observed_at
            elif (observed_at - last_updated).total_seconds() > TRACK_STALE_AFTER_SECONDS:
                status = Availability.STALE
                reason = f"Track has not been updated for more than {TRACK_STALE_AFTER_SECONDS}s."
                observed = last_updated
            else:
                status = Availability.LIVE
                reason = None
                observed = last_updated
            camera_id = _string(raw.get("camera_id"))
            evidence = evidence_validator.evidence(
                kind="track",
                item_id=track_id,
                camera_id=camera_id,
                occurred_at=last_updated,
                label=class_name,
            )
            items.append(
                TrackItem(
                    track_id=track_id,
                    camera_id=camera_id,
                    class_name=class_name,
                    risk_score=_number(raw.get("risk_score")),
                    verification_status=_string(raw.get("verification_status")),
                    evidence=[evidence] if evidence else [],
                    freshness=self._freshness(observed, status, reason, expires=status == Availability.LIVE),
                )
            )
        return items

    def _collect_semantic(
        self, observed_at: datetime
    ) -> Tuple[SemanticContext, List[str]]:
        try:
            state = self._state_getter()
            engine = getattr(state, "semantic_query_engine", None)
            if engine is None:
                detail = "Live-evidence semantic search is not initialized."
                return (
                    SemanticContext(
                        capability=Availability.UNAVAILABLE,
                        reason=detail,
                        freshness=self._freshness(observed_at, Availability.UNAVAILABLE, detail),
                    ),
                    [detail],
                )
            active_query = _string(getattr(state, "active_semantic_query", None))
            return (
                SemanticContext(
                    capability=Availability.LIVE,
                    mode="live_evidence",
                    active_query=active_query,
                    evidence=[],
                    freshness=self._freshness(observed_at, Availability.LIVE, expires=True),
                ),
                [],
            )
        except Exception as exc:
            detail = f"Semantic capability state is unavailable: {exc}"
            return (
                SemanticContext(
                    capability=Availability.UNAVAILABLE,
                    reason=detail,
                    freshness=self._freshness(observed_at, Availability.UNAVAILABLE, detail),
                ),
                [detail],
            )

    def _collect_ai(
        self, evidence_validator: _EvidenceValidator
    ) -> Tuple[AIContext, List[str]]:
        reasons: List[str] = []
        settings = None
        try:
            settings = self._settings_getter()
            configured_key = getattr(getattr(settings, "gemini", None), "api_key", "")
            provider_configured = bool(configured_key or os.getenv("GEMINI_API_KEY", ""))
        except Exception as exc:
            provider_configured = None
            reasons.append(f"AI provider configuration could not be checked: {exc}")

        if provider_configured is True:
            chat = Availability.LIVE
            ai_reason = evidence_validator.reason
        elif provider_configured is False:
            chat = Availability.DEGRADED
            ai_reason = "No AI provider is configured; chat uses its limited fallback response path."
        else:
            chat = Availability.UNAVAILABLE
            ai_reason = "AI provider configuration is unavailable."
        if ai_reason:
            reasons.append(ai_reason)
        try:
            from aegis.intelligence.live_service import get_live_capabilities

            live_capability = get_live_capabilities(settings)
        except Exception as exc:
            live_capability = None
            reasons.append(f"Gemini Live capability could not be checked: {type(exc).__name__}.")

        voice_status = live_capability.availability if live_capability is not None else Availability.UNAVAILABLE
        voice_reason = live_capability.reason if live_capability is not None else "Gemini Live capability is unavailable."
        if voice_status != Availability.LIVE and voice_reason:
            reasons.append(voice_reason)
        return (
            AIContext(
                chat=chat,
                provider_configured=provider_configured,
                evidence_grounding=evidence_validator.status,
                reason=ai_reason,
                voice=VoiceCapability(
                    push_to_talk=voice_status,
                    hands_free=voice_status,
                    reason=voice_reason,
                ),
            ),
            reasons,
        )

    def _build_suggestions(
        self,
        cameras: CamerasContext,
        alerts: AlertsContext,
        evidence_validator: _EvidenceValidator,
    ) -> List[IntelligenceSuggestion]:
        """Return only condition-backed links to existing, same-origin pages."""
        suggestions: List[IntelligenceSuggestion] = []
        for camera in cameras.items:
            if camera.runtime not in {Availability.OFFLINE, Availability.STALE}:
                continue
            reason = camera.freshness.reason
            if reason is None:
                # A review suggestion must cite the concrete runtime reason.
                continue
            evidence = evidence_validator.evidence(
                kind="health",
                item_id=f"camera:{camera.camera_id}",
                camera_id=camera.camera_id,
                occurred_at=camera.last_frame_at,
                label="camera runtime status",
            )
            if evidence is None:
                continue
            suggestions.append(
                IntelligenceSuggestion(
                    suggestion_id=f"camera-runtime-{camera.camera_id}",
                    label=f"Review camera {camera.name or camera.camera_id}",
                    reason=reason,
                    evidence=[evidence],
                    availability=Availability.LIVE,
                    href="/cameras",
                )
            )
        for alert in alerts.items:
            evidence = [reference for reference in alert.evidence if reference.server_validated]
            if alert.level is None or not evidence:
                continue
            suggestions.append(
                IntelligenceSuggestion(
                    suggestion_id=f"risk-alert-{alert.alert_id}",
                    label=f"Review active risk alert {alert.alert_id}",
                    reason=f"Runtime risk alert is reported at level {alert.level}.",
                    evidence=evidence,
                    availability=Availability.LIVE,
                    href="/events",
                )
            )
        return suggestions[:6]

    def _freshness(
        self,
        observed_at: datetime,
        status: Availability,
        reason: Optional[str] = None,
        *,
        expires: bool = False,
    ) -> Freshness:
        return Freshness(
            observed_at=observed_at,
            expires_at=(observed_at + timedelta(seconds=REFRESH_AFTER_SECONDS * 2)) if expires else None,
            status=status,
            reason=reason,
        )

    @staticmethod
    def _deduplicate(values: Iterable[str]) -> List[str]:
        result: List[str] = []
        for value in values:
            if value and value not in result:
                result.append(value)
        return result

    @staticmethod
    def _overall_status(
        checks: Sequence[HealthCheck],
        cameras: CamerasContext,
        alerts: AlertsContext,
        tracks: Sequence[TrackItem],
        detections: DetectionSummary,
        semantic: SemanticContext,
        ai: AIContext,
    ) -> Availability:
        del tracks
        statuses = [check.status for check in checks]
        statuses.extend(
            [
                cameras.freshness.status,
                alerts.freshness.status,
                detections.freshness.status,
                semantic.capability,
                ai.chat,
                ai.evidence_grounding,
            ]
        )
        if any(status in {Availability.OFFLINE, Availability.DEGRADED, Availability.UNAVAILABLE} for status in statuses):
            return Availability.DEGRADED
        if any(status == Availability.STALE for status in statuses):
            return Availability.STALE
        return Availability.LIVE


def get_intelligence_context_service() -> IntelligenceContextService:
    """Dependency factory used by the authenticated API route."""

    return IntelligenceContextService()
