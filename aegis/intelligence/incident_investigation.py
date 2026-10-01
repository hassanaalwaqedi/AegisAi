"""Agent-safe read models for incident investigation.

These projections expose persisted evidence, never ORM objects, media bytes, or
filesystem paths. They keep CV measurements, policy decisions, VLM results,
and operator lifecycle data in separate fields.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from math import hypot
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

logger = logging.getLogger(__name__)

_SNAPSHOT_ROOT = Path("data/output/snapshots")
_RECORDING_ROOT = Path("data/recordings")
_TIME_WINDOW = re.compile(r"^(\d{1,8})(s|m|h|d)$", re.IGNORECASE)


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _safe_file_available(value: Any, root: Path) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        approved_root = root.resolve()
        candidate = Path(value).resolve()
        return candidate != approved_root and approved_root in candidate.parents and candidate.is_file()
    except (OSError, RuntimeError, ValueError):
        return False


def _verification_projection(record: Any) -> Dict[str, Any]:
    """Whitelist verification fields; never forward evidence_metadata paths."""
    metadata = record.evidence_metadata if isinstance(record.evidence_metadata, dict) else {}
    safe_metadata = {
        key: metadata[key]
        for key in ("keyframe_count", "keyframe_timestamps", "keyframe_frame_ids", "event_frame_id")
        if key in metadata
    }
    return {
        "verificationId": record.verification_id,
        "incidentId": record.incident_id,
        "eventId": record.event_id,
        "cameraId": record.camera_id,
        "provider": record.provider,
        "model": record.model,
        "status": record.status,
        "combinedState": record.combined_state,
        "verdict": record.verdict,
        "confidence": record.confidence,
        "severity": record.severity,
        "summary": record.summary,
        "subjects": list(record.subjects or []),
        "observations": list(record.observations or []),
        "supportingEvidence": list(record.supporting_evidence or []),
        "contradictingEvidence": list(record.contradicting_evidence or []),
        "uncertainties": list(record.uncertainties or []),
        "recommendedAction": record.recommended_action,
        "evidenceMetadata": safe_metadata,
        "latencyMs": record.latency_ms,
        "analysisVersion": record.analysis_version,
        "createdAt": _iso(record.created_at),
        "updatedAt": _iso(record.updated_at),
    }


def _event_projection(event: Any) -> Dict[str, Any]:
    metadata = event.event_metadata if isinstance(event.event_metadata, dict) else {}
    metadata_tracks = metadata.get("track_ids") if isinstance(metadata.get("track_ids"), list) else []
    tracks = []
    for value in [event.track_key, *metadata_tracks]:
        if value is not None and str(value).strip() and str(value) not in tracks:
            tracks.append(str(value))
    return {
        "eventId": event.event_id,
        "incidentId": event.incident_id,
        "eventType": event.event_type,
        "timestamp": _iso(event.timestamp),
        "cameraId": event.camera_id,
        "cameraName": event.camera_name,
        "riskLevel": event.risk_level,
        "riskScore": event.risk_score,
        "message": event.message,
        "reason": event.reason,
        "factors": list(event.factors or []),
        "tracks": tracks,
        "zoneId": event.zone_id,
        "zoneName": event.zone_name,
        "snapshotAvailable": event.snapshot_status == "saved" and _safe_file_available(event.snapshot_path, _SNAPSHOT_ROOT),
        "clipAvailable": _safe_file_available(event.clip_path, _RECORDING_ROOT),
        "createdAt": _iso(event.created_at),
    }


def _assessment_projection(record: Any) -> Dict[str, Any]:
    return {
        "assessmentId": record.assessment_id,
        "eventId": record.event_id,
        "assessedAt": _iso(record.assessed_at),
        "riskLevel": record.risk_level,
        "policyScore": record.policy_score,
        "confidenceStatus": record.confidence_status,
        "factorResults": list(record.factor_results or []),
        "missingEvidence": list(record.missing_evidence or []),
        "rationale": record.rationale,
    }


def _load_incident_bundle(incident_id: str) -> Optional[Dict[str, Any]]:
    from aegis.database.connection import get_db_session
    from aegis.database.repositories import (
        EventRepository,
        IncidentRepository,
        IncidentVerificationRepository,
        RiskAssessmentRepository,
    )

    with get_db_session() as session:
        incident = IncidentRepository(session).get_by_incident_id(str(incident_id))
        if incident is None:
            return None
        events = EventRepository(session).get_by_incident_id(str(incident_id))
        assessments = RiskAssessmentRepository(session).list_for_incident(str(incident_id))
        verification_repository = IncidentVerificationRepository(session)
        verifications = verification_repository.list_for_incident(str(incident_id))
        verification_ids = {item.verification_id for item in verifications}
        for event in events:
            if event.event_id:
                event_verification = verification_repository.latest_for_event(str(event.event_id))
                if event_verification and event_verification.verification_id not in verification_ids:
                    verifications.append(event_verification)
                    verification_ids.add(event_verification.verification_id)
        verifications.sort(key=lambda item: _utc(item.created_at) if item.created_at else datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        latest_verification = verifications[0] if verifications else None

        event_rows = [_event_projection(item) for item in events]
        assessment_rows = [_assessment_projection(item) for item in assessments]
        verification_rows = [_verification_projection(item) for item in verifications]
        track_ids: list[str] = []
        for value in [incident.primary_track_id, *(incident.related_track_ids or [])]:
            if value is not None and str(value).strip() and str(value) not in track_ids:
                track_ids.append(str(value))
        for event in event_rows:
            for value in event["tracks"]:
                if value not in track_ids:
                    track_ids.append(value)

        latest_assessment = assessment_rows[-1] if assessment_rows else None
        operator_decision = None
        if incident.lifecycle_updated_at is not None or incident.lifecycle_updated_by or incident.lifecycle_reason:
            operator_decision = {
                "status": incident.lifecycle_status,
                "updatedAt": _iso(incident.lifecycle_updated_at),
                "updatedBy": incident.lifecycle_updated_by,
                "reason": incident.lifecycle_reason,
            }

        return {
            "incident": {
                "incidentId": incident.incident_id,
                "cameraId": incident.camera_id,
                "startTime": _iso(incident.start_time),
                "endTime": _iso(incident.last_seen_time),
                "status": incident.lifecycle_status or ("resolved" if incident.status == "resolved" else "open"),
                "processingStatus": incident.status,
                "severity": incident.current_risk_level,
                "maxRiskScore": incident.max_risk_score,
                "summary": incident.summary_reason,
                "riskTypes": list(incident.risk_types or []),
                "contributingFactors": list(incident.contributing_factors or []),
                "zoneId": incident.zone_id,
                "zoneName": incident.zone_name,
                "createdAt": _iso(incident.created_at),
                "updatedAt": _iso(incident.updated_at),
            },
            "events": event_rows,
            "tracks": track_ids,
            "riskAssessments": assessment_rows,
            "latestRiskAssessment": latest_assessment,
            "visualLanguageVerifications": verification_rows,
            "latestVisualLanguageVerification": _verification_projection(latest_verification) if latest_verification else None,
            "operatorDecision": operator_decision,
            "references": {
                "incidentId": incident.incident_id,
                "eventIds": [item["eventId"] for item in event_rows if item["eventId"]],
                "trackIds": track_ids,
                "verificationIds": [item["verificationId"] for item in verification_rows],
            },
        }


def get_recent_incidents(*, limit: int = 10, since_seconds: Optional[int] = None, severity: Optional[str] = None, camera_id: Optional[str] = None) -> Dict[str, Any]:
    from aegis.database.connection import get_db_session
    from aegis.database.repositories import IncidentRepository

    bounded_limit = max(1, min(int(limit), 50))
    lookback = max(1, min(int(since_seconds), 30 * 24 * 60 * 60)) if since_seconds is not None else None
    minimum_time = datetime.now(timezone.utc) - timedelta(seconds=lookback) if lookback is not None else None
    severity_filter = str(severity or "").strip().upper() or None
    camera_filter = str(camera_id or "").strip() or None
    allowed_severities = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
    if severity_filter and severity_filter not in allowed_severities:
        raise ValueError("Unsupported incident severity filter.")
    with get_db_session() as session:
        incidents = IncidentRepository(session).list_recent(limit=200)
        rows = []
        for item in incidents:
            if camera_filter and str(item.camera_id or "") != camera_filter:
                continue
            if minimum_time is not None and _utc(item.last_seen_time) < minimum_time:
                continue
            level = str(item.current_risk_level or "").upper()
            if severity_filter and level != severity_filter:
                continue
            rows.append({
                "incidentId": item.incident_id,
                "cameraId": item.camera_id,
                "startTime": _iso(item.start_time),
                "endTime": _iso(item.last_seen_time),
                "status": item.lifecycle_status or ("resolved" if item.status == "resolved" else "open"),
                "severity": item.current_risk_level,
                "maxRiskScore": item.max_risk_score,
                "summary": item.summary_reason,
                "eventIds": list(item.event_ids or []),
            })
            if len(rows) >= bounded_limit:
                break
        return {"incidents": rows, "count": len(rows), "limit": bounded_limit, "sinceSeconds": lookback, "severity": severity_filter, "cameraId": camera_filter}


def get_incident(incident_id: str) -> Optional[Dict[str, Any]]:
    return _load_incident_bundle(incident_id)


def get_incident_evidence(incident_id: str) -> Optional[Dict[str, Any]]:
    bundle = _load_incident_bundle(incident_id)
    if bundle is None:
        return None

    incident = bundle["incident"]
    snapshots = []
    for event in bundle["events"]:
        snapshots.append({
            "eventId": event["eventId"],
            "cameraId": event["cameraId"],
            "timestamp": event["timestamp"],
            "available": event["snapshotAvailable"],
            "reference": f"event:{event['eventId']}" if event["eventId"] else None,
            "provenance": "persisted_event_snapshot",
        })

    keyframes = []
    for verification in bundle["visualLanguageVerifications"]:
        metadata = verification.get("evidenceMetadata") or {}
        timestamps = metadata.get("keyframe_timestamps") if isinstance(metadata.get("keyframe_timestamps"), list) else []
        frame_ids = metadata.get("keyframe_frame_ids") if isinstance(metadata.get("keyframe_frame_ids"), list) else []
        count = max(int(metadata.get("keyframe_count") or 0), len(timestamps), len(frame_ids))
        for index in range(count):
            keyframes.append({
                "verificationId": verification["verificationId"],
                "eventId": verification["eventId"],
                "frameIndex": index,
                "frameId": frame_ids[index] if index < len(frame_ids) else None,
                "timestamp": timestamps[index] if index < len(timestamps) else None,
                "provenance": "stored_vlm_keyframe_metadata",
            })

    recordings = _overlapping_recordings(incident)
    return {
        "incidentId": incident["incidentId"],
        "snapshots": snapshots,
        "selectedKeyframes": keyframes,
        "recordings": recordings,
        "clips": [
            {"eventId": event["eventId"], "available": event["clipAvailable"], "provenance": "persisted_event_clip_reference"}
            for event in bundle["events"]
        ],
        "references": bundle["references"],
        "limitations": ["Image and video bytes are not included in agent context."],
    }


def _overlapping_recordings(incident: Dict[str, Any]) -> list[Dict[str, Any]]:
    metadata_path = _RECORDING_ROOT / "metadata.json"
    if not metadata_path.is_file():
        return []
    try:
        from aegis.recording.models import RecordingMetadata

        records = RecordingMetadata(str(metadata_path)).list_events(camera_id=incident["cameraId"], limit=1000)
    except Exception as exc:
        logger.info("Incident recording metadata unavailable (%s)", type(exc).__name__)
        return []
    incident_start = datetime.fromisoformat(incident["startTime"]) if incident.get("startTime") else None
    incident_end = datetime.fromisoformat(incident["endTime"]) if incident.get("endTime") else None
    results = []
    for record in records:
        record_start = getattr(record, "start_time", None)
        record_end = getattr(record, "end_time", None) or record_start
        if incident_start is None or incident_end is None or record_start is None or record_end is None:
            continue
        try:
            overlaps = _utc(record_start) <= _utc(incident_end) and _utc(record_end) >= _utc(incident_start)
        except (TypeError, ValueError):
            continue
        if not overlaps:
            continue
        results.append({
            "recordingId": str(record.event_id),
            "cameraId": str(record.camera_id),
            "startTime": _iso(record_start),
            "endTime": _iso(record_end),
            "available": _safe_file_available(record.file_path, _RECORDING_ROOT),
            "association": "camera_time_overlap_only",
            "provenance": "recording_metadata",
        })
    return results[:100]


def get_incident_timeline(incident_id: str) -> Optional[Dict[str, Any]]:
    bundle = _load_incident_bundle(incident_id)
    if bundle is None:
        return None
    incident = bundle["incident"]
    items: list[Dict[str, Any]] = []

    def add(timestamp: Optional[str], kind: str, label: str, **details: Any) -> None:
        if timestamp:
            items.append({"timestamp": timestamp, "kind": kind, "label": label, **details})

    add(incident.get("createdAt"), "incident", "Incident record created", incidentId=incident["incidentId"])
    add(incident.get("startTime"), "incident", "Incident observation window started", incidentId=incident["incidentId"])
    for event in bundle["events"]:
        add(
            event.get("timestamp"), "cv_event", "Persisted computer-vision event",
            eventId=event.get("eventId"), eventType=event.get("eventType"), riskLevel=event.get("riskLevel"),
            riskScore=event.get("riskScore"), factors=event.get("factors", []), reason=event.get("reason"),
        )
    for assessment in bundle["riskAssessments"]:
        add(
            assessment.get("assessedAt"), "risk_assessment", "Risk engine assessment recorded",
            assessmentId=assessment.get("assessmentId"), eventId=assessment.get("eventId"),
            riskLevel=assessment.get("riskLevel"), policyScore=assessment.get("policyScore"),
            rationale=assessment.get("rationale"),
        )
    for verification in bundle["visualLanguageVerifications"]:
        add(
            verification.get("updatedAt") or verification.get("createdAt"), "vlm_verification", "Visual-language verification status recorded",
            verificationId=verification.get("verificationId"), eventId=verification.get("eventId"),
            status=verification.get("status"), combinedState=verification.get("combinedState"),
            verdict=verification.get("verdict"),
        )
    decision = bundle.get("operatorDecision")
    if decision:
        add(
            decision.get("updatedAt"), "operator_decision", "Operator lifecycle decision recorded",
            status=decision.get("status"), reason=decision.get("reason"), updatedBy=decision.get("updatedBy"),
        )
    items.sort(key=lambda item: _utc(datetime.fromisoformat(item["timestamp"])))
    return {"incidentId": incident["incidentId"], "items": items, "count": len(items)}


def generate_incident_report(incident_id: str) -> Optional[Dict[str, Any]]:
    bundle = _load_incident_bundle(incident_id)
    if bundle is None:
        return None
    timeline = get_incident_timeline(incident_id)
    evidence = get_incident_evidence(incident_id)
    assessments = bundle["riskAssessments"]
    latest_vlm = bundle["latestVisualLanguageVerification"]
    uncertainties = []
    for assessment in assessments:
        uncertainties.extend(str(value) for value in assessment.get("missingEvidence", []) if value)
    if latest_vlm:
        uncertainties.extend(str(value) for value in latest_vlm.get("uncertainties", []) if value)
    return {
        "reportType": "evidence_grounded_incident_report",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "incident": bundle["incident"],
        "computerVision": {"events": bundle["events"], "tracks": bundle["tracks"]},
        "riskEngine": {"assessments": assessments, "latest": bundle["latestRiskAssessment"]},
        "timeline": timeline["items"] if timeline else [],
        "subjectsAndTracks": bundle["tracks"],
        "visualEvidence": evidence,
        "visualLanguageVerification": latest_vlm,
        "uncertainties": list(dict.fromkeys(uncertainties)),
        "operatorDecision": bundle["operatorDecision"],
        "references": bundle["references"],
        "provenance": {
            "computerVision": "persisted events and observations",
            "riskEngine": "persisted risk assessments",
            "visualLanguageVerification": "stored secondary assessment; not ground truth",
            "operatorDecision": "persisted incident lifecycle fields",
        },
    }


def get_risk_explanation(*, incident_id: Optional[str] = None, event_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if incident_id:
        bundle = _load_incident_bundle(incident_id)
        if bundle is None:
            return None
        return {
            "incidentId": incident_id,
            "computerVisionEvents": bundle["events"],
            "riskAssessments": bundle["riskAssessments"],
            "visualLanguageVerification": bundle["latestVisualLanguageVerification"],
            "operatorDecision": bundle["operatorDecision"],
            "references": bundle["references"],
            "limitations": ["Explain only the stored risk factors and assessments; no intent or identity is inferred."],
        }
    if not event_id:
        return None
    from aegis.database.connection import get_db_session
    from aegis.database.repositories import EventRepository, IncidentVerificationRepository, RiskAssessmentRepository

    with get_db_session() as session:
        event = EventRepository(session).get_by_event_id(str(event_id))
        if event is None:
            return None
        assessments = RiskAssessmentRepository(session).list_for_incident(event.incident_id) if event.incident_id else []
        verification = IncidentVerificationRepository(session).latest_for_event(str(event_id))
        projected = _event_projection(event)
        return {
            "event": projected,
            "riskAssessments": [_assessment_projection(item) for item in assessments],
            "visualLanguageVerification": _verification_projection(verification) if verification else None,
            "references": {"incidentId": event.incident_id, "eventId": event.event_id, "cameraId": event.camera_id, "trackIds": projected["tracks"]},
            "limitations": ["Explain only the stored risk factors and assessments; no intent or identity is inferred."],
        }


def parse_time_window(value: Optional[str]) -> Optional[timedelta]:
    if value is None or not str(value).strip():
        return None
    match = _TIME_WINDOW.fullmatch(str(value).strip())
    if not match:
        raise ValueError("Use a bounded time window such as 30s, 10m, 2h, or 1d.")
    amount = int(match.group(1))
    unit = match.group(2).lower()
    seconds = amount * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
    if amount < 1 or seconds > 30 * 24 * 60 * 60:
        raise ValueError("Track history time window must be between one second and thirty days.")
    return timedelta(seconds=seconds)


def get_track_trajectory(track_id: str, *, camera_id: Optional[str] = None, time_window: Optional[str] = None) -> Dict[str, Any]:
    from aegis.database.connection import get_db_session
    from aegis.database.models import Event, Observation
    from aegis.database.repositories import ObservationRepository

    identifier = str(track_id or "").strip()[:160]
    if not identifier:
        return {"availability": "unavailable", "reason": "A track ID is required."}
    window = parse_time_window(time_window)
    normalized_camera = str(camera_id or "").strip() or None
    with get_db_session() as session:
        if ":" in identifier:
            candidates = [identifier]
        elif normalized_camera:
            candidates = [f"{normalized_camera}:{identifier}"]
        else:
            candidates = [str(row[0]) for row in session.query(Observation.track_key).filter(
                Observation.track_key.like(f"%:{identifier}"),
                Observation.track_key.isnot(None),
            ).distinct().limit(20).all()]
        if len(candidates) > 1:
            return {"availability": "unavailable", "error": "ambiguous_track_id", "candidateTrackIds": candidates}
        if not candidates:
            return {"availability": "unavailable", "error": "track_history_not_persisted", "trackId": identifier}
        track_key = candidates[0]
        observations = ObservationRepository(session).list_for_track(track_key, limit=1000)
        if window is not None:
            cutoff = datetime.now(timezone.utc) - window
            observations = [item for item in observations if _utc(item.captured_at) >= cutoff]
        observations = list(reversed(observations))
        if not observations:
            return {"availability": "unavailable", "error": "track_history_not_available_for_window", "trackId": track_key}

        event_ids = list(dict.fromkeys(str(item.event_id) for item in observations if item.event_id))
        events = session.query(Event).filter(Event.track_key == track_key).order_by(Event.timestamp.asc()).limit(100).all()
        event_ids.extend(str(item.event_id) for item in events if item.event_id and item.event_id not in event_ids)
        points = []
        previous = None
        for item in observations:
            box = item.bounding_box if isinstance(item.bounding_box, (list, tuple)) and len(item.bounding_box) == 4 else None
            center = ((float(box[0]) + float(box[2])) / 2, (float(box[1]) + float(box[3])) / 2) if box else None
            metadata = item.observation_metadata if isinstance(item.observation_metadata, dict) else {}
            speed = None
            if center is not None and previous is not None:
                previous_time, previous_center = previous
                elapsed = (_utc(item.captured_at) - previous_time).total_seconds()
                if elapsed > 0:
                    speed = round(hypot(center[0] - previous_center[0], center[1] - previous_center[1]) / elapsed, 3)
            if center is not None:
                previous = (_utc(item.captured_at), center)
            points.append({
                "timestamp": _iso(item.captured_at),
                "cameraId": item.camera_id,
                "frameId": item.frame_id,
                "label": item.label,
                "boundingBoxXyxyPixels": list(box) if box else None,
                "positionPixels": {"x": round(center[0], 2), "y": round(center[1], 2)} if center else None,
                "normalizedPosition": None,
                "derivedSpeedPixelsPerSecond": speed,
                "riskLevel": metadata.get("risk_level"),
                "policyScore": metadata.get("policy_score"),
                "riskFactors": list(metadata.get("risk_factors") or []),
                "behaviorLabels": list(metadata.get("behavior_labels") or []),
                "eventId": item.event_id,
                "source": "persisted_observation",
            })
        event_rows = [_event_projection(item) for item in events]
        return {
            "availability": "live",
            "trackId": track_key,
            "cameraId": observations[-1].camera_id,
            "historySource": "persisted_observations",
            "timeWindow": time_window,
            "observations": points,
            "associatedEvents": event_rows,
            "eventIds": event_ids,
            "limitations": [
                "Observation records do not persist camera frame dimensions; normalized positions are unavailable.",
                "Speed is derived from pixel-center displacement and capture timestamps; it is not calibrated physical speed.",
                "Movement state and cross-camera identity are not persisted by this trajectory source.",
                "Trajectory is capped at the 1000 most recent persisted observations.",
            ],
        }
