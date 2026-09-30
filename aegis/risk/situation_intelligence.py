"""Explainable, temporal situation assessment built on existing Aegis risk inputs.

This module deliberately evaluates observable evidence only.  It does not infer
intent, identity, or future actions, and it adds no model inference.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from math import hypot
from typing import Any, Callable, Deque, Optional


@dataclass(frozen=True)
class SituationRiskConfig:
    medium_threshold: float = 0.25
    high_threshold: float = 0.50
    critical_threshold: float = 0.75
    decay_per_frame: float = 0.12
    rapid_approach_speed: float = 12.0
    close_distance_ratio: float = 1.1
    trend_window: int = 4
    threat_weights: dict[str, float] = field(default_factory=lambda: {
        "handgun": 0.25, "long_gun": 0.30, "blade": 0.18, "blunt_weapon": 0.14,
    })


@dataclass
class SituationEvidence:
    category: str
    signal: str
    confidence: float
    source: str
    subject_track_id: Optional[str] = None
    target_track_id: Optional[str] = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category, "signal": self.signal,
            "confidence": round(self.confidence, 3), "source": self.source,
            "subject_track_id": self.subject_track_id,
            "target_track_id": self.target_track_id, "details": self.details,
        }


@dataclass
class RiskContribution:
    reason_code: str
    value: float
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {"reason_code": self.reason_code, "value": round(self.value, 3), "description": self.description}


@dataclass
class SituationAssessment:
    camera_id: str
    primary_track_id: Optional[str]
    related_track_ids: list[str]
    risk_score: float
    risk_level: str
    risk_trend: str
    current: bool
    peak_risk_score: float
    peak_risk_level: str
    reason_codes: list[str]
    contributions: list[RiskContribution]
    evidence: list[SituationEvidence]
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "camera_id": self.camera_id, "primary_track_id": self.primary_track_id,
            "related_track_ids": self.related_track_ids, "risk_score": round(self.risk_score, 3),
            "risk_level": self.risk_level, "risk_trend": self.risk_trend, "current": self.current,
            "peak_risk_score": round(self.peak_risk_score, 3), "peak_risk_level": self.peak_risk_level,
            "reason_codes": self.reason_codes, "contributions": [item.to_dict() for item in self.contributions],
            "evidence": [item.to_dict() for item in self.evidence], "explanation": self.explanation,
        }


@dataclass
class _SubjectState:
    score: float = 0.0
    peak_score: float = 0.0
    scores: Deque[float] = field(default_factory=lambda: deque(maxlen=4))
    positions: Deque[tuple[float, float]] = field(default_factory=lambda: deque(maxlen=4))


class SituationIntelligence:
    """Centralized Phase 6 evaluator used by the established risk pipeline."""

    def __init__(self, config: Optional[SituationRiskConfig] = None):
        self.config = config or SituationRiskConfig()
        self._states: dict[tuple[str, str], _SubjectState] = {}

    def assess(
        self,
        *,
        camera_id: str,
        tracks: list[Any],
        threat_evidence: list[dict[str, Any]],
        analyses: Optional[dict[Any, Any]] = None,
        base_risks: Optional[dict[str, float]] = None,
        zone_for_track: Optional[Callable[[Any], Any]] = None,
    ) -> list[SituationAssessment]:
        analyses, base_risks = analyses or {}, base_risks or {}
        persons = [track for track in tracks if self._is_person(track)]
        person_by_id = {self._track_id(track): track for track in persons}
        for track_id, track in person_by_id.items():
            self._state(camera_id, track_id).positions.append(self._center(track))

        associated: dict[str, list[dict[str, Any]]] = defaultdict(list)
        unassociated: list[dict[str, Any]] = []
        for item in threat_evidence:
            track_id = item.get("track_id")
            if track_id and str(track_id) in person_by_id:
                associated[str(track_id)].append(item)
            else:
                unassociated.append(item)

        assessments = [
            self._assess_subject(camera_id, track, associated.get(track_id, []), persons, analyses.get(getattr(track, "track_id", track_id)),
                                 float(base_risks.get(track_id, 0.0) or 0.0), zone_for_track(track) if zone_for_track else None)
            for track_id, track in person_by_id.items()
        ]
        if unassociated:
            assessments.append(self._assess_scene(camera_id, unassociated))
        self.cleanup(camera_id, set(person_by_id) | ({"__scene__"} if unassociated else set()))
        return assessments

    def cleanup(self, camera_id: str, active_track_ids: set[str]) -> None:
        """Bound per-camera temporal state to currently active tracked subjects."""
        active = {str(track_id) for track_id in active_track_ids}
        for key in list(self._states):
            if key[0] == camera_id and key[1] not in active:
                self._states.pop(key, None)

    def reset(self, camera_id: Optional[str] = None) -> None:
        if camera_id is None:
            self._states.clear()
            return
        self.cleanup(camera_id, set())

    def _assess_subject(self, camera_id: str, track: Any, threats: list[dict[str, Any]], persons: list[Any], analysis: Any,
                        base_risk: float, zone_context: Any) -> SituationAssessment:
        track_id = self._track_id(track)
        evidence: list[SituationEvidence] = []
        contributions: list[RiskContribution] = []
        related: list[str] = []
        if base_risk > 0.01:
            # Preserve the established RiskEngine/legacy weapon layer as an
            # input to the unified decision path; do not silently downgrade it.
            self._add(contributions, "EXISTING_BEHAVIOR_RISK", min(base_risk, 1.0), "Existing behavioral risk contribution")

        for threat in threats:
            family = str(threat.get("normalized_threat_class", "")).lower()
            persistent = threat.get("persistence_state") == "persistent"
            association = str(threat.get("association_state", "unassociated"))
            weight = self.config.threat_weights.get(family, 0.12)
            if not persistent:
                weight *= 0.45
            self._add(contributions, f"{'PERSISTENT_' if persistent else ''}{family.upper()}_CANDIDATE", weight,
                      f"{family.replace('_', ' ')} candidate observed")
            evidence.append(SituationEvidence("THREAT", f"{family}_candidate", float(threat.get("detector_confidence", 0.0) or 0.0),
                                             "threat_fusion", track_id, details={"observations": threat.get("observations", 0), "persistence": threat.get("persistence_state")}))
            if association == "probable":
                self._add(contributions, "PROBABLE_PERSON_THREAT_ASSOCIATION", 0.10, "Threat candidate is probably associated with this track")
            elif association == "ambiguous":
                self._add(contributions, "AMBIGUOUS_PERSON_THREAT_ASSOCIATION", 0.03, "Threat candidate association remains ambiguous")
            if persistent and int(threat.get("observations", 0) or 0) >= 2:
                self._add(contributions, "MULTI_SIGNAL_PERSISTENCE", 0.06, "Threat evidence persisted across inference cycles")

        behavior = getattr(analysis, "behavior", analysis)
        motion = getattr(analysis, "motion", None)
        if bool(getattr(behavior, "is_running", False)):
            self._add(contributions, "RAPID_MOVEMENT", 0.06, "Observed rapid movement")
            evidence.append(SituationEvidence("BEHAVIOR", "rapid_movement", 1.0, "behavior_analyzer", track_id))
        if bool(getattr(behavior, "has_anomaly", False)) or bool(getattr(behavior, "is_erratic", False)):
            self._add(contributions, "ABNORMAL_MOVEMENT", 0.08, "Observed anomalous or erratic movement")
        if bool(getattr(behavior, "is_loitering", False)):
            self._add(contributions, "LOITERING", 0.04, "Observed prolonged stationary behavior")

        target, rapid = self._approach_target(camera_id, track, persons, motion)
        if target is not None:
            target_id = self._track_id(target)
            related.append(target_id)
            if rapid:
                self._add(contributions, "RAPID_APPROACH_TO_PERSON", 0.17, "Distance to another tracked person is decreasing during rapid movement")
                evidence.append(SituationEvidence("INTERACTION", "rapid_approach", 1.0, "trajectory", track_id, target_id))
            else:
                self._add(contributions, "CLOSE_INTERACTION", 0.03, "Close interaction with another tracked person")

        zone_type = str(getattr(getattr(zone_context, "zone_type", None), "value", "")).upper()
        zone_name = str(getattr(zone_context, "zone_name", ""))
        if zone_type in {"RESTRICTED", "HIGH_RISK"}:
            self._add(contributions, "RESTRICTED_ZONE" if zone_type == "RESTRICTED" else "SENSITIVE_ZONE", 0.10 if zone_type == "RESTRICTED" else 0.06,
                      f"Observed in {zone_name or zone_type.lower()} zone")
            evidence.append(SituationEvidence("CONTEXT", zone_type.lower(), 1.0, "zone_manager", track_id))
        if "authorized_tool" in zone_name.lower() and threats:
            self._add(contributions, "AUTHORIZED_TOOL_AREA_CONTEXT", -0.08, "Authorized-tool area moderates but does not remove threat evidence")

        codes = {item.reason_code for item in contributions}
        if threats and "RAPID_APPROACH_TO_PERSON" in codes and "PROBABLE_PERSON_THREAT_ASSOCIATION" in codes:
            self._add(contributions, "THREAT_APPROACH_COMBINATION", 0.13, "Persistent associated threat evidence and rapid approach co-occur")
        return self._finalize(camera_id, track_id, related, contributions, evidence)

    def _assess_scene(self, camera_id: str, threats: list[dict[str, Any]]) -> SituationAssessment:
        contributions: list[RiskContribution] = []
        evidence: list[SituationEvidence] = []
        for threat in threats:
            family = str(threat.get("normalized_threat_class", "unknown")).upper()
            value = 0.12 if threat.get("persistence_state") == "persistent" else 0.05
            self._add(contributions, f"UNASSOCIATED_{family}_CANDIDATE", value, "Threat candidate has no reliable person association")
            evidence.append(SituationEvidence("THREAT", "unassociated_threat", float(threat.get("detector_confidence", 0.0) or 0.0), "threat_fusion", details={"class": family.lower()}))
        return self._finalize(camera_id, "__scene__", [], contributions, evidence, scene=True)

    def _finalize(self, camera_id: str, state_id: str, related: list[str], contributions: list[RiskContribution], evidence: list[SituationEvidence], scene: bool = False) -> SituationAssessment:
        raw = max(0.0, min(sum(item.value for item in contributions), 1.0))
        state = self._state(camera_id, state_id)
        score = raw if raw >= state.score else max(raw, state.score - self.config.decay_per_frame)
        state.score, state.peak_score = score, max(state.peak_score, score)
        state.scores.append(score)
        trend = self._trend(state.scores)
        level, peak_level = self._level(score), self._level(state.peak_score)
        ordered = sorted(contributions, key=lambda item: abs(item.value), reverse=True)
        positive = [item for item in ordered if item.value > 0]
        if positive:
            summary = "; ".join(item.description for item in positive[:3])
            explanation = f"{level.title()} situation assessment: {summary}."
        else:
            explanation = "Low situation assessment: no elevated observable signals."
        return SituationAssessment(camera_id, None if scene else state_id, sorted(set(related)), score, level, trend, raw > 0.01,
                                   state.peak_score, peak_level, [item.reason_code for item in positive], ordered, evidence, explanation)

    def _approach_target(self, camera_id: str, track: Any, persons: list[Any], motion: Any) -> tuple[Optional[Any], bool]:
        track_id, center = self._track_id(track), self._center(track)
        candidates = [(hypot(center[0] - self._center(other)[0], center[1] - self._center(other)[1]), other) for other in persons if self._track_id(other) != track_id]
        if not candidates:
            return None, False
        distance, target = min(candidates, key=lambda item: item[0])
        own_state, target_state = self._state(camera_id, track_id), self._state(camera_id, self._track_id(target))
        if len(own_state.positions) < 2 or len(target_state.positions) < 2:
            return (target, False) if distance <= self._scale(track) * self.config.close_distance_ratio else (None, False)
        previous = hypot(own_state.positions[-2][0] - target_state.positions[-2][0], own_state.positions[-2][1] - target_state.positions[-2][1])
        speed = float(getattr(motion, "speed_smoothed", getattr(motion, "speed", 0.0)) or 0.0)
        return target, bool(previous - distance > 1.0 and speed >= self.config.rapid_approach_speed)

    def _state(self, camera_id: str, track_id: str) -> _SubjectState:
        return self._states.setdefault((camera_id, str(track_id)), _SubjectState(scores=deque(maxlen=self.config.trend_window), positions=deque(maxlen=4)))

    @staticmethod
    def _add(items: list[RiskContribution], code: str, value: float, description: str) -> None:
        items.append(RiskContribution(code, value, description))

    def _level(self, score: float) -> str:
        if score >= self.config.critical_threshold: return "CRITICAL"
        if score >= self.config.high_threshold: return "HIGH"
        if score >= self.config.medium_threshold: return "MEDIUM"
        return "LOW"

    @staticmethod
    def _trend(scores: Deque[float]) -> str:
        if len(scores) < 3: return "stable"
        delta = scores[-1] - scores[0]
        return "escalating" if delta >= 0.08 else "de_escalating" if delta <= -0.08 else "stable"

    @staticmethod
    def _track_id(track: Any) -> str: return str(getattr(track, "track_id", ""))
    @staticmethod
    def _is_person(track: Any) -> bool: return bool(getattr(track, "is_person", False)) or str(getattr(track, "class_name", "")).lower() == "person"
    @staticmethod
    def _center(track: Any) -> tuple[float, float]:
        x1, y1, x2, y2 = getattr(track, "bbox", (0, 0, 0, 0)); return ((float(x1)+float(x2))/2, (float(y1)+float(y2))/2)
    @staticmethod
    def _scale(track: Any) -> float:
        x1, y1, x2, y2 = getattr(track, "bbox", (0, 0, 0, 0)); return max(hypot(float(x2)-float(x1), float(y2)-float(y1)), 1.0)
