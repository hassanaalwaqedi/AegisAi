"""Explainable incident assessment derived from durable event facts."""

from __future__ import annotations

from datetime import datetime, timezone

from aegis.database.models import Event, Incident
from aegis.database.repositories import RiskAssessmentRepository


POLICY_VERSION = "incident-policy-v1"


def persist_assessment(repository: RiskAssessmentRepository, incident: Incident, event: Event):
    """Record one non-probabilistic assessment for an incident event update."""
    metadata = event.event_metadata if isinstance(event.event_metadata, dict) else {}
    factors = [str(value) for value in (event.factors or []) if str(value).strip()]
    factors.extend(
        str(value) for value in (metadata.get("reason_codes") or []) if str(value).strip() and str(value) not in factors
    )
    missing: list[str] = []
    if not metadata.get("threat_context"):
        missing.append("independent_interaction_signal_missing")
    if event.snapshot_status != "saved":
        missing.append("snapshot_artifact_unavailable")
    if metadata.get("association_type") in {"near", "overlap", "contained"}:
        missing.append("geometric_association_is_not_identity_or_intent_proof")
    observed_at = event.timestamp if isinstance(event.timestamp, datetime) else datetime.now(timezone.utc)
    assessment_id = f"assessment:{event.event_id}:{POLICY_VERSION}"
    return repository.create_or_get(
        assessment_id=assessment_id,
        policy_version=POLICY_VERSION,
        incident_id=incident.incident_id,
        event_id=event.event_id,
        assessed_at=observed_at,
        risk_level=event.risk_level or "LOW",
        policy_score=event.risk_score,
        confidence_status="not_calibrated",
        factor_results=factors,
        missing_evidence=missing,
        rationale=event.reason or event.message,
    )
