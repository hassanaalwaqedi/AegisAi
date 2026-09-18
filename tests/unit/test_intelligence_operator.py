"""Behavior tests for the real Intelligence command executor."""

from datetime import datetime, timezone

from aegis.ai.schemas import OperatorCommandRequest
from aegis.intelligence import operator


def test_high_risk_command_filters_real_event_records_and_preserves_navigation(monkeypatch):
    monkeypatch.setattr(operator, "get_recent_events", lambda limit: [
        {"event_id": "high-1", "risk_level": "HIGH", "timestamp": datetime.now(timezone.utc).isoformat(), "message": "Restricted entry", "camera_id": "north"},
        {"event_id": "low-1", "risk_level": "LOW", "timestamp": datetime.now(timezone.utc).isoformat(), "message": "Routine motion", "camera_id": "south"},
    ])

    response = operator.execute_operator_command(OperatorCommandRequest(message="Show high-risk events from the last hour"))

    assert response.action == "RISK_QUERY"
    assert response.target == "/events?range=1h&risk=high"
    assert response.result["total"] == 1
    assert response.result["events"][0]["event_id"] == "high-1"
    assert [step.key for step in response.trace] == ["understood", "source", "completed"]


def test_arabic_risk_command_uses_the_same_verified_event_path(monkeypatch):
    monkeypatch.setattr(operator, "get_recent_events", lambda limit: [
        {"event_id": "critical-1", "risk_level": "CRITICAL", "timestamp": datetime.now(timezone.utc).isoformat(), "message": "خطر مؤكد", "camera_id": "north"},
    ])

    response = operator.execute_operator_command(OperatorCommandRequest(message="اعرض الأحداث عالية الخطورة خلال الساعة الماضية"))

    assert response.action == "RISK_QUERY"
    assert response.response_language.value == "Arabic"
    assert response.result["events"][0]["event_id"] == "critical-1"


def test_camera_command_resolves_only_a_configured_camera(monkeypatch):
    monkeypatch.setattr(operator, "get_camera_status", lambda: {
        "availability": "available",
        "cameras": [
            {"camera_id": "north-gate", "name": "North Gate", "status": "online", "source_type": "RTSP_STREAM"},
            {"camera_id": "south-gate", "name": "South Gate", "status": "offline", "source_type": "HTTP_STREAM"},
        ],
    })

    response = operator.execute_operator_command(OperatorCommandRequest(message="Open North Gate camera"))

    assert response.action == "CAMERA_OPEN"
    assert response.result["camera"]["camera_id"] == "north-gate"
    assert response.target == "/cameras?camera=north-gate&view=focus"


def test_evidence_command_returns_only_semantic_index_results(monkeypatch):
    monkeypatch.setattr(operator.evidence_search, "search", lambda request: {
        "results": [{"event_id": "evt-1", "reason": "Person near restricted zone", "event_type": "risk_alert"}],
        "total": 1,
        "pending_evidence": 0,
    })

    response = operator.execute_operator_command(OperatorCommandRequest(message="Find evidence of a person near the restricted zone"))

    assert response.action == "EVIDENCE_SEARCH"
    assert response.result["evidence"][0]["event_id"] == "evt-1"
    assert response.sources[0].id == "evt-1"
    assert response.target.startswith("/semantic?q=")


def test_highest_risk_selects_most_severe_actual_event(monkeypatch):
    monkeypatch.setattr(operator, "get_recent_events", lambda limit: [
        {"event_id": "low", "risk_level": "LOW", "risk_score": 0.1},
        {"event_id": "critical", "risk_level": "CRITICAL", "risk_score": 0.9},
        {"event_id": "high", "risk_level": "HIGH", "risk_score": 0.7},
    ])
    response = operator.execute_operator_command(OperatorCommandRequest(message="Show the highest risk event"))
    assert [row["event_id"] for row in response.result["events"]] == ["critical"]


def test_related_evidence_requires_selection():
    response = operator.execute_operator_command(OperatorCommandRequest(message="Show related evidence"))
    assert response.result["evidence"] == []
    assert "Select an event" in response.answer


def test_voice_scene_ordinal_resolves_display_order_before_query(monkeypatch):
    from aegis.intelligence import operator_scene
    captured = []
    monkeypatch.setattr(operator_scene, "execute_operator_command", lambda request: captured.append(request))
    context = operator_scene.OperatorSceneContext(panel="events", ordered_ids=["newer", "older"], selected_id="newer")
    operator_scene.execute_scene_command("Open the second one", context)
    assert captured[0].previous_evidence_id == "older"
    assert captured[0].message == "Show related evidence"


def test_voice_scene_context_is_bounded():
    import pytest
    from pydantic import ValidationError
    from aegis.intelligence.operator_scene import OperatorSceneContext
    with pytest.raises(ValidationError):
        OperatorSceneContext(ordered_ids=[str(i) for i in range(51)])
