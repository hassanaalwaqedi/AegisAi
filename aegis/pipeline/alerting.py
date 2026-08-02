"""
AegisAI - Alerting Pipeline Stage

Final stage in the pipeline. Consumes risk-scored events and generates
alerts when thresholds are exceeded. Persists events to database and
publishes to the events stream for WebSocket delivery.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional

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

                event = {
                    "type": "risk_alert",
                    "camera_id": camera_id,
                    "frame_id": frame_id,
                    "track_id": risk.get("track_id"),
                    "risk_level": risk_level,
                    "risk_score": risk_score,
                    "explanation": risk.get("explanation", ""),
                    "timestamp": timestamp,
                }

                self._events.append(event)
                self._total_alerts += 1

                # Persist high-risk events
                if risk_score >= self._high_risk_threshold:
                    self._persist_event(event)

                # Trigger alert manager for critical events
                if risk_score >= self._critical_risk_threshold:
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

    def _persist_event(self, event: Dict[str, Any]) -> None:
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
                EventRepository(session).create(
                    event_type="risk_alert",
                    message=message,
                    timestamp=timestamp,
                    track_id=track_id,
                    risk_level=event.get("risk_level"),
                    risk_score=self._optional_float(event.get("risk_score")),
                    factors=event.get("factors"),
                    zone=event.get("camera_id"),
                    metadata=dict(event),
                )
            get_persistence_status().record_success("pipeline_alerting")
        except Exception as exc:
            # Persistence is non-blocking for frame processing, but it is not
            # silent: the typed Intelligence context exposes this degradation.
            try:
                from aegis.database.persistence import get_persistence_status

                get_persistence_status().record_failure("pipeline_alerting", exc)
            except Exception:
                pass
            logger.warning("Risk-alert persistence failed: %s", exc)

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
            manager.trigger(
                level="CRITICAL" if event.get("risk_score", 0) >= 0.9 else "HIGH",
                camera_id=event.get("camera_id"),
                message=event.get("explanation", "Risk threshold exceeded"),
                data=event,
            )
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
