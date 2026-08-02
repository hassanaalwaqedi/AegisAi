"""
AegisAI - AI Orchestrator

The brain of the AI module. Receives user requests, classifies intent,
collects verified context, calls the LLM provider, returns structured responses.

Flow:
    Frontend → POST /api/ai/chat → Orchestrator → Collect Context → LLMProvider → JSON → Frontend

The orchestrator is LLM-agnostic — it works with any LLMProvider implementation.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

from aegis.ai.schemas import (
    ActionItem,
    ChatRequest,
    ChatResponse,
    Intent,
    SourceReference,
)
from aegis.ai.context import collect_system_context, context_to_text
from aegis.knowledge.service import NOT_DOCUMENTED, UNAVAILABLE, get_system_knowledge_service
from aegis.ai.prompts import (
    SYSTEM_PROMPT,
    CONTEXT_TEMPLATE,
    VOICE_SYSTEM_PROMPT,
    VOICE_CONTEXT_TEMPLATE,
    PROACTIVE_ALERT_TEMPLATE,
    format_history,
)
from aegis.ai.tools import (
    execute_tool,
    get_camera_detail,
    generate_incident_report,
    get_active_alerts,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Intent keywords mapping
# ---------------------------------------------------------------------------
INTENT_KEYWORDS: Dict[str, list] = {
    "Investigation": ["investigate", "inspection", "look into", "examine", "check camera", "review"],
    "Incident": ["incident", "accident", "breach", "intrusion", "unauthorized"],
    "Report": ["report", "generate report", "export", "summary", "daily report"],
    "Search": ["search", "find", "look for", "where", "locate", "semantic"],
    "Analytics": ["analytics", "statistics", "stats", "graph", "trend", "chart", "how many"],
    "Risk": ["risk", "threat", "danger", "highest risk", "critical", "suspicious"],
    "Camera": ["camera", "cam", "feed", "stream", "offline", "online"],
    "Tracking": ["track", "person", "vehicle", "object", "movement", "follow"],
    "Health": ["health", "status", "system", "gpu", "cpu", "memory", "database", "uptime"],
    "Knowledge": ["knowledge", "pattern", "history", "past", "learn"],
    "Settings": ["settings", "config", "configure", "setup"],
}


def classify_intent(message: str) -> Intent:
    """Classify user intent from the message text."""
    msg_lower = message.lower()
    scores: Dict[str, int] = {}

    for intent, keywords in INTENT_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in msg_lower)
        if score > 0:
            scores[intent] = score

    if scores:
        best = max(scores, key=scores.get)
        return Intent(best)
    return Intent.GENERAL


def collect_intent_context(intent: Intent, message: str) -> Dict[str, Any]:
    """Collect additional context specific to the classified intent."""
    extra: Dict[str, Any] = {}
    msg_lower = message.lower()

    # Extract camera ID if mentioned
    cam_match = re.search(r"camera\s*(\d+|[a-z0-9_-]+)", msg_lower)
    if cam_match:
        camera_id = cam_match.group(1)
        for prefix in [f"cam-{camera_id}", f"camera-{camera_id}", camera_id]:
            detail = get_camera_detail(prefix)
            if "error" not in detail:
                extra["camera_detail"] = detail
                break

    if intent == Intent.REPORT:
        extra["report_data"] = generate_incident_report()

    if intent == Intent.RISK:
        from aegis.ai.tools import get_high_risk_events
        extra["high_risk_events"] = get_high_risk_events(limit=10)

    if intent == Intent.HEALTH:
        from aegis.ai.tools import get_gpu_usage, get_database_status
        extra["gpu"] = get_gpu_usage()
        extra["database"] = get_database_status()

    return extra


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

class AIOrchestrator:
    """
    Central AI orchestrator. LLM-provider-agnostic.

    1. Receives user message + optional conversation history
    2. Classifies intent
    3. Collects verified system context
    4. Sends context + message + history to LLMProvider
    5. Parses structured response
    6. Returns ChatResponse
    """

    def __init__(self, provider=None):
        """
        Args:
            provider: An LLMProvider instance. If None, uses the default provider.
        """
        self._provider = provider

    def _get_provider(self):
        """Lazy-load the default provider if none was injected."""
        if self._provider is None:
            from aegis.ai.provider import get_default_provider
            self._provider = get_default_provider()
        return self._provider

    def process(self, request: ChatRequest, voice_mode: bool = False) -> ChatResponse:
        """
        Process a chat request end-to-end.

        Args:
            request: ChatRequest with message and optional conversation history
            voice_mode: If True, uses voice-optimized prompt (no markdown in response)
        """
        start = time.monotonic()
        history = getattr(request, "history", []) or []

        # 1. Classify intent
        intent = classify_intent(request.message)
        logger.info("AI request intent=%s voice=%s message='%s'", intent.value, voice_mode, request.message[:80])

        # 2. Retrieve official creator/project knowledge through the shared,
        # database-backed service before any LLM prompt is assembled.  Direct
        # answers prevent the provider from inferring creator facts.
        knowledge_result = get_system_knowledge_service().retrieve(request.message)
        if knowledge_result.is_official_question:
            if knowledge_result.availability == "unavailable":
                return ChatResponse(
                    intent=Intent.KNOWLEDGE,
                    answer=UNAVAILABLE[knowledge_result.locale],
                    confidence=0.0,
                    latency_ms=round((time.monotonic() - start) * 1000, 2),
                    error="Official knowledge retrieval unavailable",
                )
            if knowledge_result.records:
                return ChatResponse(
                    intent=Intent.KNOWLEDGE,
                    answer=knowledge_result.answer,
                    sources=[SourceReference(type="database", label=item.title) for item in knowledge_result.records],
                    confidence=1.0,
                    latency_ms=round((time.monotonic() - start) * 1000, 2),
                )
            return ChatResponse(
                intent=Intent.KNOWLEDGE,
                answer=NOT_DOCUMENTED[knowledge_result.locale],
                confidence=1.0,
                latency_ms=round((time.monotonic() - start) * 1000, 2),
            )

        # 3. Collect system context
        try:
            system_context = collect_system_context(request.message, locale=knowledge_result.locale)
            context_text = context_to_text(system_context)
        except Exception as exc:
            logger.error("Context collection failed: %s", exc)
            context_text = f"System context unavailable: {exc}"

        # 4. Collect intent-specific context
        try:
            extra_context = collect_intent_context(intent, request.message)
            if extra_context:
                context_text += "\n\n=== INTENT-SPECIFIC DATA ===\n"
                context_text += json.dumps(extra_context, indent=2, default=str)
        except Exception as exc:
            logger.debug("Extra context collection failed: %s", exc)

        # 5. Build prompt with history
        history_block = format_history(history)
        if voice_mode:
            prompt = VOICE_CONTEXT_TEMPLATE.format(
                context=context_text,
                history_block=history_block,
                message=request.message,
            )
            system = VOICE_SYSTEM_PROMPT
        else:
            prompt = CONTEXT_TEMPLATE.format(
                context=context_text,
                history_block=history_block,
                message=request.message,
            )
            system = SYSTEM_PROMPT

        # 6. Call LLM provider
        try:
            provider = self._get_provider()
            response_data = provider.generate_json(prompt=prompt, system_prompt=system)
            latency_ms = (time.monotonic() - start) * 1000
            return self._parse_response(response_data, intent, latency_ms)

        except Exception as exc:
            logger.error("LLM provider call failed: %s", exc)
            latency_ms = (time.monotonic() - start) * 1000
            return self._build_fallback(intent, request.message, latency_ms, str(exc))

    def generate_proactive_alert(self, alert_data: Dict[str, Any]) -> Optional[str]:
        """
        Generate a spoken announcement for a proactive alert.
        Returns plain text for TTS, or None if generation fails.
        """
        try:
            prompt = PROACTIVE_ALERT_TEMPLATE.format(
                alert_data=json.dumps(alert_data, indent=2, default=str)
            )
            provider = self._get_provider()
            result = provider.generate_json(prompt=prompt, system_prompt="")
            return result.get("announcement", "")
        except Exception as exc:
            logger.error("Proactive alert generation failed: %s", exc)
            # Build a fallback announcement from raw data
            cam = alert_data.get("camera_id", "unknown")
            level = alert_data.get("risk_level", "High")
            return f"Attention. A {level} risk alert was detected on Camera {cam}."

    def _parse_response(
        self, data: Dict[str, Any], fallback_intent: Intent, latency_ms: float
    ) -> ChatResponse:
        """Parse LLM JSON response into ChatResponse."""
        try:
            intent_str = data.get("intent", fallback_intent.value)
            try:
                intent = Intent(intent_str)
            except ValueError:
                intent = fallback_intent

            actions = [
                ActionItem(
                    type=a.get("type", "navigate"),
                    target=a.get("target", ""),
                    label=a.get("label", ""),
                )
                for a in data.get("actions", [])
                if isinstance(a, dict)
            ]

            sources = [
                SourceReference(
                    type=s.get("type", "metric"),
                    id=s.get("id"),
                    label=s.get("label", ""),
                )
                for s in data.get("sources", [])
                if isinstance(s, dict)
            ]

            return ChatResponse(
                intent=intent,
                answer=data.get("answer", "I processed your request."),
                actions=actions,
                sources=sources,
                confidence=float(data.get("confidence", 0.85)),
                latency_ms=round(latency_ms, 2),
            )
        except Exception as exc:
            logger.error("Failed to parse LLM response: %s", exc)
            return ChatResponse(
                intent=fallback_intent,
                answer=str(data) if isinstance(data, str) else "Response received.",
                confidence=0.5,
                latency_ms=round(latency_ms, 2),
            )

    def _build_fallback(
        self, intent: Intent, message: str, latency_ms: float, error: str
    ) -> ChatResponse:
        """Build a fallback response using real system data when LLM is unavailable."""
        from aegis.ai.tools import get_system_health, get_camera_status

        answer = "I couldn't reach the AI service. Here is what I can tell you from system data. "

        try:
            health = get_system_health()
            answer += f"System is {health.get('status', 'unknown')}. "
            answer += f"Database is {health.get('database', 'unknown')}. "
            answer += f"Pipeline is {health.get('pipeline', 'unknown')}. "
        except Exception:
            answer += "System health data unavailable. "

        try:
            cameras = get_camera_status()
            answer += f"Cameras: {cameras.get('online', 0)} of {cameras.get('total', 0)} online."
        except Exception:
            pass

        return ChatResponse(
            intent=intent,
            answer=answer,
            confidence=0.3,
            latency_ms=round(latency_ms, 2),
            error=f"AI service error: {error}",
            sources=[SourceReference(type="metric", label="System health fallback")],
        )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_orchestrator: Optional[AIOrchestrator] = None


def get_orchestrator() -> AIOrchestrator:
    """Get the global AI orchestrator (lazy singleton)."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AIOrchestrator()
    return _orchestrator
