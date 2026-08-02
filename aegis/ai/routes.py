"""Authenticated AI endpoints and truthful Intelligence compatibility views."""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends

from aegis.api.security import verify_api_key
from aegis.ai.schemas import ChatRequest, ChatResponse, VoiceRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])


def _intelligence_payload() -> Dict[str, Any]:
    """Return the single Phase 0 operational contract for compatibility APIs."""
    from aegis.intelligence.context_service import get_intelligence_context_service

    payload = get_intelligence_context_service().build().model_dump(
        by_alias=True, mode="json"
    )
    # This is a source-backed capability signal only.  It deliberately does
    # not expose private records, record IDs, source paths, or content.
    try:
        from aegis.knowledge.service import get_system_knowledge_service

        result = get_system_knowledge_service().retrieve("what is Aegis", locale="en")
        payload["officialKnowledge"] = {
            "availability": result.availability,
            "publicRecordsAvailable": len(result.records) if result.availability == "available" else None,
            "reason": result.reason if result.availability == "unavailable" else None,
        }
    except Exception:
        payload["officialKnowledge"] = {
            "availability": "unavailable",
            "publicRecordsAvailable": None,
            "reason": "Official knowledge retrieval failed.",
        }
    return payload


@router.post("/chat", response_model=ChatResponse)
async def ai_chat(
    request: ChatRequest,
    _: bool = Depends(verify_api_key),
) -> ChatResponse:
    """Process an authenticated text interaction through the AI orchestrator."""
    try:
        from aegis.ai.orchestrator import get_orchestrator

        return get_orchestrator().process(request)
    except Exception as exc:
        logger.error("AI chat error: %s", exc)
        return ChatResponse(
            answer="I couldn't process your request. Please try again.",
            error=str(exc),
            confidence=0.0,
        )


@router.post("/voice", response_model=ChatResponse)
async def ai_voice(
    request: VoiceRequest,
    _: bool = Depends(verify_api_key),
) -> ChatResponse:
    """Process explicit, pre-transcribed push-to-talk input only."""
    if not request.text:
        return ChatResponse(
            answer="No voice input received.",
            error="Empty transcription",
            confidence=0.0,
        )

    try:
        from aegis.ai.orchestrator import get_orchestrator

        return get_orchestrator().process(ChatRequest(message=request.text), voice_mode=True)
    except Exception as exc:
        logger.error("AI voice error: %s", exc)
        return ChatResponse(
            answer="I couldn't process your voice command.",
            error=str(exc),
            confidence=0.0,
        )


@router.get("/health")
async def ai_health(_: bool = Depends(verify_api_key)) -> Dict[str, Any]:
    """Expose source-backed AI capability states without a fixed healthy flag."""
    context = _intelligence_payload()
    return {
        "generatedAt": context["generatedAt"],
        "chat": context["ai"]["chat"],
        "providerConfigured": context["ai"]["providerConfigured"],
        "evidenceGrounding": context["ai"]["evidenceGrounding"],
        "voice": context["ai"]["voice"],
    }


@router.get("/context")
async def ai_context(_: bool = Depends(verify_api_key)) -> Dict[str, Any]:
    """Compatibility alias for the versioned Intelligence context contract."""
    return _intelligence_payload()


@router.get("/suggestions")
async def ai_suggestions(_: bool = Depends(verify_api_key)) -> Dict[str, Any]:
    """Return only evidence-backed suggestions with an implemented route."""
    context = _intelligence_payload()
    return {"suggestions": context["suggestions"]}


@router.get("/metrics")
async def ai_system_metrics(_: bool = Depends(verify_api_key)) -> Dict[str, Any]:
    """Deprecated compatibility alias; no fabricated numeric metrics are returned."""
    return _intelligence_payload()
