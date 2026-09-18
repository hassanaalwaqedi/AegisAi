"""The operator fallback must still answer risk questions from verified data."""

from __future__ import annotations

from aegis.ai.orchestrator import AIOrchestrator
from aegis.ai.schemas import Intent


def test_risk_fallback_summarizes_verified_high_priority_alerts(monkeypatch) -> None:
    monkeypatch.setattr(
        "aegis.ai.tools.get_active_alerts",
        lambda limit: [
            {
                "event_id": "risk-1",
                "risk_level": "HIGH",
                "camera_id": "north-gate",
                "message": "Possible weapon-person association.",
            },
            {
                "event_id": "risk-2",
                "risk_level": "CRITICAL",
                "camera_id": "loading-dock",
                "message": "Second person in close range with fast movement.",
            },
        ],
    )

    response = AIOrchestrator()._build_fallback(Intent.RISK, "show risks", 5.0, "provider unavailable")

    assert "1 critical and 1 high" in response.answer
    assert "loading-dock" in response.answer
    assert [source.id for source in response.sources] == ["risk-1", "risk-2"]
    assert response.confidence == 0.75
