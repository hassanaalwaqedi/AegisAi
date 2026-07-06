"""
Evidence-grounded explanation generation.

The explainer formats detector/tracker facts. It intentionally avoids action,
intent, or pose claims that are not produced by enabled models.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class EvidenceExplainer:
    """Create operator-facing text from explicit evidence fields only."""

    def explain_track(
        self,
        *,
        class_name: str,
        confidence: float,
        is_person: bool = False,
        is_vehicle: bool = False,
        is_weapon: bool = False,
        association: Optional[Dict[str, Any]] = None,
        verification_status: str = "confirmed",
        risk_level: str = "LOW",
    ) -> str:
        normalized = str(class_name or "object").lower()
        pct = f"{confidence:.2f}"

        if is_weapon:
            if confidence < 0.50:
                return f"{normalized.title()} detected with {pct} confidence; confidence is below verification threshold."

            if association:
                association_type = str(association.get("association_type") or "none")
                stable_frames = int(association.get("stable_frames") or 0)
                person_track_id = association.get("person_track_id")
                association_score = float(association.get("association_score") or 0.0)
                if association_type == "near":
                    return (
                        f"{normalized.title()} detected with {pct} confidence near Person #{person_track_id} "
                        f"for {stable_frames} consecutive frames; association score {association_score:.2f}."
                    )
                if association_type in {"contained", "overlap"}:
                    return (
                        f"{normalized.title()} detected with {pct} confidence associated with Person #{person_track_id} "
                        f"for {stable_frames} consecutive frames; association score {association_score:.2f}."
                    )

            return f"{normalized.title()} detected with {pct} confidence without person association."

        if is_person:
            return "Person detected. Risk remains LOW because no confirmed threat evidence exists."

        if is_vehicle:
            return "Vehicle detected. Risk remains LOW because no confirmed threat evidence exists."

        if verification_status == "candidate" or risk_level == "CANDIDATE_MEDIUM":
            return "Candidate evidence detected; further temporal confirmation is required."

        return f"{normalized.title()} detected by backend object detector."

    def explain_event(self, evidence: Dict[str, Any]) -> str:
        return self.explain_track(
            class_name=str(evidence.get("class_name") or evidence.get("weapon_class") or "object"),
            confidence=float(evidence.get("confidence") or evidence.get("weapon_confidence") or 0.0),
            is_person=bool(evidence.get("is_person")),
            is_vehicle=bool(evidence.get("is_vehicle")),
            is_weapon=bool(evidence.get("is_weapon") or evidence.get("weapon_class")),
            association=evidence.get("association"),
            verification_status=str(evidence.get("verification_status") or "confirmed"),
            risk_level=str(evidence.get("risk_level") or "LOW"),
        )
