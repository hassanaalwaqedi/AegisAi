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
        self._weapon_aggression_engines: Dict[str, Any] = {}

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
                from aegis.risk.person_weapon_association import PersonWeaponAssociationEngine
                self._association_engines[camera_id] = PersonWeaponAssociationEngine()
            except ImportError:
                return None
        return self._association_engines[camera_id]

    def _get_weapon_aggression_engine(self, camera_id: str):
        if camera_id not in self._weapon_aggression_engines:
            try:
                from aegis.risk.weapon_aggression import WeaponAggressionRiskLayer

                self._weapon_aggression_engines[camera_id] = WeaponAggressionRiskLayer()
            except ImportError:
                return None
        return self._weapon_aggression_engines[camera_id]

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
                weapon_aggression_engine = self._get_weapon_aggression_engine(camera_id)

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

                analysis_by_track = {
                    analysis.track_id: analysis for analysis in track_analyses
                }
                threat_contexts = []
                if weapon_aggression_engine and raw_tracks:
                    threat_contexts = weapon_aggression_engine.assess(
                        tracks=raw_tracks,
                        associations=associations or [],
                        analyses=analysis_by_track,
                        frame_id=frame_id,
                    )

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

                risk_by_track = {str(item["track_id"]): item for item in risk_data}
                associated_weapon_ids = {
                    str(context.weapon_track_id)
                    for context in threat_contexts
                    if context.weapon_track_id is not None
                }
                for track in raw_tracks:
                    track_id = str(getattr(track, "track_id", ""))
                    is_weapon = bool(getattr(track, "is_weapon", False)) or str(
                        getattr(track, "object_category", "")
                    ).lower() == "weapon"
                    if not is_weapon or track_id in associated_weapon_ids:
                        continue
                    confidence = float(getattr(track, "confidence", 0.0) or 0.0)
                    level = "MEDIUM" if confidence >= 0.50 else "CANDIDATE_MEDIUM"
                    score = 0.40 if confidence >= 0.50 else 0.30
                    existing = risk_by_track.get(track_id)
                    if existing is None:
                        existing = {"track_id": track_id}
                        risk_data.append(existing)
                        risk_by_track[track_id] = existing
                    if score >= float(existing.get("score", 0.0)):
                        existing.update({
                            "score": score,
                            "level": level,
                            "is_concerning": level == "MEDIUM",
                            "explanation": (
                                f"Possible {getattr(track, 'class_name', 'weapon')} detected without person association. "
                                "Operator review required."
                            ),
                            "reason_codes": [
                                "WEAPON_LIKE_OBJECT_DETECTION",
                                "WEAPON_DETECTED_WITHOUT_PERSON_ASSOCIATION"
                                if confidence >= 0.50
                                else "LOW_CONFIDENCE_WEAPON_CANDIDATE",
                            ],
                            "event_type": "weapon_detected",
                            "weapon_track_id": track_id,
                            "weapon_class": str(getattr(track, "class_name", "weapon")),
                            "weapon_confidence": confidence,
                            "object_class": str(getattr(track, "class_name", "weapon")),
                            "bbox": list(getattr(track, "bbox", (0, 0, 0, 0))),
                            "evidence_objects": [{
                                "object_class": str(getattr(track, "class_name", "weapon")),
                                "track_id": track_id,
                                "bbox": list(getattr(track, "bbox", (0, 0, 0, 0))),
                                "confidence": confidence,
                                "model_source": str(getattr(track, "model_source", "")),
                            }],
                        })
                for context in threat_contexts:
                    context_payload = context.to_dict()
                    actor_id = str(context.armed_person_track_id)
                    existing = risk_by_track.get(actor_id)
                    if existing is None:
                        existing = {"track_id": actor_id}
                        risk_data.append(existing)
                        risk_by_track[actor_id] = existing
                    level_rank = {"LOW": 0, "CANDIDATE_MEDIUM": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
                    existing_level = str(existing.get("level") or "LOW")
                    merged_level = (
                        context.risk_level
                        if level_rank.get(context.risk_level, 0) >= level_rank.get(existing_level, 0)
                        else existing_level
                    )
                    existing.update({
                            "score": max(float(context.risk_score), float(existing.get("score", 0.0))),
                            "level": merged_level,
                            "is_concerning": bool(existing.get("is_concerning")) or context.risk_level in {"MEDIUM", "HIGH", "CRITICAL"},
                            "explanation": context.explanation,
                            "reason_codes": list(context.reason_codes),
                            "event_type": context.event_type,
                            "person_track_id": actor_id,
                            "object_class": "person",
                            "weapon_track_id": context.weapon_track_id,
                            "nearby_person_track_id": context.nearby_person_track_id,
                            "weapon_class": context.weapon_class,
                            "weapon_confidence": context.weapon_confidence,
                            "bbox": context.armed_person_bbox,
                            "evidence_objects": [
                                {
                                    "object_class": context.weapon_class,
                                    "track_id": context.weapon_track_id,
                                    "bbox": context.weapon_bbox,
                                    "confidence": context.weapon_confidence,
                                    "model_source": context.weapon_model_source,
                                },
                                {
                                    "object_class": "person",
                                    "track_id": actor_id,
                                    "bbox": context.armed_person_bbox,
                                    "role": "observed_person",
                                },
                                *([{
                                    "object_class": "person",
                                    "track_id": context.nearby_person_track_id,
                                    "bbox": context.nearby_person_bbox,
                                    "role": "nearby_person",
                                }] if context.nearby_person_track_id else []),
                            ] if context.weapon_track_id else [
                                {
                                    "object_class": "person",
                                    "track_id": actor_id,
                                    "bbox": context.armed_person_bbox,
                                    "role": "observed_person",
                                },
                                {
                                    "object_class": "person",
                                    "track_id": context.nearby_person_track_id,
                                    "bbox": context.nearby_person_bbox,
                                    "role": "nearby_person",
                                },
                            ],
                            "threat_context": context_payload,
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
                    "_threat_contexts": threat_contexts,
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
        self._weapon_aggression_engines.pop(camera_id, None)
