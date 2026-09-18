"""
AegisAI - Alerting Pipeline Stage

Final stage in the pipeline. Consumes risk-scored events and generates
alerts when thresholds are exceeded. Persists events to database and
publishes to the events stream for WebSocket delivery.
"""

from __future__ import annotations

import logging
import re
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional

import cv2

from aegis.pipeline.stages import PipelineStage, Streams

logger = logging.getLogger(__name__)


class AlertingStage(PipelineStage):
    """
    Alert generation pipeline stage.

    Reads risk-scored results and:
    1. Generates alerts when risk thresholds are exceeded
    2. Persists events to the database
    3. Publishes high-priority events to the events stream
    4. Maintains an in-memory event buffer for WebSocket delivery

    This stage does NOT own the AlertManager — it delegates to it.
    """

    def __init__(
        self,
        event_buffer_size: int = 1000,
        high_risk_threshold: float = 0.7,
        critical_risk_threshold: float = 0.85,
        **kwargs,
    ):
        super().__init__(
            name="alerting",
            input_stream=Streams.RISKS,
            output_stream=Streams.EVENTS,
            **kwargs,
        )
        self._alert_manager = None
        self._events: Deque[Dict[str, Any]] = deque(maxlen=event_buffer_size)
        self._detections: Deque[Dict[str, Any]] = deque(maxlen=event_buffer_size)
        self._high_risk_threshold = high_risk_threshold
        self._critical_risk_threshold = critical_risk_threshold
        self._total_alerts = 0
        self._total_events = 0
        self._threat_cooldowns: Dict[str, float] = {}
        self._threat_cooldown_seconds = 30.0

    def _get_alert_manager(self):
        """Lazy-load the alert manager."""
        if self._alert_manager is None:
            try:
                from aegis.alerts import AlertManager
                self._alert_manager = AlertManager()
                logger.info("Alert manager initialized")
            except ImportError:
                logger.debug("Alert manager not available")
        return self._alert_manager

    def process(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Generate alerts from risk-scored results.

        Input: risk-scored events from RiskScoringStage
        Output: alert events for WebSocket delivery
        """
        output_events = []

        for msg in messages:
            camera_id = msg.get("camera_id", "unknown")
            frame_id = msg.get("frame_id", 0)
            timestamp = msg.get("timestamp", time.time())
            risks = msg.get("risks", [])
            max_risk = msg.get("max_risk_score", 0.0)
            concerning_count = msg.get("concerning_count", 0)

            # Store detection data for API access
            detection_record = {
                "camera_id": camera_id,
                "frame_id": frame_id,
                "timestamp": timestamp,
                "track_count": msg.get("track_count", 0),
                "detection_count": msg.get("detection_count", 0),
                "max_risk_score": max_risk,
                "concerning_count": concerning_count,
                "crowd_density": msg.get("crowd_density", 0.0),
            }
            self._detections.append(detection_record)
            self._total_events += 1

            # Generate alerts for concerning tracks
            for risk in risks:
                if not risk.get("is_concerning"):
                    continue

                risk_level = risk.get("level", "LOW")
                risk_score = risk.get("score", 0.0)
                threat_key = self._threat_cooldown_key(camera_id, risk)
                if threat_key and not self._accept_threat_context(threat_key):
                    continue

                event_id = self._event_id_for(
                    camera_id=camera_id,
                    frame_id=frame_id,
                    track_id=risk.get("track_id"),
                    timestamp=timestamp,
                    risk_level=risk_level,
                )
                related_track_ids = []
                for related_track_id in (
                    risk.get("weapon_track_id"),
                    risk.get("nearby_person_track_id"),
                ):
                    if related_track_id is None:
                        continue
                    related_key = f"{camera_id}:{related_track_id}"
                    if related_key not in related_track_ids:
                        related_track_ids.append(related_key)

                event = {
                    "event_id": event_id,
                    "evidence_id": None,
                    "evidence_status": "not_required",
                    "incident_id": None,
                    "type": "risk_alert",
                    "event_type": "risk_alert",
                    "threat_event_type": risk.get("event_type"),
                    "camera_id": camera_id,
                    "frame_id": frame_id,
                    "track_id": risk.get("track_id"),
                    "person_track_id": risk.get("person_track_id"),
                    "weapon_track_id": risk.get("weapon_track_id"),
                    "nearby_person_track_id": risk.get("nearby_person_track_id"),
                    "weapon_class": risk.get("weapon_class"),
                    "weapon_confidence": risk.get("weapon_confidence"),
                    "object_class": risk.get("object_class"),
                    "class_name": risk.get("object_class"),
                    "risk_level": risk_level,
                    "risk_score": risk_score,
                    "explanation": risk.get("explanation", ""),
                    "reason": risk.get("explanation", ""),
                    "reason_codes": risk.get("reason_codes", []),
                    "factors": risk.get("reason_codes", []),
                    "bbox": risk.get("bbox"),
                    "evidence_objects": risk.get("evidence_objects", []),
                    "related_track_ids": related_track_ids,
                    "threat_context": risk.get("threat_context"),
                    "timestamp": timestamp,
                }

                # HIGH/CRITICAL threat evidence gets one keyframe. Encoding or
                # persistence failure remains non-fatal to stream processing.
                should_persist = risk_level in {"HIGH", "CRITICAL"} or risk_score >= self._high_risk_threshold
                if should_persist:
                    if risk.get("threat_context"):
                        snapshot_path, snapshot_status = self._save_snapshot(
                            camera_id=camera_id,
                            event_id=event_id,
                            timestamp=timestamp,
                            frame=msg.get("_frame"),
                        )
                        event["snapshot_path"] = snapshot_path
                        event["snapshot_status"] = snapshot_status
                    if self._persist_event(event):
                        event["evidence_id"] = event.get("evidence_id") or event_id
                        event["evidence_status"] = "persisted"
                    else:
                        event["evidence_status"] = "failed"

                self._events.append(event)
                self._total_alerts += 1

                # Trigger alert manager for critical events
                if risk_level == "CRITICAL" or risk_score >= self._critical_risk_threshold:
                    self._trigger_alert(event)

                output_events.append(event)

            # Publish a frame summary event even if no alerts
            if concerning_count == 0 and msg.get("track_count", 0) > 0:
                summary = {
                    "type": "frame_summary",
                    "camera_id": camera_id,
                    "frame_id": frame_id,
                    "track_count": msg.get("track_count", 0),
                    "max_risk_score": max_risk,
                    "timestamp": timestamp,
                }
                output_events.append(summary)

        return output_events

    def _persist_event(self, event: Dict[str, Any]) -> bool:
        """Persist a high-risk event through the active ``aegis.database`` stack.

        ``get_db_session`` is a context manager, so a repository must never be
        cached with a closed or un-entered session.  This is deliberately the
        same repository stack used by the camera ingestion path; ``aegis.db``
        is not consulted here.
        """
        try:
            from aegis.database.connection import get_db_session
            from aegis.database.persistence import get_persistence_status
            from aegis.database.repositories import EventRepository

            timestamp = self._parse_event_timestamp(event.get("timestamp"))
            message = event.get("explanation") or event.get("message") or event.get("description")
            if not isinstance(message, str) or not message.strip():
                raise ValueError("Cannot persist a risk alert without an explanation")

            raw_track_id = str(event.get("track_id", "")).split(":")[-1]
            track_id = int(raw_track_id) if raw_track_id.isdigit() else None
            with get_db_session() as session:
                persisted_event, _ = EventRepository(session).create_or_get_evidence(
                    event_id=str(event.get("event_id") or self._event_id_for(
                        camera_id=event.get("camera_id", "unknown"),
                        frame_id=event.get("frame_id", 0),
                        track_id=event.get("track_id"),
                        timestamp=event.get("timestamp"),
                        risk_level=event.get("risk_level", "LOW"),
                    )),
                    event_type="risk_alert",
                    message=message,
                    timestamp=timestamp,
                    track_id=track_id,
                    track_key=event.get("track_id"),
                    alert_id=event.get("alert_id"),
                    camera_id=event.get("camera_id"),
                    camera_name=event.get("camera_name"),
                    object_class=event.get("object_class") or event.get("class_name"),
                    risk_level=event.get("risk_level"),
                    risk_score=self._optional_float(event.get("risk_score")),
                    factors=event.get("factors"),
                    zone=event.get("zone") or event.get("camera_id"),
                    zone_id=event.get("zone_id"),
                    zone_name=event.get("zone_name"),
                    bounding_box=event.get("bbox"),
                    reason=event.get("reason") or message,
                    snapshot_path=event.get("snapshot_path"),
                    snapshot_status=event.get("snapshot_status") or "unavailable",
                    clip_path=event.get("clip_path"),
                    metadata=dict(event),
                )
                # Keep the legacy stream path on the same incident store as
                # camera ingestion. Correlation failure is isolated so a
                # database issue never blocks alert publication.
                try:
                    from aegis.intelligence.incident_correlation import IncidentCorrelationService

                    with session.begin_nested():
                        incident = IncidentCorrelationService(session).correlate_event(persisted_event)
                    if incident is not None:
                        event["incident_id"] = incident.incident_id
                except Exception as correlation_error:
                    logger.warning(
                        "Incident correlation failed for event_id=%s: %s",
                        event.get("event_id"),
                        correlation_error,
                    )
                persisted_event_id = getattr(persisted_event, "event_id", None)
                if persisted_event_id:
                    event["evidence_id"] = persisted_event_id
            get_persistence_status().record_success("pipeline_alerting")
            return True
        except Exception as exc:
            # Persistence is non-blocking for frame processing, but it is not
            # silent: the typed Intelligence context exposes this degradation.
            try:
                from aegis.database.persistence import get_persistence_status

                get_persistence_status().record_failure("pipeline_alerting", exc)
            except Exception:
                pass
            logger.warning("Risk-alert persistence failed: %s", exc)
            return False

    def _threat_cooldown_key(self, camera_id: str, risk: Dict[str, Any]) -> Optional[str]:
        event_type = str(risk.get("event_type") or "")
        if not event_type:
            return None
        actor_id = str(risk.get("person_track_id") or risk.get("track_id") or "untracked")
        nearby_id = str(risk.get("nearby_person_track_id") or "none")
        if event_type == "possible_assault" and nearby_id != "none":
            actor_id, nearby_id = sorted((actor_id, nearby_id))
        return ":".join((str(camera_id), event_type, actor_id, nearby_id))

    def _accept_threat_context(self, key: str) -> bool:
        now = time.monotonic()
        last_seen = self._threat_cooldowns.get(key)
        if last_seen is not None and now - last_seen < self._threat_cooldown_seconds:
            return False
        self._threat_cooldowns[key] = now
        return True

    def _save_snapshot(
        self,
        *,
        camera_id: str,
        event_id: str,
        timestamp: Any,
        frame: Any,
    ) -> tuple[Optional[str], str]:
        if frame is None:
            return None, "failed"
        try:
            observed_at = self._parse_event_timestamp(timestamp)
            snapshot_dir = Path("data/output/snapshots")
            snapshot_dir.mkdir(parents=True, exist_ok=True)
            safe_camera = re.sub(r"[^A-Za-z0-9_-]+", "-", str(camera_id)).strip("-_") or "camera"
            safe_event = re.sub(r"[^A-Za-z0-9_-]+", "-", str(event_id)).strip("-_") or "event"
            path = snapshot_dir / f"{safe_camera[:80]}_{safe_event[:128]}_{observed_at.strftime('%Y%m%dT%H%M%S%fZ')}.jpg"
            if cv2.imwrite(str(path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85]):
                return path.as_posix(), "saved"
        except Exception as exc:
            logger.warning("Pipeline snapshot failed event_id=%s: %s", event_id, exc)
        return None, "failed"

    @staticmethod
    def _event_id_for(
        *,
        camera_id: Any,
        frame_id: Any,
        track_id: Any,
        timestamp: Any,
        risk_level: Any,
    ) -> str:
        """Build a deterministic identity for a legacy stream message.

        The camera ingestion path receives an AlertManager event ID.  The
        Redis-stage path historically did not, so this identity prevents the
        same delivered message from becoming several durable records.
        """
        return "pipeline:{camera}:{frame}:{track}:{risk}:{timestamp}".format(
            camera=str(camera_id or "unknown"),
            frame=str(frame_id or 0),
            track=str(track_id or "untracked"),
            risk=str(risk_level or "LOW").upper(),
            timestamp=str(timestamp or "unknown"),
        )

    @staticmethod
    def _parse_event_timestamp(value: Any) -> datetime:
        """Parse an event timestamp without substituting a fabricated time."""
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc)
        if isinstance(value, str) and value.strip():
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        raise ValueError("Cannot persist a risk alert without a timestamp")

    @staticmethod
    def _optional_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        return float(value)

    def _trigger_alert(self, event: Dict[str, Any]) -> None:
        """Trigger an alert for a critical event."""
        manager = self._get_alert_manager()
        if manager is None:
            return

        try:
            cooldown_key = self._threat_cooldown_key(
                str(event.get("camera_id") or "unknown"),
                {
                    "event_type": event.get("threat_event_type"),
                    "person_track_id": event.get("person_track_id"),
                    "nearby_person_track_id": event.get("nearby_person_track_id"),
                    "track_id": event.get("track_id"),
                },
            ) or str(event.get("track_id") or "untracked")
            alert = manager.process_risk(
                track_id=str(event.get("track_id") or "untracked"),
                risk_level=str(event.get("risk_level") or "HIGH"),
                risk_score=float(event.get("risk_score") or 0.0),
                message=event.get("explanation", "Risk threshold exceeded"),
                zone=str(event.get("camera_id") or ""),
                factors=list(event.get("reason_codes") or []),
                cooldown_key=cooldown_key,
            )
            if alert is not None:
                event["alert_id"] = alert.event_id
                persist_alert = getattr(manager, "persist_alert", None)
                if not callable(persist_alert):
                    event["alert_persistence_status"] = "unavailable"
                elif not persist_alert(
                    alert,
                    event_id=str(event.get("event_id")),
                    cooldown_key=cooldown_key,
                ):
                    event["alert_persistence_status"] = "failed"
                else:
                    event["alert_persistence_status"] = "persisted"
        except Exception as exc:
            logger.debug("Alert trigger failed: %s", exc)

    def get_recent_events(self, camera_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent events, optionally filtered by camera."""
        events = list(self._events)
        if camera_id:
            events = [e for e in events if e.get("camera_id") == camera_id]
        return events[-limit:]

    def get_recent_detections(self, camera_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent detection summaries."""
        detections = list(self._detections)
        if camera_id:
            detections = [d for d in detections if d.get("camera_id") == camera_id]
        return detections[-limit:]

    def get_stats(self) -> Dict[str, Any]:
        """Return alerting stage metrics."""
        base = super().get_stats()
        try:
            from aegis.database.persistence import get_persistence_status

            persistence = get_persistence_status().snapshot()
        except Exception as exc:
            persistence = {"status_error": str(exc)}
        base.update({
            "total_alerts": self._total_alerts,
            "total_events": self._total_events,
            "event_buffer_size": len(self._events),
            "detection_buffer_size": len(self._detections),
            "persistence": persistence,
        })
        return base
