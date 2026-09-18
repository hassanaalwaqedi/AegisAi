"""Regression tests for the safe, unified Intelligence event projection."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from aegis.intelligence.event_access import merge_event_records, persisted_event_record


def test_merge_event_records_deduplicates_by_public_event_id_and_keeps_runtime_fields() -> None:
    records = merge_event_records(
        [{"event_id": "risk-1", "timestamp": "2026-08-09T12:00:00+00:00", "description": "Persisted evidence."}],
        [{"event_id": "risk-1", "timestamp": "2026-08-09T12:00:00+00:00", "acknowledged": False}],
    )

    assert records == [
        {
            "event_id": "risk-1",
            "timestamp": "2026-08-09T12:00:00+00:00",
            "description": "Persisted evidence.",
            "acknowledged": False,
        }
    ]


def test_persisted_event_projection_preserves_risk_and_evidence_fields() -> None:
    event = SimpleNamespace(
        id=17,
        event_id="risk-17",
        alert_id="alert-17",
        incident_id="incident-17",
        event_type="risk_alert",
        timestamp=datetime(2026, 8, 9, 12, tzinfo=timezone.utc),
        created_at=None,
        camera_id="north-gate",
        camera_name="North Gate",
        track_key="person-12",
        track_id=None,
        risk_level="HIGH",
        risk_score=0.91,
        object_class="knife",
        bounding_box=[1, 2, 3, 4],
        reason="Possible knife detected near person track #12.",
        message="Possible armed threat.",
        factors=["weapon_person_association"],
        zone="north",
        zone_id="zone-north",
        zone_name="North Gate",
        snapshot_status="saved",
        event_metadata={"weapon_confidence": 0.88},
    )

    record = persisted_event_record(event)

    assert record["event_id"] == "risk-17"
    assert record["incident_id"] == "incident-17"
    assert record["track_id"] == "person-12"
    assert record["description"] == "Possible knife detected near person track #12."
    assert record["evidence_status"] == "persisted"
    assert record["data"]["weapon_confidence"] == 0.88
