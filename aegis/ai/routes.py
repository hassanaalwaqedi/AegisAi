"""Authenticated AI endpoints and truthful Intelligence compatibility views."""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, Header

from aegis.api.security import verify_api_key
from aegis.ai.language import detect_response_language, processing_error_message
from aegis.ai.schemas import ChatRequest, ChatResponse, OperatorCommandRequest, OperatorExecutionResponse, VoiceRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])


def _audit_agent_request(response: ChatResponse, *, actor: str | None, voice_mode: bool) -> None:
    """Audit agent use without persisting the operator's raw message."""
    from aegis.audit import record_audit

    record_audit(
        "agent.operational_query",
        actor_id=(str(actor or "").strip()[:160] or "api-key-operator"),
        resource_type="agent",
        resource_id=None,
        details={
            "intent": response.intent.value,
            "response_language": response.response_language.value,
            "voice_mode": voice_mode,
            "source_types": sorted({source.type for source in response.sources}),
            "availability": "unavailable" if response.error else "available",
        },
    )


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
    x_aegis_actor: str | None = Header(default=None),
    _: bool = Depends(verify_api_key),
) -> ChatResponse:
    """Process an authenticated text interaction through the AI orchestrator."""
    try:
        from aegis.ai.orchestrator import get_orchestrator

        response = get_orchestrator().process(request)
    except Exception as exc:
        logger.error("AI chat error: %s", exc)
        response_language = detect_response_language(request.message)
        response = ChatResponse(
            answer=processing_error_message(response_language),
            error=str(exc),
            confidence=0.0,
            response_language=response_language,
        )
    _audit_agent_request(response, actor=x_aegis_actor, voice_mode=False)
    return response


@router.post("/operator/execute", response_model=OperatorExecutionResponse)
async def execute_operator(
    request: OperatorCommandRequest,
    x_aegis_actor: str | None = Header(default=None),
    _: bool = Depends(verify_api_key),
) -> OperatorExecutionResponse:
    """Execute a typed operator command against authoritative Aegis services."""
    from aegis.audit import record_audit
    from aegis.intelligence.operator import execute_operator_command

    response = execute_operator_command(request)
    record_audit(
        "agent.command_executed",
        actor_id=(str(x_aegis_actor or "").strip()[:160] or "api-key-operator"),
        resource_type="agent",
        resource_id=response.sources[0].id if response.sources else None,
        details={
            "action": response.action,
            "intent": response.intent.value,
            "panel": response.panel,
            "source_types": sorted({source.type for source in response.sources}),
            "availability": "unavailable" if response.error else "available",
        },
    )
    return response


@router.post("/voice", response_model=ChatResponse)
async def ai_voice(
    request: VoiceRequest,
    x_aegis_actor: str | None = Header(default=None),
    _: bool = Depends(verify_api_key),
) -> ChatResponse:
    """Process explicit, pre-transcribed push-to-talk input only."""
    if not request.text:
        response = ChatResponse(
            answer="No voice input received.",
            error="Empty transcription",
            confidence=0.0,
        )
        _audit_agent_request(response, actor=x_aegis_actor, voice_mode=True)
        return response

    try:
        from aegis.ai.orchestrator import get_orchestrator

        response = get_orchestrator().process(ChatRequest(message=request.text), voice_mode=True)
    except Exception as exc:
        logger.error("AI voice error: %s", exc)
        response_language = detect_response_language(request.text)
        response = ChatResponse(
            answer=processing_error_message(response_language),
            error=str(exc),
            confidence=0.0,
            response_language=response_language,
        )
    _audit_agent_request(response, actor=x_aegis_actor, voice_mode=True)
    return response


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
