"""Evidence-based natural-language search over AegisAI live intelligence.

This is deliberately separate from Grounding DINO.  Grounding DINO answers
open-vocabulary *visual* questions and can be expensive to run.  The query
engine answers operator questions over evidence the pipeline has already
verified: live tracks, confirmed events, risk reasons, associations, and crowd
metrics.  It provides instant results without inventing a visual attribute.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
import time
from typing import Any, Iterable, Mapping, Sequence


_ARABIC_DIACRITICS = re.compile(r"[\u064b-\u065f\u0670]")
_NON_WORD = re.compile(r"[^\w\s]", re.UNICODE)


def _normalise(value: object) -> str:
    """Normalise English and Arabic evidence into a comparison-safe string."""
    text = str(value or "").casefold()
    text = _ARABIC_DIACRITICS.sub("", text)
    text = text.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه", "_": " "}))
    return " ".join(_NON_WORD.sub(" ", text).split())


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    # Substring matching turns the "car" in "carrying" into a vehicle.  A
    # token boundary keeps the intent parser conservative and explainable.
    return any(re.search(rf"(?<!\w){re.escape(_normalise(term))}(?!\w)", text) for term in terms)


CONCEPT_TERMS = {
    "person": {"person", "people", "human", "pedestrian", "individual", "شخص", "اشخاص", "انسان"},
    "weapon": {"weapon", "weapons", "gun", "guns", "firearm", "pistol", "rifle", "knife", "knives", "سلاح", "اسلحه", "مسدس", "بندقيه", "سكين"},
    "vehicle": {"vehicle", "car", "truck", "bus", "motorcycle", "مركبه", "سياره", "شاحنه", "حافله"},
    "loitering": {"loiter", "loitering", "lingering", "idle", "stationary", "تسكع", "تجول", "ثابت"},
    "restricted": {"restricted", "unauthorized", "intrusion", "forbidden", "no entry", "zone intrusion", "محظور", "ممنوع", "تسلل", "غير مصرح"},
    "crowd": {"crowd", "crowded", "density", "congestion", "ازدحام", "حشد", "كثافه"},
    "running": {"running", "run", "sprinting", "هرب", "يركض", "جري"},
    "high_risk": {"risk", "risky", "suspicious", "danger", "dangerous", "high risk", "critical", "خطر", "مشبوه", "عالي"},
}

_QUERY_STOP_WORDS = {
    "find", "show", "detect", "identify", "search", "list", "where", "with", "near", "from", "that",
    "the", "and", "for", "all", "any", "a", "an", "of", "in", "on", "to", "is", "are",
    "ابحث", "اعرض", "اكتشف", "حدد", "كل", "من", "في", "مع", "عن", "الى", "هذا", "هذه",
}


@dataclass(frozen=True)
class SemanticQueryExecution:
    """A complete, serialisable result for one live semantic query."""

    prompt: str
    results: list[dict[str, Any]]
    evaluated_tracks: int
    evaluated_events: int
    execution_ms: float
    updated_at: str


class SemanticQueryEngine:
    """Evaluate a small, transparent natural-language query against live data."""

    mode = "live_evidence"

    def search(
        self,
        prompt: str,
        tracks: Sequence[Mapping[str, Any]],
        events: Sequence[Mapping[str, Any]],
        statistics: Mapping[str, Any] | None = None,
        limit: int = 50,
    ) -> SemanticQueryExecution:
        started_at = time.perf_counter()
        normalised_prompt = _normalise(prompt)
        concepts = {name for name, terms in CONCEPT_TERMS.items() if _contains_any(normalised_prompt, terms)}

        matches = [
            result
            for result in (self._match_track(track, normalised_prompt, concepts) for track in tracks)
            if result is not None
        ]

        # Events remain queryable after a live track has expired.  Avoid showing
        # duplicate evidence for a currently active track.
        active_track_ids = {str(track.get("track_id")) for track in tracks}
        for event in reversed(events):
            track_id = event.get("track_id")
            if track_id is not None and str(track_id) in active_track_ids:
                continue
            result = self._match_event(event, normalised_prompt, concepts)
            if result is not None:
                matches.append(result)

        crowd_result = self._match_crowd(statistics or {}, normalised_prompt, concepts)
        if crowd_result is not None:
            matches.append(crowd_result)

        matches.sort(key=lambda item: (item["semantic_confidence"], item["risk_score"]), reverse=True)
        elapsed = (time.perf_counter() - started_at) * 1000
        return SemanticQueryExecution(
            prompt=prompt,
            results=matches[:limit],
            evaluated_tracks=len(tracks),
            evaluated_events=len(events),
            execution_ms=round(elapsed, 2),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

    def _match_track(self, track: Mapping[str, Any], prompt: str, concepts: set[str]) -> dict[str, Any] | None:
        evidence = self._track_evidence(track)
        matched = self._matched_concepts(track, evidence, concepts)
        if not self._is_match(prompt, concepts, evidence, matched):
            return None

        return self._result(
            source="track",
            identifier=track.get("track_id"),
            base_class=track.get("class_name", "unknown"),
            risk_score=track.get("risk_score"),
            camera_id=track.get("camera_id"),
            zone=track.get("zone"),
            confidence=track.get("confidence"),
            verification_status=track.get("verification_status"),
            timestamp=track.get("last_seen") or track.get("last_updated"),
            behaviors=track.get("behaviors") or track.get("behavior_labels") or [],
            prompt=prompt,
            matched=matched,
            evidence=self._evidence_lines(track, matched),
        )

    def _match_event(self, event: Mapping[str, Any], prompt: str, concepts: set[str]) -> dict[str, Any] | None:
        evidence = self._track_evidence(event)
        matched = self._matched_concepts(event, evidence, concepts)
        if not self._is_match(prompt, concepts, evidence, matched):
            return None

        identifier = event.get("track_id") or event.get("event_id") or event.get("id")
        return self._result(
            source="event",
            identifier=identifier,
            base_class=event.get("class_name") or event.get("object_class") or event.get("object_type") or "event",
            risk_score=event.get("risk_score") or event.get("edge_risk_score"),
            camera_id=event.get("camera_id"),
            zone=event.get("zone"),
            confidence=event.get("confidence"),
            verification_status=event.get("verification_status"),
            timestamp=event.get("timestamp"),
            behaviors=event.get("behavior_labels") or event.get("behaviors") or [],
            prompt=prompt,
            matched=matched,
            evidence=self._evidence_lines(event, matched),
        )

    def _match_crowd(self, statistics: Mapping[str, Any], prompt: str, concepts: set[str]) -> dict[str, Any] | None:
        if "crowd" not in concepts:
            return None
        crowd_detected = bool(statistics.get("crowd_detected"))
        max_density = self._number(statistics.get("max_density"))
        if not crowd_detected and max_density <= 0:
            return None

        risk_distribution = statistics.get("risk_distribution") or {}
        elevated = sum(self._number(risk_distribution.get(level)) for level in ("MEDIUM", "HIGH", "CRITICAL"))
        return {
            "track_id": "crowd-summary",
            "source": "statistics",
            "base_class": "crowd",
            "semantic_label": "crowd density evidence",
            "semantic_confidence": 1.0,
            "risk_score": min(1.0, 0.35 + min(max_density, 10) / 20 + (0.15 if elevated else 0.0)),
            "matched_phrase": prompt,
            "behaviors": ["crowd_detected"] if crowd_detected else [],
            "camera_id": None,
            "zone": None,
            "confidence": None,
            "verification_status": "measured",
            "timestamp": statistics.get("timestamp"),
            "evidence": [f"Crowd detected: {'yes' if crowd_detected else 'no'}", f"Maximum density: {max_density:g}"],
        }

    def _is_match(self, prompt: str, concepts: set[str], evidence: str, matched: set[str]) -> bool:
        if concepts:
            # A phrase such as "people carrying weapons" must have evidence for
            # both concepts, not merely a nearby person or weapon detection.
            required = concepts - {"high_risk"}
            if required and not required.issubset(matched):
                return False
            if "high_risk" in concepts and "high_risk" not in matched:
                return False
            return True

        # For unknown concepts, perform a conservative lexical evidence match.
        keywords = [word for word in prompt.split() if len(word) >= 3 and word not in _QUERY_STOP_WORDS]
        return bool(keywords) and all(re.search(rf"(?<!\w){re.escape(word)}(?!\w)", evidence) for word in keywords)

    def _matched_concepts(self, record: Mapping[str, Any], evidence: str, concepts: set[str]) -> set[str]:
        matched: set[str] = set()
        is_person = bool(record.get("is_person")) or _contains_any(evidence, CONCEPT_TERMS["person"])
        has_weapon_association = bool(record.get("is_weapon")) or bool(record.get("weapon_class")) or bool(record.get("weapon_track_id"))
        has_weapon_association = has_weapon_association or _contains_any(evidence, CONCEPT_TERMS["weapon"])

        if "person" in concepts and is_person:
            matched.add("person")
        if "weapon" in concepts and has_weapon_association:
            matched.add("weapon")
        if "vehicle" in concepts and (bool(record.get("is_vehicle")) or _contains_any(evidence, CONCEPT_TERMS["vehicle"])):
            matched.add("vehicle")
        if "loitering" in concepts and _contains_any(evidence, CONCEPT_TERMS["loitering"]):
            matched.add("loitering")
        if "restricted" in concepts and _contains_any(evidence, CONCEPT_TERMS["restricted"]):
            matched.add("restricted")
        if "running" in concepts and _contains_any(evidence, CONCEPT_TERMS["running"]):
            matched.add("running")
        risk_level = _normalise(record.get("risk_level") or record.get("severity") or "")
        if "high_risk" in concepts and (
            self._number(record.get("risk_score")) >= 0.5
            or risk_level in {"medium", "high", "critical", "candidate medium"}
        ):
            matched.add("high_risk")
        return matched

    def _track_evidence(self, record: Mapping[str, Any]) -> str:
        values: list[object] = [
            record.get("class_name"), record.get("object_class"), record.get("object_type"), record.get("object_category"),
            record.get("zone"), record.get("camera_id"), record.get("risk_level"), record.get("risk_explanation"),
            record.get("description"), record.get("explanation"), record.get("reason"), record.get("movement_state"),
            record.get("weapon_class"), record.get("association_type"), record.get("verification_status"),
        ]
        for key in ("behaviors", "behavior_labels", "detected_classes", "reason_codes", "risk_factors", "triggers", "detected_objects", "evidence_objects"):
            values.extend(record.get(key) or [])
        return _normalise(" ".join(str(value) for value in values if value is not None))

    def _evidence_lines(self, record: Mapping[str, Any], matched: set[str]) -> list[str]:
        lines = [f"Matched concepts: {', '.join(sorted(matched)) or 'text evidence'}"]
        if record.get("risk_level"):
            lines.append(f"Risk level: {record['risk_level']}")
        if record.get("reason_codes"):
            lines.append(f"Reasons: {', '.join(map(str, record['reason_codes'][:3]))}")
        if record.get("association_type"):
            lines.append(f"Association: {record['association_type']}")
        if record.get("risk_explanation") or record.get("explanation"):
            lines.append(str(record.get("risk_explanation") or record.get("explanation")))
        return lines

    def _result(
        self,
        *,
        source: str,
        identifier: object,
        base_class: object,
        risk_score: object,
        camera_id: object,
        zone: object,
        confidence: object,
        verification_status: object,
        timestamp: object,
        behaviors: object,
        prompt: str,
        matched: set[str],
        evidence: list[str],
    ) -> dict[str, Any]:
        behaviour_list = [str(item) for item in behaviors] if isinstance(behaviors, (list, tuple, set)) else []
        confidence_score = 0.55 + (0.1 * len(matched))
        if str(verification_status or "").lower() in {"confirmed", "critical"}:
            confidence_score += 0.15
        return {
            "track_id": str(identifier if identifier is not None else "unknown"),
            "source": source,
            "base_class": str(base_class),
            "semantic_label": "live evidence match",
            "semantic_confidence": min(round(confidence_score, 2), 1.0),
            "risk_score": min(max(self._number(risk_score), 0.0), 1.0),
            "matched_phrase": prompt,
            "behaviors": behaviour_list,
            "camera_id": str(camera_id) if camera_id is not None else None,
            "zone": str(zone) if zone is not None else None,
            "confidence": self._number(confidence) if confidence is not None else None,
            "verification_status": str(verification_status) if verification_status is not None else None,
            "timestamp": str(timestamp) if timestamp is not None else None,
            "evidence": evidence,
        }

    @staticmethod
    def _number(value: object) -> float:
        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0
