"""
AegisAI - ByteTrack Multi-Object Tracker

Lightweight, CPU-optimized tracker using ByteTrack via supervision library.
Pure IoU-based association — no neural network embeddings needed.

Phase 1: Edge/CPU Perception Layer
"""

import logging
from typing import List, Optional, Tuple, NamedTuple

import numpy as np
import supervision as sv

from config import AegisConfig
from aegis.core.interfaces import BaseTracker

logger = logging.getLogger(__name__)


def _bbox_iou(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> float:
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    if inter <= 0:
        return 0.0
    area_a = max(0, a[2] - a[0]) * max(0, a[3] - a[1])
    area_b = max(0, b[2] - b[0]) * max(0, b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


class Track(NamedTuple):
    """Standardized tracking result — compatible with existing pipeline."""
    track_id: int
    bbox: Tuple[int, int, int, int]
    class_id: int
    class_name: str
    confidence: float
    is_confirmed: bool = True
    object_category: str = "generic"
    is_weapon: bool = False
    is_person: bool = False
    is_vehicle: bool = False
    is_animal: bool = False
    model_source: str = ""
    source_class_id: Optional[int] = None


class ByteTrackTracker(BaseTracker):
    """
    ByteTrack multi-object tracker (CPU-optimized).
    
    Uses supervision's ByteTrack: pure IoU-based, no appearance model.
    Significantly faster than DeepSORT on CPU-only environments.

    Example:
        >>> tracker = ByteTrackTracker()
        >>> tracks = tracker.update(detections, frame)
    """

    def __init__(self, config: Optional[AegisConfig] = None):
        if config is not None and hasattr(config, 'bytetrack'):
            bt = config.bytetrack
            self._activation_thresh = bt.track_activation_threshold
            self._lost_buffer = bt.lost_track_buffer
            self._min_match = bt.minimum_matching_threshold
            self._fps = bt.frame_rate
        else:
            self._activation_thresh = 0.25
            self._lost_buffer = 30
            self._min_match = 0.8
            self._fps = 30

        self._tracker = sv.ByteTrack(
            track_activation_threshold=self._activation_thresh,
            lost_track_buffer=self._lost_buffer,
            minimum_matching_threshold=self._min_match,
            frame_rate=self._fps,
        )
        self._track_metadata: dict = {}
        self._total_tracks_created = 0

        logger.info(
            f"ByteTrackTracker initialized | "
            f"threshold={self._activation_thresh}, buffer={self._lost_buffer}"
        )

    def update(self, detections: list, frame: np.ndarray) -> List[Track]:
        """Update tracker with new detections, return active tracks."""
        if len(detections) == 0:
            empty_sv = sv.Detections.empty()
            self._tracker.update_with_detections(empty_sv)
            return []

        # Convert Detection list → sv.Detections
        bboxes, confs, cls_ids, metas = [], [], [], []
        for det in detections:
            b = det.bbox if isinstance(det.bbox, (list, tuple)) else (0, 0, 0, 0)
            bboxes.append([b[0], b[1], b[2], b[3]])
            confs.append(det.confidence)
            cls_ids.append(det.class_id)
            metas.append({
                "class_id": det.class_id,
                "class_name": det.class_name,
                "confidence": det.confidence,
                "object_category": getattr(det, "object_category", "generic"),
                "is_weapon": getattr(det, "is_weapon", False),
                "is_person": getattr(det, "is_person", False),
                "is_vehicle": getattr(det, "is_vehicle", False),
                "is_animal": getattr(det, "is_animal", False),
                "model_source": getattr(det, "model_source", ""),
                "source_class_id": getattr(det, "source_class_id", None),
            })

        sv_dets = sv.Detections(
            xyxy=np.array(bboxes, dtype=np.float32),
            confidence=np.array(confs, dtype=np.float32),
            class_id=np.array(cls_ids, dtype=int),
        )

        # Run ByteTrack
        tracked = self._tracker.update_with_detections(sv_dets)

        # Convert back to Track objects
        tracks = []
        if tracked.tracker_id is not None and len(tracked.tracker_id) > 0:
            for i in range(len(tracked.tracker_id)):
                tid = int(tracked.tracker_id[i])
                self._total_tracks_created = max(self._total_tracks_created, tid)

                xyxy = tracked.xyxy[i]
                bbox = (int(xyxy[0]), int(xyxy[1]), int(xyxy[2]), int(xyxy[3]))
                conf = float(tracked.confidence[i]) if tracked.confidence is not None else 0.0
                cid = int(tracked.class_id[i]) if tracked.class_id is not None else 0

                # Match metadata back to the tracked detection by class and bbox IoU.
                meta = self._match_metadata(bbox, cid, detections, metas)
                if meta:
                    self._track_metadata[tid] = meta

                stored = self._track_metadata.get(tid, {})

                tracks.append(Track(
                    track_id=tid,
                    bbox=bbox,
                    class_id=stored.get("class_id", cid),
                    class_name=stored.get("class_name", f"class_{cid}"),
                    confidence=conf,
                    is_confirmed=True,
                    object_category=stored.get("object_category", "generic"),
                    is_weapon=stored.get("is_weapon", False),
                    is_person=stored.get("is_person", False),
                    is_vehicle=stored.get("is_vehicle", False),
                    is_animal=stored.get("is_animal", False),
                    model_source=stored.get("model_source", ""),
                    source_class_id=stored.get("source_class_id"),
                ))

        logger.debug(f"Active tracks: {len(tracks)}")
        return tracks

    def _match_metadata(self, bbox: Tuple[int, int, int, int], class_id: int, detections: list, metas: list) -> Optional[dict]:
        best_index = None
        best_iou = -1.0
        for index, det in enumerate(detections):
            if metas[index]["class_id"] != class_id:
                continue
            iou = _bbox_iou(bbox, det.bbox)
            if iou > best_iou:
                best_iou = iou
                best_index = index
        if best_index is None:
            return None
        return metas[best_index]

    def get_track_count(self) -> int:
        return len(self._track_metadata)

    def get_total_tracks_created(self) -> int:
        return self._total_tracks_created

    def reset(self) -> None:
        self._tracker = sv.ByteTrack(
            track_activation_threshold=self._activation_thresh,
            lost_track_buffer=self._lost_buffer,
            minimum_matching_threshold=self._min_match,
            frame_rate=self._fps,
        )
        self._track_metadata.clear()
        self._total_tracks_created = 0
        logger.info("ByteTrackTracker reset")

    def __repr__(self) -> str:
        return (
            f"ByteTrackTracker(threshold={self._activation_thresh}, "
            f"buffer={self._lost_buffer}, created={self._total_tracks_created})"
        )
