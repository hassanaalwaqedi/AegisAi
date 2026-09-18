"""
AegisAI - Tracking Pipeline Stage

Consumes detection results and assigns persistent track IDs using
ByteTrack. Maintains per-camera tracker state and publishes tracked
objects with history.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from aegis.pipeline.stages import PipelineStage, Streams

logger = logging.getLogger(__name__)


class TrackingStage(PipelineStage):
    """
    Multi-object tracking pipeline stage.

    Maintains one ByteTrack tracker instance per camera. Reads detection
    results, updates tracks, publishes tracked objects with stable IDs.
    """

    def __init__(self, **kwargs):
        super().__init__(
            name="tracking",
            input_stream=Streams.DETECTIONS,
            output_stream=Streams.TRACKS,
            **kwargs,
        )
        self._trackers: Dict[str, Any] = {}
        self._history_managers: Dict[str, Any] = {}
        self._motion_analyzers: Dict[str, Any] = {}
        self._behavior_analyzers: Dict[str, Any] = {}
        self._crowd_analyzers: Dict[str, Any] = {}
        self._camera_start_ts: Dict[str, float] = {}

    def _get_tracker(self, camera_id: str):
        """Get or create a tracker for a camera."""
        if camera_id not in self._trackers:
            try:
                from aegis.tracking.bytetrack_tracker import ByteTrackTracker
                self._trackers[camera_id] = ByteTrackTracker()
            except ImportError:
                from aegis.tracking import DeepSORTTracker
                self._trackers[camera_id] = DeepSORTTracker()
        return self._trackers[camera_id]

    def _get_history_manager(self, camera_id: str):
        if camera_id not in self._history_managers:
            from aegis.analysis import TrackHistoryManager
            self._history_managers[camera_id] = TrackHistoryManager()
        return self._history_managers[camera_id]

    def _get_motion_analyzer(self, camera_id: str):
        if camera_id not in self._motion_analyzers:
            from aegis.analysis import MotionAnalyzer
            self._motion_analyzers[camera_id] = MotionAnalyzer()
        return self._motion_analyzers[camera_id]

    def _get_behavior_analyzer(self, camera_id: str):
        if camera_id not in self._behavior_analyzers:
            from aegis.analysis import BehaviorAnalyzer
            self._behavior_analyzers[camera_id] = BehaviorAnalyzer(
                motion_analyzer=self._get_motion_analyzer(camera_id)
            )
        return self._behavior_analyzers[camera_id]

    def _get_crowd_analyzer(self, camera_id: str):
        if camera_id not in self._crowd_analyzers:
            from aegis.analysis import CrowdAnalyzer
            self._crowd_analyzers[camera_id] = CrowdAnalyzer()
        return self._crowd_analyzers[camera_id]

    def process(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Run tracking on detection results.

        Input: detection results from DetectionStage
        Output: tracked objects with IDs, history, motion, behavior
        """
        results = []

        for msg in messages:
            camera_id = msg.get("camera_id", "unknown")
            frame_id = msg.get("frame_id", 0)
            frame = msg.get("_frame")

            if frame is None:
                continue

            if camera_id not in self._camera_start_ts:
                self._camera_start_ts[camera_id] = time.time()

            try:
                # Reconstruct detection objects for the tracker
                raw_detections = msg.get("detections", [])
                detections = self._reconstruct_detections(raw_detections)

                tracker = self._get_tracker(camera_id)
                tracks = tracker.update(detections, frame)

                timestamp_seconds = time.time() - self._camera_start_ts[camera_id]

                # Run analysis chain
                history_manager = self._get_history_manager(camera_id)
                history_manager.update(tracks, frame_id=frame_id, timestamp=timestamp_seconds)

                motion_states = self._get_motion_analyzer(camera_id).analyze_all(history_manager)
                behaviors = self._get_behavior_analyzer(camera_id).analyze_all(
                    history_manager, motion_states
                )
                crowd_metrics = self._get_crowd_analyzer(camera_id).analyze(tracks, frame.shape)

                # Build track analysis payloads
                track_data = []
                for track in tracks:
                    track_id = str(getattr(track, "track_id", ""))
                    history = history_manager.get_history(track.track_id)
                    motion = motion_states.get(track.track_id)
                    behavior = behaviors.get(track.track_id)

                    track_data.append({
                        "track_id": track_id,
                        "class_id": int(getattr(track, "class_id", 0)),
                        "class_name": str(getattr(track, "class_name", "unknown")),
                        "bbox": list(getattr(track, "bbox", (0, 0, 0, 0))),
                        "is_person": bool(getattr(track, "is_person", False)),
                        "is_weapon": bool(getattr(track, "is_weapon", False)),
                        "is_vehicle": bool(getattr(track, "is_vehicle", False)),
                        "history_length": history.history_length if history else 0,
                        "duration": history.duration if history else 0.0,
                        "has_motion": motion is not None,
                        "has_behavior": behavior is not None,
                        "has_anomaly": (
                            behavior.has_anomaly if behavior else False
                        ),
                    })

                results.append({
                    "camera_id": camera_id,
                    "frame_id": frame_id,
                    "timestamp": msg.get("timestamp", time.time()),
                    "tracks": track_data,
                    "track_count": len(track_data),
                    "crowd_density": getattr(crowd_metrics, "density", 0.0),
                    "detection_count": msg.get("detection_count", 0),
                    "inference_ms": msg.get("inference_ms", 0),
                    "_frame": frame,
                    "_tracks": tracks,
                    "_track_analyses_raw": {
                        "motion_states": motion_states,
                        "behaviors": behaviors,
                        "crowd_metrics": crowd_metrics,
                        "history_manager": history_manager,
                    },
                })

            except Exception as exc:
                logger.error(
                    "Tracking failed camera_id=%s frame_id=%s: %s",
                    camera_id,
                    frame_id,
                    exc,
                )

        return results

    def _reconstruct_detections(self, raw: List[Dict[str, Any]]) -> list:
        """Convert serialized detections back to Detection objects."""
        try:
            from aegis.detection.yolo_detector import Detection

            return [
                Detection(
                    bbox=tuple(d["bbox"]),
                    confidence=d["confidence"],
                    class_id=d["class_id"],
                    class_name=d["class_name"],
                    object_category=d.get("object_category", "generic"),
                    is_weapon=bool(d.get("is_weapon", False)),
                    is_person=bool(d.get("is_person", False)),
                    is_vehicle=bool(d.get("is_vehicle", False)),
                    is_animal=bool(d.get("is_animal", False)),
                    model_source=str(d.get("model_source", "")),
                    source_class_id=d.get("source_class_id"),
                )
                for d in raw
            ]
        except (ImportError, KeyError):
            return []

    def remove_camera(self, camera_id: str) -> None:
        """Clean up state for a removed camera."""
        self._trackers.pop(camera_id, None)
        self._history_managers.pop(camera_id, None)
        self._motion_analyzers.pop(camera_id, None)
        self._behavior_analyzers.pop(camera_id, None)
        self._crowd_analyzers.pop(camera_id, None)
        self._camera_start_ts.pop(camera_id, None)
