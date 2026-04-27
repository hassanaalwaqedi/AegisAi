"""
AegisAI - Proximity Risk Engine (Phase 1, CPU-Only)

Lightweight, rule-based risk engine for edge deployment.
Evaluates person-weapon proximity and temporal stability
to produce fast risk assessments without heavy AI models.

Rules:
    1. Person + Weapon in same frame → MEDIUM (0.5)
    2. Weapon bbox overlaps Person bbox → boost to 0.7
    3. Same pair stable across N frames → HIGH (0.85)
    4. Behavioral anomaly flags → +0.1 boost

Phase 1: Edge/CPU Risk Intelligence
"""

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from config import AegisConfig
from aegis.core.interfaces import BaseRiskEngine

logger = logging.getLogger(__name__)


# ─── Data Types ───


@dataclass
class ThreatPair:
    """A tracked person-weapon proximity pair."""
    person_track_id: int
    weapon_track_id: int
    first_seen_frame: int
    last_seen_frame: int
    max_iou: float = 0.0
    consecutive_frames: int = 1

    @property
    def pair_key(self) -> Tuple[int, int]:
        return (self.person_track_id, self.weapon_track_id)


@dataclass
class ProximityRiskAssessment:
    """
    Result of proximity-based risk assessment for a single frame.

    Attributes:
        risk_score: Combined risk score (0.0 - 1.0)
        risk_level: Risk level string (LOW/MEDIUM/HIGH/CRITICAL)
        triggers: List of triggered risk rules
        threat_pairs: Active person-weapon pairs
        should_escalate: Whether to send this to cloud
        frame_id: Frame number
        timestamp: Assessment time
        track_summaries: Lightweight track data for cloud transmission
    """
    risk_score: float = 0.0
    risk_level: str = "LOW"
    triggers: List[str] = field(default_factory=list)
    threat_pairs: List[ThreatPair] = field(default_factory=list)
    should_escalate: bool = False
    frame_id: int = 0
    timestamp: float = 0.0
    track_summaries: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "risk_score": round(self.risk_score, 3),
            "risk_level": self.risk_level,
            "triggers": self.triggers,
            "should_escalate": self.should_escalate,
            "frame_id": self.frame_id,
            "timestamp": self.timestamp,
            "threat_pairs": [
                {
                    "person_id": p.person_track_id,
                    "weapon_id": p.weapon_track_id,
                    "frames": p.consecutive_frames,
                    "max_iou": round(p.max_iou, 3),
                }
                for p in self.threat_pairs
            ],
        }


# ─── Configuration ───


@dataclass
class ProximityRiskConfig:
    """Configuration for the proximity risk engine."""
    enabled: bool = True
    weapon_coexist_score: float = 0.5
    weapon_overlap_score: float = 0.7
    stability_high_score: float = 0.85
    behavioral_boost: float = 0.1
    stability_window: int = 5       # frames for HIGH escalation
    decay_frames: int = 10          # frames before pair expires
    escalation_threshold: float = 0.6
    iou_threshold: float = 0.05
    containment_check: bool = True


# ─── Utility Functions ───


def _bbox_iou(a: tuple, b: tuple) -> float:
    """Compute IoU between two (x1,y1,x2,y2) bboxes."""
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])

    inter = max(0, x2 - x1) * max(0, y2 - y1)
    if inter == 0:
        return 0.0

    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    union = area_a + area_b - inter

    return inter / union if union > 0 else 0.0


def _bbox_contains(outer: tuple, inner: tuple) -> bool:
    """Check if inner bbox center is inside outer bbox."""
    cx = (inner[0] + inner[2]) / 2
    cy = (inner[1] + inner[3]) / 2
    return outer[0] <= cx <= outer[2] and outer[1] <= cy <= outer[3]


def _score_to_level(score: float) -> str:
    """Map risk score to level string."""
    if score >= 0.75:
        return "CRITICAL"
    elif score >= 0.50:
        return "HIGH"
    elif score >= 0.25:
        return "MEDIUM"
    return "LOW"


