"""
Person-to-weapon association for evidence-based risk scoring.

This module uses only detector/tracker evidence: bounding boxes, class metadata,
confidence, and temporal stability. It does not infer pose, intent, action, or
hand contact.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple


BBox = Tuple[float, float, float, float]


@dataclass(frozen=True)
class WeaponAssociation:
    """Association evidence between one tracked person and one tracked weapon."""

    person_track_id: str
    weapon_track_id: str
    weapon_class: str
    association_type: str
    association_score: float
    stable_frames: int
    weapon_confidence: float
    person_confidence: float
    iou: float
    center_distance: float
    normalized_distance: float
    person_bbox: List[float]
    weapon_bbox: List[float]
    frame_id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "person_track_id": self.person_track_id,
            "weapon_track_id": self.weapon_track_id,
            "weapon_class": self.weapon_class,
            "association_type": self.association_type,
            "association_score": round(self.association_score, 3),
            "stable_frames": self.stable_frames,
            "weapon_confidence": round(self.weapon_confidence, 3),
            "person_confidence": round(self.person_confidence, 3),
            "iou": round(self.iou, 4),
            "center_distance": round(self.center_distance, 2),
            "normalized_distance": round(self.normalized_distance, 3),
            "person_bbox": self.person_bbox,
            "weapon_bbox": self.weapon_bbox,
            "frame_id": self.frame_id,
        }


class PersonWeaponAssociationEngine:
    """
    Associates tracked weapons with tracked persons using geometric evidence.

    A relationship must persist over frames before it can be treated as stable.
    The output deliberately says "associated" or "near", not "holding", because
    this layer has no pose or hand-object interaction model.
    """

    def __init__(self, near_distance_ratio: float = 0.80, overlap_threshold: float = 0.04):
        self.near_distance_ratio = near_distance_ratio
        self.overlap_threshold = overlap_threshold
        self._stable_counts: Dict[Tuple[str, str], int] = {}

    def assess(self, tracks: Iterable[Any], frame_id: Optional[int] = None) -> List[WeaponAssociation]:
        persons = [track for track in tracks if self._is_person(track)]
        weapons = [track for track in tracks if self._is_weapon(track)]

        current_pairs: set[Tuple[str, str]] = set()
        associations: List[WeaponAssociation] = []

        for weapon in weapons:
            best = self._best_person_for_weapon(weapon, persons)
            if best is None:
                continue

            person, association_type, score, iou, distance, normalized_distance = best
            pair_key = (str(getattr(person, "track_id")), str(getattr(weapon, "track_id")))
            current_pairs.add(pair_key)

            if association_type == "none":
                self._stable_counts[pair_key] = 0
                stable_frames = 0
            else:
                stable_frames = self._stable_counts.get(pair_key, 0) + 1
                self._stable_counts[pair_key] = stable_frames

            associations.append(
                WeaponAssociation(
                    person_track_id=str(getattr(person, "track_id")),
                    weapon_track_id=str(getattr(weapon, "track_id")),
                    weapon_class=str(getattr(weapon, "class_name", "weapon")).lower(),
                    association_type=association_type,
                    association_score=score,
                    stable_frames=stable_frames,
                    weapon_confidence=float(getattr(weapon, "confidence", 0.0) or 0.0),
                    person_confidence=float(getattr(person, "confidence", 0.0) or 0.0),
                    iou=iou,
                    center_distance=distance,
                    normalized_distance=normalized_distance,
                    person_bbox=list(self._bbox(person)),
                    weapon_bbox=list(self._bbox(weapon)),
                    frame_id=frame_id,
                )
            )

        for pair_key in list(self._stable_counts):
            if pair_key not in current_pairs:
                self._stable_counts[pair_key] = 0

        return associations

    def reset(self) -> None:
        self._stable_counts.clear()

    def _best_person_for_weapon(
        self,
        weapon: Any,
        persons: List[Any],
    ) -> Optional[Tuple[Any, str, float, float, float, float]]:
        if not persons:
            return None

        weapon_bbox = self._bbox(weapon)
        weapon_center = self._center(weapon_bbox)
        best: Optional[Tuple[Any, str, float, float, float, float]] = None

        for person in persons:
            person_bbox = self._bbox(person)
            iou = self._iou(person_bbox, weapon_bbox)
            overlap_ratio = self._overlap_ratio(weapon_bbox, person_bbox)
            center_inside = self._point_inside(weapon_center, person_bbox)
            distance = self._distance(self._center(person_bbox), weapon_center)
            normalized_distance = distance / max(self._diagonal(person_bbox), 1.0)

            association_type = "none"
            score = 0.0
            if center_inside:
                association_type = "contained"
                score = 0.92 + min(overlap_ratio, 0.08)
            elif iou >= self.overlap_threshold or overlap_ratio >= 0.25:
                association_type = "overlap"
                score = 0.78 + min(max(iou, overlap_ratio) * 0.30, 0.17)
            elif normalized_distance <= self.near_distance_ratio:
                association_type = "near"
                score = max(0.35, 0.72 - normalized_distance * 0.35)

            score = max(0.0, min(score, 0.99))
            candidate = (person, association_type, score, iou, distance, normalized_distance)
            if best is None or candidate[2] > best[2]:
                best = candidate

        return best

    @staticmethod
    def _is_person(track: Any) -> bool:
        return bool(getattr(track, "is_person", False)) or str(getattr(track, "class_name", "")).lower() == "person"

    @staticmethod
    def _is_weapon(track: Any) -> bool:
        class_name = str(getattr(track, "class_name", "")).lower()
        return bool(getattr(track, "is_weapon", False)) or class_name in {"knife", "pistol"}

    @staticmethod
    def _bbox(track: Any) -> BBox:
        bbox = getattr(track, "bbox", (0.0, 0.0, 0.0, 0.0))
        return (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))

    @staticmethod
    def _center(bbox: BBox) -> Tuple[float, float]:
        return ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)

    @staticmethod
    def _point_inside(point: Tuple[float, float], bbox: BBox) -> bool:
        return bbox[0] <= point[0] <= bbox[2] and bbox[1] <= point[1] <= bbox[3]

    @staticmethod
    def _distance(a: Tuple[float, float], b: Tuple[float, float]) -> float:
        return math.hypot(a[0] - b[0], a[1] - b[1])

    @staticmethod
    def _diagonal(bbox: BBox) -> float:
        return math.hypot(max(bbox[2] - bbox[0], 0.0), max(bbox[3] - bbox[1], 0.0))

    @staticmethod
    def _iou(a: BBox, b: BBox) -> float:
        x1 = max(a[0], b[0])
        y1 = max(a[1], b[1])
        x2 = min(a[2], b[2])
        y2 = min(a[3], b[3])
        inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        if inter <= 0:
            return 0.0
        area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
        area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
        union = area_a + area_b - inter
        return inter / union if union > 0 else 0.0

    @staticmethod
    def _overlap_ratio(inner: BBox, outer: BBox) -> float:
        x1 = max(inner[0], outer[0])
        y1 = max(inner[1], outer[1])
        x2 = min(inner[2], outer[2])
        y2 = min(inner[3], outer[3])
        inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        area_inner = max(0.0, inner[2] - inner[0]) * max(0.0, inner[3] - inner[1])
        return inter / area_inner if area_inner > 0 else 0.0
