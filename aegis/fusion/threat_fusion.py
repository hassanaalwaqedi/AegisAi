"""Deterministic, evidence-only YOLOE/person fusion.

This module intentionally does not import or call the risk engine.  It turns
open-vocabulary *candidates* into attributable temporal observations for a
later situation-intelligence phase; it never claims possession or intent.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Optional


BBox = tuple[float, float, float, float]

NORMALIZATION_MAP = {
    "handgun": "handgun", "pistol": "handgun", "revolver": "handgun",
    "rifle": "long_gun", "shotgun": "long_gun",
    "knife": "blade", "machete": "blade",
    "baseball bat": "blunt_weapon", "crowbar": "blunt_weapon",
}


@dataclass(frozen=True)
class ThreatFusionConfig:
    enabled: bool = True
    dedup_iou_threshold: float = 0.55
    expanded_person_ratio: float = 0.25
    minimum_association_score: float = 0.45
    winner_margin: float = 0.08
    temporal_ttl_frames: int = 9
    continuity_bonus: float = 0.08


@dataclass
class _Candidate:
    bbox: BBox
    raw_class: str
    normalized_threat_class: str
    detector_confidence: float
    aliases: list[str]
    contributing_confidences: dict[str, float]
    detector: str
    model_source: str


@dataclass
class PersonThreatAssociation:
    """A bounded observation record; association confidence is geometry-only."""

    threat_id: str
    track_id: Optional[str]
    raw_class: str
    normalized_threat_class: str
    detector_confidence: float
    association_confidence: float
    bbox: list[float]
    aliases: list[str]
    contributing_confidences: dict[str, float]
    first_seen_frame: int
    last_seen_frame: int
    observations: int
    association_state: str
    persistence_state: str
    observed_now: bool
    detector: str = "threat_yoloe"
    model_source: str = ""
    age_frames: int = 0
    diagnostics: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class ThreatFusionEngine:
    """Associate normalized YOLOE candidates to current person tracks cheaply.

    Score = 0.55 * expanded-region containment + 0.25 * threat overlap
    + 0.20 * normalized proximity + bounded continuity bonus.  Detector
    confidence is intentionally excluded from this score.
    """

    def __init__(self, config: Optional[ThreatFusionConfig] = None):
        self.config = config or ThreatFusionConfig()
        self._evidence: dict[str, PersonThreatAssociation] = {}
        self._sequence = 0
        self._last_diagnostics: dict[str, int | float] = {}

    @classmethod
    def from_detection_config(cls, config: Any) -> "ThreatFusionEngine":
        return cls(ThreatFusionConfig(
            enabled=bool(getattr(config, "threat_fusion_enabled", True)),
            dedup_iou_threshold=float(getattr(config, "threat_dedup_iou_threshold", 0.55)),
            expanded_person_ratio=float(getattr(config, "threat_person_expansion_ratio", 0.25)),
            minimum_association_score=float(getattr(config, "threat_association_min_score", 0.45)),
            winner_margin=float(getattr(config, "threat_association_winner_margin", 0.08)),
            temporal_ttl_frames=int(getattr(config, "threat_evidence_ttl_frames", 9)),
            continuity_bonus=float(getattr(config, "threat_continuity_bonus", 0.08)),
        ))

    @staticmethod
    def normalize(raw_class: str) -> str:
        value = " ".join(str(raw_class).strip().lower().replace("_", " ").split())
        return NORMALIZATION_MAP.get(value, value or "unknown")

    def fuse(
        self,
        camera_id: str,
        frame_id: int,
        detections: Iterable[Any],
        tracks: Iterable[Any],
        *,
        threat_observed: bool,
    ) -> list[PersonThreatAssociation]:
        """Advance TTL every frame; only create observations on YOLOE frames."""
        if not self.config.enabled:
            self._last_diagnostics = {"fusion_enabled": 0, "active_person_tracks": 0, "current_threat_candidates": 0, "associated_threats": 0, "ambiguous_threats": 0, "unassociated_threats": 0, "persistent_threat_evidence": 0}
            return []
        persons = [track for track in tracks if self._is_person(track)]
        for item in self._evidence.values():
            item.observed_now = False
            item.age_frames = max(0, int(frame_id) - item.last_seen_frame)
            if item.track_id and not any(str(getattr(person, "track_id", "")) == item.track_id for person in persons):
                if item.persistence_state != "expired":
                    item.association_state = "unassociated"
                    item.persistence_state = "stale"
            if item.age_frames > self.config.temporal_ttl_frames:
                item.association_state = "unassociated"
                item.persistence_state = "expired"

        raw = [self._candidate(det) for det in detections if self._is_threat_candidate(det)] if threat_observed else []
        candidates = self._deduplicate(raw)
        associated = ambiguous = unassociated = 0
        for candidate in candidates:
            track_id, score, state, diagnostics = self._associate(candidate, persons)
            existing = self._match_existing(candidate, track_id)
            if existing is None:
                self._sequence += 1
                existing = PersonThreatAssociation(
                    threat_id=f"{camera_id}:threat:{self._sequence}", track_id=track_id,
                    raw_class=candidate.raw_class, normalized_threat_class=candidate.normalized_threat_class,
                    detector_confidence=candidate.detector_confidence, association_confidence=score,
                    bbox=list(candidate.bbox), aliases=candidate.aliases,
                    contributing_confidences=candidate.contributing_confidences,
                    first_seen_frame=frame_id, last_seen_frame=frame_id, observations=1,
                    association_state=state, persistence_state="new", observed_now=True,
                    detector=candidate.detector, model_source=candidate.model_source, diagnostics=diagnostics,
                )
                self._evidence[existing.threat_id] = existing
            else:
                existing.track_id = track_id
                existing.raw_class = candidate.raw_class
                existing.detector_confidence = candidate.detector_confidence
                existing.association_confidence = score
                existing.bbox = list(candidate.bbox)
                existing.aliases = candidate.aliases
                existing.contributing_confidences = candidate.contributing_confidences
                existing.last_seen_frame = frame_id
                existing.observations += 1
                existing.association_state = state
                existing.persistence_state = "persistent" if existing.observations >= 2 else "new"
                existing.observed_now = True
                existing.age_frames = 0
                existing.diagnostics = diagnostics
            if state == "probable": associated += 1
            elif state == "ambiguous": ambiguous += 1
            else: unassociated += 1

        self._last_diagnostics = {
            "fusion_enabled": 1,
            "active_person_tracks": len(persons), "current_threat_candidates": len(candidates),
            "associated_threats": associated, "ambiguous_threats": ambiguous,
            "unassociated_threats": unassociated,
            "persistent_threat_evidence": sum(1 for item in self._evidence.values() if item.persistence_state == "persistent"),
        }
        return [item for item in self._evidence.values() if item.persistence_state != "expired"]

    def diagnostics(self) -> dict[str, int | float]:
        return dict(self._last_diagnostics)

    def _associate(self, candidate: _Candidate, persons: list[Any]) -> tuple[Optional[str], float, str, dict[str, float]]:
        scored: list[tuple[str, float, dict[str, float]]] = []
        for person in persons:
            person_bbox = self._bbox(person)
            center = self._center(candidate.bbox)
            expanded = self._expand(person_bbox)
            inside = 1.0 if self._inside(center, expanded) else 0.0
            overlap = self._overlap_ratio(candidate.bbox, expanded)
            distance = self._distance_to_box(center, person_bbox)
            diagonal = max(math.hypot(person_bbox[2] - person_bbox[0], person_bbox[3] - person_bbox[1]), 1.0)
            proximity = max(0.0, 1.0 - distance / diagonal)
            geometry = 0.55 * inside + 0.25 * overlap + 0.20 * proximity
            track_id = str(getattr(person, "track_id", ""))
            continuity = self.config.continuity_bonus if self._has_recent_match(candidate, track_id) else 0.0
            score = min(1.0, geometry + continuity)
            scored.append((track_id, score, {"containment": round(inside, 4), "overlap": round(overlap, 4), "proximity": round(proximity, 4), "continuity": round(continuity, 4), "geometry_score": round(geometry, 4)}))
        if not scored:
            return None, 0.0, "unassociated", {}
        scored.sort(key=lambda value: value[1], reverse=True)
        track_id, score, diagnostics = scored[0]
        if score < self.config.minimum_association_score:
            return None, score, "unassociated", diagnostics
        if len(scored) > 1 and score - scored[1][1] < self.config.winner_margin:
            diagnostics["runner_up_score"] = round(scored[1][1], 4)
            return None, score, "ambiguous", diagnostics
        return track_id, score, "probable", diagnostics

    def _deduplicate(self, candidates: list[_Candidate]) -> list[_Candidate]:
        retained: list[_Candidate] = []
        for candidate in sorted(candidates, key=lambda value: value.detector_confidence, reverse=True):
            match = next((item for item in retained if item.normalized_threat_class == candidate.normalized_threat_class and self._iou(item.bbox, candidate.bbox) >= self.config.dedup_iou_threshold), None)
            if match is None:
                retained.append(candidate)
                continue
            match.aliases = sorted(set([*match.aliases, *candidate.aliases]))
            match.contributing_confidences.update(candidate.contributing_confidences)
        return retained

    def _match_existing(self, candidate: _Candidate, track_id: Optional[str]) -> Optional[PersonThreatAssociation]:
        possible = [item for item in self._evidence.values() if item.persistence_state != "expired" and item.normalized_threat_class == candidate.normalized_threat_class]
        if track_id:
            same_track = [
                item for item in possible
                if item.track_id == track_id and self._iou(tuple(item.bbox), candidate.bbox) >= 0.25
            ]
            if same_track:
                return max(same_track, key=lambda item: self._iou(tuple(item.bbox), candidate.bbox))
        return next((item for item in possible if self._iou(tuple(item.bbox), candidate.bbox) >= 0.25), None)

    def _has_recent_match(self, candidate: _Candidate, track_id: str) -> bool:
        return any(item.track_id == track_id and item.normalized_threat_class == candidate.normalized_threat_class and item.persistence_state != "expired" for item in self._evidence.values())

    @staticmethod
    def _is_person(value: Any) -> bool:
        return bool(getattr(value, "is_person", False)) or str(getattr(value, "class_name", "")).lower() == "person"

    @staticmethod
    def _is_threat_candidate(value: Any) -> bool:
        return str(getattr(value, "evidence_type", "")) == "threat_candidate" or str(getattr(value, "detector", "")) == "threat_yoloe"

    def _candidate(self, value: Any) -> _Candidate:
        raw = str(getattr(value, "class_name", "unknown"))
        return _Candidate(self._bbox(value), raw, self.normalize(raw), float(getattr(value, "confidence", 0.0) or 0.0), [raw], {raw: float(getattr(value, "confidence", 0.0) or 0.0)}, str(getattr(value, "detector", "threat_yoloe")), str(getattr(value, "model_source", "")))

    @staticmethod
    def _bbox(value: Any) -> BBox:
        bbox = getattr(value, "bbox", (0, 0, 0, 0))
        return tuple(float(part) for part in bbox)  # type: ignore[return-value]

    def _expand(self, bbox: BBox) -> BBox:
        width, height = bbox[2] - bbox[0], bbox[3] - bbox[1]
        return (bbox[0] - width * self.config.expanded_person_ratio, bbox[1] - height * self.config.expanded_person_ratio, bbox[2] + width * self.config.expanded_person_ratio, bbox[3] + height * self.config.expanded_person_ratio)

    @staticmethod
    def _center(bbox: BBox) -> tuple[float, float]: return ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
    @staticmethod
    def _inside(point: tuple[float, float], bbox: BBox) -> bool: return bbox[0] <= point[0] <= bbox[2] and bbox[1] <= point[1] <= bbox[3]
    @classmethod
    def _distance_to_box(cls, point: tuple[float, float], bbox: BBox) -> float:
        return math.hypot(max(bbox[0] - point[0], 0, point[0] - bbox[2]), max(bbox[1] - point[1], 0, point[1] - bbox[3]))
    @staticmethod
    def _iou(a: BBox, b: BBox) -> float:
        x1, y1, x2, y2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        union = max(0, a[2]-a[0]) * max(0, a[3]-a[1]) + max(0, b[2]-b[0]) * max(0, b[3]-b[1]) - inter
        return inter / union if union else 0.0
    @staticmethod
    def _overlap_ratio(inner: BBox, outer: BBox) -> float:
        x1, y1, x2, y2 = max(inner[0], outer[0]), max(inner[1], outer[1]), min(inner[2], outer[2]), min(inner[3], outer[3])
        area = max(0, inner[2]-inner[0]) * max(0, inner[3]-inner[1])
        return max(0, x2-x1) * max(0, y2-y1) / area if area else 0.0