# ─── Engine ───


class ProximityRiskEngine(BaseRiskEngine):
    """
    Lightweight proximity-based risk engine for Phase 1 (CPU).

    Evaluates person-weapon spatial relationships and tracks
    pair stability across frames to escalate threat levels.

    Example:
        >>> engine = ProximityRiskEngine()
        >>> assessment = engine.assess(tracks, frame_id=42)
        >>> print(f"Risk: {assessment.risk_level} ({assessment.risk_score:.2f})")
    """

    def __init__(
        self,
        config: Optional[AegisConfig] = None,
        risk_config: Optional[ProximityRiskConfig] = None,
    ):
        if config is not None and hasattr(config, 'proximity_risk'):
            pr = config.proximity_risk
            self._config = ProximityRiskConfig(
                enabled=pr.enabled,
                weapon_coexist_score=pr.weapon_coexist_score,
                weapon_overlap_score=pr.weapon_overlap_score,
                stability_high_score=pr.stability_high_score,
                behavioral_boost=pr.behavioral_boost,
                stability_window=pr.stability_window,
                decay_frames=pr.decay_frames,
                escalation_threshold=pr.escalation_threshold,
                iou_threshold=pr.iou_threshold,
            )
        elif risk_config is not None:
            self._config = risk_config
        else:
            self._config = ProximityRiskConfig()

        # Temporal pair tracking: (person_id, weapon_id) → ThreatPair
        self._active_pairs: Dict[Tuple[int, int], ThreatPair] = {}

        # Statistics
        self._total_frames = 0
        self._total_escalations = 0
        self._total_high_risks = 0

        logger.info(
            f"ProximityRiskEngine initialized | "
            f"escalation_threshold={self._config.escalation_threshold}, "
            f"stability_window={self._config.stability_window}"
        )

    def assess(self, tracks: list, frame_id: int = 0, **kwargs) -> ProximityRiskAssessment:
        """
        Assess risk for tracked objects using proximity rules.

        Args:
            tracks: List of Track objects from tracker
            frame_id: Current frame number

        Returns:
            ProximityRiskAssessment with score, level, and triggers
        """
        self._total_frames += 1

        score = 0.0
        triggers = []
        current_pairs: Set[Tuple[int, int]] = set()

        # Classify tracks
        persons = []
        weapons = []

        for track in tracks:
            is_person = getattr(track, 'is_person', False) or getattr(track, 'class_id', -1) == 0
            is_weapon = getattr(track, 'is_weapon', False)

            if is_person:
                persons.append(track)
            if is_weapon:
                weapons.append(track)

        # ── Rule 1: Weapon + Person coexist ──
        if weapons and persons:
            score = max(score, self._config.weapon_coexist_score)
            weapon_names = [getattr(w, 'class_name', 'weapon') for w in weapons]
            triggers.append(f"weapon_person_coexist:{','.join(weapon_names)}")

            # ── Rule 2: Check spatial overlap ──
            for weapon in weapons:
                w_bbox = getattr(weapon, 'bbox', (0, 0, 0, 0))
                w_tid = getattr(weapon, 'track_id', None)

                for person in persons:
                    p_bbox = getattr(person, 'bbox', (0, 0, 0, 0))
                    p_tid = getattr(person, 'track_id', None)

                    iou = _bbox_iou(w_bbox, p_bbox)
                    contained = _bbox_contains(p_bbox, w_bbox) if self._config.containment_check else False

                    if iou > self._config.iou_threshold or contained:
                        score = max(score, self._config.weapon_overlap_score)
                        triggers.append(
                            f"weapon_overlap:iou={iou:.2f}:w={w_tid}:p={p_tid}"
                        )

                    # Track this pair
                    if p_tid is not None and w_tid is not None:
                        pair_key = (p_tid, w_tid)
                        current_pairs.add(pair_key)

                        if pair_key in self._active_pairs:
                            pair = self._active_pairs[pair_key]
                            pair.last_seen_frame = frame_id
                            pair.consecutive_frames += 1
                            pair.max_iou = max(pair.max_iou, iou)
                        else:
                            self._active_pairs[pair_key] = ThreatPair(
                                person_track_id=p_tid,
                                weapon_track_id=w_tid,
                                first_seen_frame=frame_id,
                                last_seen_frame=frame_id,
                                max_iou=iou,
                            )

        # ── Rule 3: Temporal stability → HIGH ──
        stable_pairs = []
        for pair_key, pair in self._active_pairs.items():
            if pair.consecutive_frames >= self._config.stability_window:
                score = max(score, self._config.stability_high_score)
                stable_pairs.append(pair)
                triggers.append(
                    f"stable_threat:p={pair.person_track_id}:w={pair.weapon_track_id}:"
                    f"frames={pair.consecutive_frames}"
                )
                self._total_high_risks += 1

        # ── Rule 4: Behavioral anomaly boost ──
        for track in tracks:
            behavior = getattr(track, 'behavior', None)
            if behavior and hasattr(behavior, 'has_anomaly') and behavior.has_anomaly:
                score = min(score + self._config.behavioral_boost, 1.0)
                triggers.append(f"behavioral_anomaly:track={getattr(track, 'track_id', '?')}")
                break  # Count once

        # ── Decay stale pairs ──
        stale_keys = []
        for pair_key, pair in self._active_pairs.items():
            if pair_key not in current_pairs:
                # Not seen this frame — reset consecutive count
                if frame_id - pair.last_seen_frame > self._config.decay_frames:
                    stale_keys.append(pair_key)
                else:
                    pair.consecutive_frames = 0

        for key in stale_keys:
            del self._active_pairs[key]

        # Clamp
        score = min(score, 1.0)
        risk_level = _score_to_level(score)
        should_escalate = score >= self._config.escalation_threshold

        if should_escalate:
            self._total_escalations += 1

        # Build track summaries for cloud
        from aegis.edge.event_types import TrackSummary
        summaries = []
        for track in tracks:
            summaries.append(TrackSummary(
                track_id=getattr(track, 'track_id', None),
                class_name=getattr(track, 'class_name', 'unknown'),
                class_id=getattr(track, 'class_id', -1),
                confidence=getattr(track, 'confidence', 0.0),
                bbox=tuple(getattr(track, 'bbox', (0, 0, 0, 0))),
                object_category=getattr(track, 'object_category', 'generic'),
                is_weapon=getattr(track, 'is_weapon', False),
                is_person=getattr(track, 'is_person', False),
                is_animal=getattr(track, 'is_animal', False),
            ))

        active_pairs = list(self._active_pairs.values())

        return ProximityRiskAssessment(
            risk_score=score,
            risk_level=risk_level,
            triggers=triggers,
            threat_pairs=active_pairs,
            should_escalate=should_escalate,
            frame_id=frame_id,
            timestamp=time.time(),
            track_summaries=summaries,
        )

    def get_stats(self) -> dict:
        return {
            "total_frames": self._total_frames,
            "total_escalations": self._total_escalations,
            "total_high_risks": self._total_high_risks,
            "active_pairs": len(self._active_pairs),
            "escalation_rate": round(
                self._total_escalations / max(self._total_frames, 1), 4
            ),
        }

    def reset(self) -> None:
        self._active_pairs.clear()
        self._total_frames = 0
        self._total_escalations = 0
        self._total_high_risks = 0
        logger.info("ProximityRiskEngine reset")

    def __repr__(self) -> str:
        return (
            f"ProximityRiskEngine("
            f"threshold={self._config.escalation_threshold}, "
            f"frames={self._total_frames}, "
            f"pairs={len(self._active_pairs)})"
        )
