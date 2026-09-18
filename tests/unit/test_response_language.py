"""Language selection must be deterministic before any provider call."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from aegis.ai.language import (
    ResponseLanguage,
    detect_response_language,
    live_turn_with_language,
)
from aegis.ai.orchestrator import AIOrchestrator
from aegis.ai.schemas import ChatRequest, Intent


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("كم كاميرا شغالة الآن؟", ResponseLanguage.ARABIC),
        ("فيه high risk alert؟", ResponseLanguage.ARABIC),
        ("What happened in camera 3?", ResponseLanguage.ENGLISH),
        ("Kameralar şu anda aktif mi?", ResponseLanguage.TURKISH),
        ("Please reply in English: كم كاميرا شغالة؟", ResponseLanguage.ENGLISH),
        ("Speak Arabic: What happened in camera 3?", ResponseLanguage.ARABIC),
        ("Türkçe konuş. What happened in camera 3?", ResponseLanguage.TURKISH),
    ],
)
def test_detect_response_language_uses_latest_message_and_explicit_override(message, expected) -> None:
    assert detect_response_language(message) is expected


class _CapturingProvider:
    def __init__(self) -> None:
        self.prompt = ""
        self.system_prompt = ""

    def generate_json(self, *, prompt: str, system_prompt: str):
        self.prompt = prompt
        self.system_prompt = system_prompt
        return {"intent": "General", "answer": "تمت المعالجة.", "confidence": 0.9}


def _patch_non_official_context(monkeypatch) -> None:
    import aegis.ai.orchestrator as orchestrator_module

    knowledge = SimpleNamespace(
        retrieve=lambda _message, *, locale: SimpleNamespace(
            is_official_question=False,
            locale=locale,
        )
    )
    monkeypatch.setattr(orchestrator_module, "get_system_knowledge_service", lambda: knowledge)
    monkeypatch.setattr(orchestrator_module, "collect_system_context", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(orchestrator_module, "context_to_text", lambda _context: "verified context")
    monkeypatch.setattr(orchestrator_module, "collect_intent_context", lambda *_args: {})


@pytest.mark.parametrize("voice_mode", [False, True])
def test_orchestrator_stores_language_and_injects_mandatory_instruction(monkeypatch, voice_mode) -> None:
    _patch_non_official_context(monkeypatch)
    provider = _CapturingProvider()

    response = AIOrchestrator(provider=provider).process(
        ChatRequest(message="كم كاميرا شغالة الآن؟"),
        voice_mode=voice_mode,
    )

    assert response.response_language is ResponseLanguage.ARABIC
    assert "RESPONSE LANGUAGE (MANDATORY): Arabic." in provider.prompt
    assert "Respond only in Arabic" in provider.prompt


def test_local_fallback_keeps_arabic_response_when_provider_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        "aegis.ai.tools.get_active_alerts",
        lambda limit: [{"event_id": "risk-1", "risk_level": "HIGH", "camera_id": "north-gate"}],
    )

    response = AIOrchestrator()._build_fallback(
        Intent.RISK,
        "هل يوجد تنبيه خطورة؟",
        5.0,
        "provider unavailable",
    )

    assert response.response_language is ResponseLanguage.ARABIC
    assert "تنبيهات المخاطر" in response.answer
    assert "Latest" not in response.answer


def test_live_turn_language_instruction_is_bound_to_the_detected_language() -> None:
    payload = live_turn_with_language("فيه high risk alert؟", ResponseLanguage.ARABIC)

    assert "RESPONSE LANGUAGE (MANDATORY): Arabic." in payload
    assert payload.endswith("Operator request: فيه high risk alert؟")
