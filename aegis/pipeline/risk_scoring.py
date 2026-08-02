"""
AegisAI - Risk Scoring Pipeline Stage

Consumes tracked objects and computes risk scores using the RiskEngine,
ProximityRiskEngine, and WeaponAssociationEngine. Publishes risk-scored
results to the events stream.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from aegis.pipeline.stages import PipelineStage, Streams

logger = logging.getLogger(__name__)


class RiskScoringStage(PipelineStage):
    """
    Risk assessment pipeline stage.

    Takes tracked objects with analysis data and computes per-track risk
    scores using spatial proximity, weapon association, crowd density,
    and behavioral signals.
    """

    def __init__(self, **kwargs):
        super().__init__(
            name="risk-scoring",
            input_stream=Streams.TRACKS,
            output_stream=Streams.RISKS,
            **kwargs,
        )
        self._risk_engines: Dict[str, Any] = {}
        self._proximity_engines: Dict[str, Any] = {}
        self._association_engines: Dict[str, Any] = {}

    def _get_risk_engine(self, camera_id: str, frame_shape=None, metadata=None):
        """Get or create a risk engine for a camera."""
        if camera_id not in self._risk_engines:
            try:
                from aegis.risk import RiskEngine
                self._risk_engines[camera_id] = RiskEngine()
                # Configure zones if metadata provides them
                if metadata and metadata.get("zones"):
                    try:
                        self._risk_engines[camera_id].zone_manager.load_zones(
                            metadata["zones"], frame_shape
                        )
                    except Exception:
                        pass
            except ImportError:
                logger.warning("Risk engine not available")
                return None
        return self._risk_engines[camera_id]

    def _get_proximity_engine(self, camera_id: str):
        if camera_id not in self._proximity_engines:
            try:
                from aegis.risk.proximity_risk import ProximityRiskEngine
                self._proximity_engines[camera_id] = ProximityRiskEngine()
            except ImportError:
                return None
        return self._proximity_engines[camera_id]

    def _get_association_engine(self, camera_id: str):
        if camera_id not in self._association_engines:
            try:
                from aegis.risk.weapon_association import WeaponAssociationEngine
                self._association_engines[camera_id] = WeaponAssociationEngine()
            except ImportError:
                return None
        return self._association_engines[camera_id]

    def process(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Compute risk scores for tracked objects.

        Input: tracking results with analysis data
        Output: risk-scored events ready for alerting
        """
        results = []

        for msg in messages:
            camera_id = msg.get("camera_id", "unknown")
            frame_id = msg.get("frame_id", 0)
            frame = msg.get("_frame")
            raw_tracks = msg.get("_tracks")
            raw_analyses = msg.get("_track_analyses_raw", {})

            if raw_tracks is None:
                continue

            try:
                risk_engine = self._get_risk_engine(camera_id)
                proximity_engine = self._get_proximity_engine(camera_id)
                association_engine = self._get_association_engine(camera_id)

                motion_states = raw_analyses.get("motion_states", {})
                behaviors = raw_analyses.get("behaviors", {})
                crowd_metrics = raw_analyses.get("crowd_metrics")
                history_manager = raw_analyses.get("history_manager")

                # Build track analyses for risk engine
                track_analyses = []
                if history_manager:
                    try:
                        from aegis.analysis.analysis_types import TrackAnalysis
                        for track in raw_tracks:
                            history = history_manager.get_history(track.track_id)
                            motion = motion_states.get(track.track_id)
                            behavior = behaviors.get(track.track_id)
                            if history and motion and behavior:
                                current = history.current_position
                                track_analyses.append(
                                    TrackAnalysis(
                                        track_id=track.track_id,
                                        class_id=track.class_id,
                                        class_name=track.class_name,
                                        motion=motion,
                                        behavior=behavior,
                                        history_length=history.history_length,
                                        time_tracked=history.duration,
                                        current_position=(
                                            (current.x, current.y) if current else (0.0, 0.0)
                                        ),
                                        current_bbox=track.bbox,
                                    )
                                )
                    except ImportError:
                        pass

                # Compute frame risks
                risk_summary = None
                if risk_engine and track_analyses:
                    timestamp = msg.get("timestamp", time.time())
                    risk_summary = risk_engine.compute_frame_risks(
                        track_analyses=track_analyses,
                        crowd_metrics=crowd_metrics,
                        frame_id=frame_id,
                        timestamp=timestamp,
                    )

                # Compute proximity and associations
                proximity = None
                associations = None
                if proximity_engine and raw_tracks:
                    proximity = proximity_engine.assess(raw_tracks, frame_id=frame_id)
                if association_engine and raw_tracks:
                    associations = association_engine.assess(raw_tracks, frame_id=frame_id)

                # Build risk result
                risk_data = []
                if risk_summary:
                    for risk in risk_summary.track_risks:
                        risk_data.append({
                            "track_id": str(risk.track_id),
                            "score": float(risk.score),
                            "level": risk.level.value,
                            "is_concerning": risk.is_concerning,
                            "explanation": (
                                risk.explanation.summary if risk.explanation else ""
                            ),
                        })

                results.append({
                    "camera_id": camera_id,
                    "frame_id": frame_id,
                    "timestamp": msg.get("timestamp", time.time()),
                    "track_count": msg.get("track_count", 0),
                    "detection_count": msg.get("detection_count", 0),
                    "risks": risk_data,
                    "max_risk_score": max(
                        (r["score"] for r in risk_data), default=0.0
                    ),
                    "concerning_count": sum(
                        1 for r in risk_data if r["is_concerning"]
                    ),
                    "crowd_density": msg.get("crowd_density", 0.0),
                    "_frame": frame,
                    "_risk_summary": risk_summary,
                    "_proximity": proximity,
                    "_associations": associations,
                })

            except Exception as exc:
                logger.error(
                    "Risk scoring failed camera_id=%s frame_id=%s: %s",
                    camera_id,
                    frame_id,
                    exc,
                )

        return results

    def remove_camera(self, camera_id: str) -> None:
        """Clean up state for a removed camera."""
        self._risk_engines.pop(camera_id, None)
        self._proximity_engines.pop(camera_id, None)
        self._association_engines.pop(camera_id, None)
