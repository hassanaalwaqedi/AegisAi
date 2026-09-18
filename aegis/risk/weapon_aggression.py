"""Evidence-based weapon and person-person threat context.

This layer combines detector, tracker, and motion facts.  It never creates a
weapon detection and deliberately describes risk as possible rather than a
confirmed attack or intent.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from aegis.risk.person_weapon_association import WeaponAssociation


BBox = Tuple[float, float, float, float]


@dataclass(frozen=True)
class WeaponAggressionConfig:
    """Short-window thresholds for explainable threat context."""

    close_person_distance_ratio: float = 0.22
    closing_distance_delta: float = 0.025
    fast_movement_ratio: float = 0.055
    association_confirmation_frames: int = 2
    aggression_confirmation_frames: int = 3
    critical_close_frames: int = 2
    high_confidence_weapon: float = 0.90
    strong_association_score: float = 0.80
    stale_after_frames: int = 12


@dataclass(frozen=True)
class ThreatContext:
    """One explainable, composite threat observation."""

    event_type: str
    armed_person_track_id: str
    risk_level: str
    risk_score: float
    verification_status: str
    reason_codes: List[str]
    explanation: str
    confirmed_frames: int
    armed_person_bbox: List[float]
    weapon_track_id: Optional[str] = None
    weapon_class: Optional[str] = None
    weapon_confidence: Optional[float] = None
    weapon_bbox: Optional[List[float]] = None
    nearby_person_track_id: Optional[str] = None
    nearby_person_bbox: Optional[List[float]] = None
    normalized_person_distance: Optional[float] = None
    distance_decreasing: bool = False
    fast_movement: bool = False
    moving_toward_person: bool = False
    association_type: Optional[str] = None
    association_score: Optional[float] = None
    body_region: Optional[str] = None
    weapon_model_source: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "armed_person_track_id": self.armed_person_track_id,
            "weapon_track_id": self.weapon_track_id,
            "weapon_class": self.weapon_class,
            "weapon_confidence": self.weapon_confidence,
            "nearby_person_track_id": self.nearby_person_track_id,
            "risk_level": self.risk_level,
            "risk_score": round(self.risk_score, 3),
            "verification_status": self.verification_status,
            "reason_codes": list(self.reason_codes),
            "explanation": self.explanation,
            "confirmed_frames": self.confirmed_frames,
            "armed_person_bbox": list(self.armed_person_bbox),
            "weapon_bbox": list(self.weapon_bbox) if self.weapon_bbox else None,
            "nearby_person_bbox": list(self.nearby_person_bbox) if self.nearby_person_bbox else None,
            "normalized_person_distance": (
                round(self.normalized_person_distance, 3)
                if self.normalized_person_distance is not None
                else None
            ),
            "distance_decreasing": self.distance_decreasing,
            "fast_movement": self.fast_movement,
            "moving_toward_person": self.moving_toward_person,
            "association_type": self.association_type,
            "association_score": (
                round(self.association_score, 3)
                if self.association_score is not None
                else None
            ),
            "body_region": self.body_region,
            "weapon_model_source": self.weapon_model_source,
        }


@dataclass
class _PairState:
    previous_distance: Optional[float] = None
    close_frames: int = 0
    last_seen_frame: int = 0


@dataclass(frozen=True)
class _PairObservation:
    normalized_distance: float
    distance_decreasing: bool
    close_frames: int
    fast_movement: bool
    sudden_movement: bool
    moving_toward: bool


class WeaponAggressionRiskLayer:
    """Fuse real weapon associations with short-window person motion context."""

    def __init__(self, config: Optional[WeaponAggressionConfig] = None) -> None:
        self._config = config or WeaponAggressionConfig()
        self._pair_states: Dict[Tuple[str, ...], _PairState] = {}

    def assess(
        self,
        tracks: Iterable[Any],
        associations: Iterable[WeaponAssociation],
        analyses: Mapping[Any, Any],
        frame_id: int,
    ) -> List[ThreatContext]:
        track_list = list(tracks)
        people = [track for track in track_list if self._is_person(track)]
        tracks_by_id = {self._track_id(track): track for track in track_list}
        contexts: List[ThreatContext] = []
        confirmed_armed_person_ids: set[str] = set()

        for association in associations:
            if association.association_type == "none":
                continue
            person = tracks_by_id.get(str(association.person_track_id))
            weapon = tracks_by_id.get(str(association.weapon_track_id))
            if person is None or weapon is None:
                continue

            person_id = self._track_id(person)
            weapon_id = self._track_id(weapon)
            nearby_person = self._nearest_other_person(person, people)
            observation = None
            if nearby_person is not None:
                observation = self._observe_pair(
                    key=("armed", person_id, weapon_id, self._track_id(nearby_person)),
                    actor=person,
                    target=nearby_person,
                    analysis=self._analysis_for(analyses, person),
                    target_analysis=self._analysis_for(analyses, nearby_person),
                    frame_id=frame_id,
                )

            context = self._armed_context(
                person=person,
                weapon=weapon,
                association=association,
                nearby_person=nearby_person if observation and self._is_close(observation) else None,
                observation=observation if observation and self._is_close(observation) else None,
            )
            contexts.append(context)
            if context.verification_status in {"confirmed", "critical"}:
                confirmed_armed_person_ids.add(person_id)

        # When no weapon track exists, close-contact motion may still justify
        # operator review.  Armed pairs are excluded to avoid duplicate event
        # types for the same observation.
        sorted_people = sorted(people, key=self._track_id)
        for index, first in enumerate(sorted_people):
            for second in sorted_people[index + 1 :]:
                if (
                    self._track_id(first) in confirmed_armed_person_ids
                    or self._track_id(second) in confirmed_armed_person_ids
                ):
                    continue
                actor, target = self._motion_order(first, second, analyses)
                pair_ids = tuple(sorted((self._track_id(first), self._track_id(second))))
                observation = self._observe_pair(
                    key=("people", *pair_ids),
                    actor=actor,
                    target=target,
                    analysis=self._analysis_for(analyses, actor),
                    target_analysis=self._analysis_for(analyses, target),
                    frame_id=frame_id,
                )
                if not self._is_close(observation):
                    continue
                aggressive_motion = observation.fast_movement and (
                    observation.moving_toward
                    or observation.distance_decreasing
                    or observation.sudden_movement
                )
                if not aggressive_motion:
                    continue
                contexts.append(self._person_context(actor, target, observation))

        self._discard_stale(frame_id)
        return contexts

    def reset(self) -> None:
        self._pair_states.clear()

    def _armed_context(
        self,
        *,
        person: Any,
        weapon: Any,
        association: WeaponAssociation,
        nearby_person: Optional[Any],
        observation: Optional[_PairObservation],
    ) -> ThreatContext:
        config = self._config
        high_confidence = (
            association.weapon_confidence >= config.high_confidence_weapon
            and association.association_score >= config.strong_association_score
            and association.association_type in {"contained", "overlap"}
        )
        association_confirmed = (
            association.stable_frames >= config.association_confirmation_frames
        ) or high_confidence

        risk_level = "HIGH" if association_confirmed else "MEDIUM"
        risk_score = 0.66 if association_confirmed else 0.45
        verification_status = "confirmed" if association_confirmed else "candidate"
        confirmed_frames = max(association.stable_frames, 1)
        reasons = {
            "WEAPON_MODEL_DETECTION",
            "WEAPON_LIKE_OBJECT_DETECTION",
            "WEAPON_PERSON_ASSOCIATION",
            "POSSIBLE_ARMED_THREAT",
            "OPERATOR_REVIEW_REQUIRED",
        }
        if association.body_region == "upper_body":
            reasons.add("WEAPON_NEAR_UPPER_BODY_REGION")
        if high_confidence:
            reasons.add("HIGH_CONFIDENCE_WEAPON_ASSOCIATION")
        if association.stable_frames >= config.association_confirmation_frames:
            reasons.add("TEMPORALLY_CONFIRMED_WEAPON_ASSOCIATION")

        if nearby_person is not None and observation is not None:
            reasons.add("SECOND_PERSON_WITHIN_CLOSE_RANGE")
            confirmed_frames = max(confirmed_frames, observation.close_frames)
            if observation.close_frames >= config.critical_close_frames:
                reasons.add("CLOSE_CONTACT_REPEATED")
            if observation.distance_decreasing:
                reasons.add("DISTANCE_DECREASING")
            if observation.fast_movement:
                reasons.add("FAST_MOVEMENT")
            if observation.moving_toward:
                reasons.add("MOVEMENT_TOWARD_PERSON")

            aggressive_combination = association_confirmed and observation.close_frames >= config.critical_close_frames and observation.fast_movement and (
                observation.moving_toward
                or observation.distance_decreasing
                or observation.sudden_movement
            )
            if aggressive_combination:
                risk_level = "CRITICAL"
                risk_score = 0.90
                verification_status = "critical"
                reasons.add("CRITICAL_WEAPON_AGGRESSION_COMBINATION")
            elif association_confirmed:
                risk_score = max(risk_score, 0.72)

        weapon_name = str(association.weapon_class or "weapon").replace("_", " ")
        person_id = self._track_id(person)
        explanation_parts = [
            f"Possible armed threat: possible {weapon_name} detected near person track #{person_id}.",
        ]
        if association.body_region == "upper_body":
            explanation_parts.append("The object is close to the tracked upper-body region.")
        if nearby_person is not None and observation is not None:
            explanation_parts.append(
                f"Second person track #{self._track_id(nearby_person)} is within close range."
            )
            if observation.distance_decreasing:
                explanation_parts.append("Distance between the people is decreasing.")
            if observation.fast_movement and observation.moving_toward:
                explanation_parts.append("Fast movement toward another person was observed.")
            elif observation.fast_movement:
                explanation_parts.append("Sudden or fast movement was observed at close range.")
        explanation_parts.extend(
            [
                "Risk increased due to weapon-person association.",
                "Operator review required.",
            ]
        )

        return ThreatContext(
            event_type="possible_armed_threat",
            armed_person_track_id=person_id,
            weapon_track_id=self._track_id(weapon),
            weapon_class=str(association.weapon_class),
            weapon_confidence=association.weapon_confidence,
            nearby_person_track_id=self._track_id(nearby_person) if nearby_person else None,
            risk_level=risk_level,
            risk_score=risk_score,
            verification_status=verification_status,
            reason_codes=sorted(reasons),
            explanation=" ".join(explanation_parts),
            confirmed_frames=confirmed_frames,
            armed_person_bbox=list(self._bbox(person)),
            weapon_bbox=list(self._bbox(weapon)),
            nearby_person_bbox=list(self._bbox(nearby_person)) if nearby_person else None,
            normalized_person_distance=observation.normalized_distance if observation else None,
            distance_decreasing=observation.distance_decreasing if observation else False,
            fast_movement=observation.fast_movement if observation else False,
            moving_toward_person=observation.moving_toward if observation else False,
            association_type=association.association_type,
            association_score=association.association_score,
            body_region=association.body_region,
            weapon_model_source=association.weapon_model_source,
        )

    def _person_context(
        self,
        actor: Any,
        target: Any,
        observation: _PairObservation,
    ) -> ThreatContext:
        confirmed = observation.close_frames >= self._config.aggression_confirmation_frames
        risk_level = "HIGH" if confirmed else "MEDIUM"
        risk_score = 0.60 if confirmed else 0.42
        verification_status = "confirmed" if confirmed else "candidate"
        reasons = {
            "POSSIBLE_ASSAULT",
            "PERSON_PERSON_CLOSE_CONTACT",
            "FAST_MOVEMENT",
            "OPERATOR_REVIEW_REQUIRED",
        }
        if observation.close_frames >= 2:
            reasons.add("CLOSE_CONTACT_REPEATED")
        if observation.distance_decreasing:
            reasons.add("DISTANCE_DECREASING")
        if observation.moving_toward:
            reasons.add("MOVEMENT_TOWARD_PERSON")
        if confirmed:
            reasons.add("CONFIRMED_AGGRESSION_PATTERN")

        actor_id = self._track_id(actor)
        target_id = self._track_id(target)
        details = [
            f"Possible assault pattern involving person tracks #{actor_id} and #{target_id}.",
        ]
        if observation.close_frames >= 2:
            details.append("Repeated close-contact movement was observed.")
        else:
            details.append("Close-contact movement was observed.")
        if observation.moving_toward:
            details.append("Fast movement toward another person was observed.")
        elif observation.fast_movement:
            details.append("Sudden or fast movement was observed at close range.")
        details.append("Operator review required.")

        return ThreatContext(
            event_type="possible_assault",
            armed_person_track_id=actor_id,
            nearby_person_track_id=target_id,
            risk_level=risk_level,
            risk_score=risk_score,
            verification_status=verification_status,
            reason_codes=sorted(reasons),
            explanation=" ".join(details),
            confirmed_frames=observation.close_frames,
            armed_person_bbox=list(self._bbox(actor)),
            nearby_person_bbox=list(self._bbox(target)),
            normalized_person_distance=observation.normalized_distance,
            distance_decreasing=observation.distance_decreasing,
            fast_movement=observation.fast_movement,
            moving_toward_person=observation.moving_toward,
        )

    def _observe_pair(
        self,
        *,
        key: Tuple[str, ...],
        actor: Any,
        target: Any,
        analysis: Optional[Any],
        target_analysis: Optional[Any],
        frame_id: int,
    ) -> _PairObservation:
        normalized_distance = self._normalized_gap(self._bbox(actor), self._bbox(target))
        state = self._pair_states.setdefault(key, _PairState())
        if state.last_seen_frame and state.last_seen_frame != frame_id - 1:
            state.previous_distance = None
            state.close_frames = 0
        distance_decreasing = (
            state.previous_distance is not None
            and state.previous_distance - normalized_distance >= self._config.closing_distance_delta
        )
        is_close = normalized_distance <= self._config.close_person_distance_ratio
        state.close_frames = state.close_frames + 1 if is_close else 0
        state.previous_distance = normalized_distance
        state.last_seen_frame = frame_id

        fast_movement, sudden_movement, velocity = self._motion_facts(actor, analysis)
        target_fast, target_sudden, target_velocity = self._motion_facts(target, target_analysis)
        relative_velocity = (
            velocity[0] - target_velocity[0],
            velocity[1] - target_velocity[1],
        )
        moving_toward = self._moving_toward(
            self._bbox(actor),
            self._bbox(target),
            relative_velocity,
        )
        return _PairObservation(
            normalized_distance=normalized_distance,
            distance_decreasing=distance_decreasing,
            close_frames=state.close_frames,
            fast_movement=fast_movement or target_fast,
            sudden_movement=sudden_movement or target_sudden,
            moving_toward=moving_toward,
        )

    def _motion_facts(
        self,
        track: Any,
        analysis: Optional[Any],
    ) -> Tuple[bool, bool, Tuple[float, float]]:
        if analysis is None:
            return False, False, (0.0, 0.0)
        motion = getattr(analysis, "motion", None)
        behavior = getattr(analysis, "behavior", None)
        if motion is None:
            return False, False, (0.0, 0.0)
        speed = max(
            float(getattr(motion, "speed", 0.0) or 0.0),
            float(getattr(motion, "speed_smoothed", 0.0) or 0.0),
        )
        speed_ratio = speed / max(self._diagonal(self._bbox(track)), 1.0)
        acceleration = abs(float(getattr(motion, "acceleration", 0.0) or 0.0))
        acceleration_ratio = acceleration / max(self._diagonal(self._bbox(track)), 1.0)
        sudden = bool(
            getattr(behavior, "sudden_speed_change", False)
            or getattr(behavior, "is_erratic", False)
            or acceleration_ratio >= self._config.fast_movement_ratio
        )
        running = bool(getattr(behavior, "is_running", False))
        velocity = getattr(motion, "velocity", (0.0, 0.0))
        return speed_ratio >= self._config.fast_movement_ratio or sudden or running, sudden, (
            float(velocity[0]),
            float(velocity[1]),
        )

    def _motion_order(
        self,
        first: Any,
        second: Any,
        analyses: Mapping[Any, Any],
    ) -> Tuple[Any, Any]:
        first_strength = self._motion_strength(first, self._analysis_for(analyses, first))
        second_strength = self._motion_strength(second, self._analysis_for(analyses, second))
        return (second, first) if second_strength > first_strength else (first, second)

    def _motion_strength(self, track: Any, analysis: Optional[Any]) -> float:
        if analysis is None:
            return 0.0
        motion = getattr(analysis, "motion", None)
        if motion is None:
            return 0.0
        return max(
            float(getattr(motion, "speed", 0.0) or 0.0),
            float(getattr(motion, "speed_smoothed", 0.0) or 0.0),
        ) / max(self._diagonal(self._bbox(track)), 1.0)

    def _nearest_other_person(self, person: Any, people: List[Any]) -> Optional[Any]:
        candidates = [item for item in people if self._track_id(item) != self._track_id(person)]
        if not candidates:
            return None
        return min(candidates, key=lambda item: self._normalized_gap(self._bbox(person), self._bbox(item)))

    def _discard_stale(self, frame_id: int) -> None:
        cutoff = frame_id - self._config.stale_after_frames
        for key in list(self._pair_states):
            if self._pair_states[key].last_seen_frame < cutoff:
                del self._pair_states[key]

    def _is_close(self, observation: _PairObservation) -> bool:
        return observation.normalized_distance <= self._config.close_person_distance_ratio

    @staticmethod
    def _analysis_for(analyses: Mapping[Any, Any], track: Any) -> Optional[Any]:
        track_id = getattr(track, "track_id", None)
        return analyses.get(track_id) or analyses.get(str(track_id))

    @staticmethod
    def _is_person(track: Any) -> bool:
        return bool(getattr(track, "is_person", False)) or str(getattr(track, "class_name", "")).lower() == "person"

    @staticmethod
    def _track_id(track: Any) -> str:
        return str(getattr(track, "track_id", ""))

    @staticmethod
    def _bbox(track: Any) -> BBox:
        bbox = getattr(track, "bbox", (0.0, 0.0, 0.0, 0.0))
        return float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])

    @staticmethod
    def _center(bbox: BBox) -> Tuple[float, float]:
        return (bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0

    @staticmethod
    def _diagonal(bbox: BBox) -> float:
        return math.hypot(max(bbox[2] - bbox[0], 0.0), max(bbox[3] - bbox[1], 0.0))

    @classmethod
    def _normalized_gap(cls, first: BBox, second: BBox) -> float:
        dx = max(first[0] - second[2], second[0] - first[2], 0.0)
        dy = max(first[1] - second[3], second[1] - first[3], 0.0)
        scale = max((cls._diagonal(first) + cls._diagonal(second)) / 2.0, 1.0)
        return math.hypot(dx, dy) / scale

    @classmethod
    def _moving_toward(
        cls,
        actor_bbox: BBox,
        target_bbox: BBox,
        velocity: Tuple[float, float],
    ) -> bool:
        speed = math.hypot(velocity[0], velocity[1])
        if speed <= 0.0:
            return False
        actor_center = cls._center(actor_bbox)
        target_center = cls._center(target_bbox)
        direction = (target_center[0] - actor_center[0], target_center[1] - actor_center[1])
        distance = math.hypot(direction[0], direction[1])
        if distance <= 0.0:
            return False
        cosine = (velocity[0] * direction[0] + velocity[1] * direction[1]) / (speed * distance)
        return cosine >= 0.45
