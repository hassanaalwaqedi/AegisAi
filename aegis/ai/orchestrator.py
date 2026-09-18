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

from aegis.ai.language import (
    ResponseLanguage,
    detect_response_language,
    response_language_instruction,
)
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
        response_language = detect_response_language(request.message)

        # 1. Classify intent
        intent = classify_intent(request.message)
        logger.info("AI request intent=%s voice=%s response_language=%s message='%s'", intent.value, voice_mode, response_language.value, request.message[:80])

        # 2. Retrieve official creator/project knowledge through the shared,
        # database-backed service before any LLM prompt is assembled.  Direct
        # answers prevent the provider from inferring creator facts.
        knowledge_result = get_system_knowledge_service().retrieve(
            request.message,
            locale=response_language.locale,
        )
        if knowledge_result.is_official_question:
            if knowledge_result.availability == "unavailable":
                return ChatResponse(
                    intent=Intent.KNOWLEDGE,
                    answer=UNAVAILABLE[knowledge_result.locale],
                    confidence=0.0,
                    latency_ms=round((time.monotonic() - start) * 1000, 2),
                    error="Official knowledge retrieval unavailable",
                    response_language=response_language,
                )
            if knowledge_result.records:
                return ChatResponse(
                    intent=Intent.KNOWLEDGE,
                    answer=knowledge_result.answer,
                    sources=[SourceReference(type="database", label=item.title) for item in knowledge_result.records],
                    confidence=1.0,
                    latency_ms=round((time.monotonic() - start) * 1000, 2),
                    response_language=response_language,
                )
            return ChatResponse(
                intent=Intent.KNOWLEDGE,
                answer=NOT_DOCUMENTED[knowledge_result.locale],
                confidence=1.0,
                latency_ms=round((time.monotonic() - start) * 1000, 2),
                response_language=response_language,
            )

        # 3. Collect system context
        try:
            system_context = collect_system_context(request.message, locale=response_language.locale)
            context_text = context_to_text(system_context)
        except Exception as exc:
            logger.error("Context collection failed: %s", exc)
            system_context = {}
            context_text = f"System context unavailable: {exc}"

        unavailable_reason = self._operational_source_unavailable(intent, system_context)
        if unavailable_reason:
            return ChatResponse(
                intent=intent,
                answer=self._unavailable_answer(response_language),
                confidence=1.0,
                latency_ms=round((time.monotonic() - start) * 1000, 2),
                error=unavailable_reason,
                response_language=response_language,
            )

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
                response_language_instruction=response_language_instruction(response_language),
            )
            system = VOICE_SYSTEM_PROMPT
        else:
            prompt = CONTEXT_TEMPLATE.format(
                context=context_text,
                history_block=history_block,
                message=request.message,
                response_language_instruction=response_language_instruction(response_language),
            )
            system = SYSTEM_PROMPT

        # 6. Call LLM provider
        try:
            provider = self._get_provider()
            response_data = provider.generate_json(prompt=prompt, system_prompt=system)
            latency_ms = (time.monotonic() - start) * 1000
            return self._parse_response(response_data, intent, latency_ms, response_language)

        except Exception as exc:
            logger.error("LLM provider call failed: %s", exc)
            latency_ms = (time.monotonic() - start) * 1000
            return self._build_fallback(
                intent,
                request.message,
                latency_ms,
                str(exc),
                response_language=response_language,
            )

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
        self,
        data: Dict[str, Any],
        fallback_intent: Intent,
        latency_ms: float,
        response_language: ResponseLanguage = ResponseLanguage.ENGLISH,
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
                response_language=response_language,
            )
        except Exception as exc:
            logger.error("Failed to parse LLM response: %s", exc)
            return ChatResponse(
                intent=fallback_intent,
                answer=str(data) if isinstance(data, str) else self._localized_copy(response_language, "response_received"),
                confidence=0.5,
                latency_ms=round(latency_ms, 2),
                response_language=response_language,
            )

    @staticmethod
    def _operational_source_unavailable(intent: Intent, context: Dict[str, Any]) -> Optional[str]:
        """Identify a required source that cannot support an operational answer."""
        source_for_intent = {
            Intent.RISK: "active_alerts",
            Intent.CAMERA: "cameras",
            Intent.TRACKING: "tracks",
            Intent.HEALTH: "system_health",
            Intent.ANALYTICS: "pipeline",
        }
        source_name = source_for_intent.get(intent)
        if source_name is None:
            return None
        source = context.get(source_name)
        if isinstance(source, dict) and source.get("availability") == "unavailable":
            return str(source.get("reason") or f"{source_name} is unavailable")
        return None

    @staticmethod
    def _unavailable_answer(language: ResponseLanguage) -> str:
        """Localized, deterministic refusal for unavailable operational data."""
        return {
            ResponseLanguage.ENGLISH: "I couldn't verify this information because the required Aegis data source is currently unavailable.",
            ResponseLanguage.ARABIC: "\u0644\u0627 \u0623\u0633\u062a\u0637\u064a\u0639 \u062a\u0623\u0643\u064a\u062f \u0647\u0630\u0647 \u0627\u0644\u0645\u0639\u0644\u0648\u0645\u0627\u062a \u0644\u0623\u0646 \u0645\u0635\u062f\u0631 \u0628\u064a\u0627\u0646\u0627\u062a Aegis \u0627\u0644\u0645\u0637\u0644\u0648\u0628 \u063a\u064a\u0631 \u0645\u062a\u0627\u062d \u062d\u0627\u0644\u064a\u0627\u064b.",
            ResponseLanguage.TURKISH: "Gerekli Aegis veri kayna\u011f\u0131 \u015fu anda kullan\u0131lamad\u0131\u011f\u0131 i\u00e7in bu bilgiyi do\u011frulayamad\u0131m.",
        }[language]

    def _build_fallback(
        self,
        intent: Intent,
        message: str,
        latency_ms: float,
        error: str,
        *,
        response_language: ResponseLanguage | None = None,
    ) -> ChatResponse:
        """Build a fallback response using real system data when LLM is unavailable."""
        from aegis.ai.tools import get_active_alerts, get_camera_status, get_system_health

        response_language = response_language or detect_response_language(message)
        answer = self._localized_copy(response_language, "preamble")
        sources: List[SourceReference] = []

        if intent == Intent.RISK:
            try:
                alerts = get_active_alerts(limit=10)
                high_priority = [
                    alert for alert in alerts
                    if str(alert.get("risk_level") or "").upper() in {"HIGH", "CRITICAL"}
                ]
                critical_count = sum(
                    str(alert.get("risk_level") or "").upper() == "CRITICAL"
                    for alert in high_priority
                )
                high_count = sum(
                    str(alert.get("risk_level") or "").upper() == "HIGH"
                    for alert in high_priority
                )
                if high_priority:
                    latest = high_priority[-1]
                    level = str(latest.get("risk_level") or "HIGH").upper()
                    camera_id = str(latest.get("camera_id") or self._localized_copy(response_language, "unknown_camera"))
                    level_label = self._localized_copy(response_language, f"level_{level.lower()}")
                    answer += self._localized_copy(response_language, "risk_summary").format(
                        critical=critical_count,
                        high=high_count,
                        level=level_label,
                        camera=camera_id,
                    )
                    sources = [
                        SourceReference(
                            type="alert",
                            id=str(alert.get("event_id") or alert.get("id") or "") or None,
                            label=str(alert.get("message") or alert.get("risk_level") or "risk alert"),
                        )
                        for alert in high_priority[:5]
                    ]
                else:
                    answer += self._localized_copy(response_language, "no_active_risk")
            except Exception:
                answer += self._localized_copy(response_language, "risk_unavailable")
            return ChatResponse(
                intent=intent,
                answer=answer,
                confidence=0.75,
                latency_ms=round(latency_ms, 2),
                error=f"AI service error: {error}",
                sources=sources,
                response_language=response_language,
            )

        try:
            health = get_system_health()
            answer += self._localized_copy(response_language, "health_summary").format(
                system=health.get("status", "unknown"),
                database=health.get("database", "unknown"),
                pipeline=health.get("pipeline", "unknown"),
            )
        except Exception:
            answer += self._localized_copy(response_language, "health_unavailable")

        try:
            cameras = get_camera_status()
            answer += self._localized_copy(response_language, "camera_summary").format(
                online=cameras.get("online", 0),
                total=cameras.get("total", 0),
            )
        except Exception:
            pass

        return ChatResponse(
            intent=intent,
            answer=answer,
            confidence=0.3,
            latency_ms=round(latency_ms, 2),
            error=f"AI service error: {error}",
            sources=[SourceReference(type="metric", label="System health fallback")],
            response_language=response_language,
        )

    @staticmethod
    def _localized_copy(language: ResponseLanguage, key: str) -> str:
        copy = {
            ResponseLanguage.ENGLISH: {
                "preamble": "The AI provider is unavailable, so this response uses verified Aegis system data. ",
                "response_received": "Response received.",
                "unknown_camera": "an unknown camera",
                "level_high": "high",
                "level_critical": "critical",
                "risk_summary": "Verified active risk alerts: {critical} critical and {high} high. Latest {level} alert is near {camera}. ",
                "no_active_risk": "No fresh, unacknowledged HIGH or CRITICAL risk alerts are currently active.",
                "risk_unavailable": "Verified active-risk data is temporarily unavailable.",
                "health_summary": "System is {system}. Database is {database}. Pipeline is {pipeline}. ",
                "health_unavailable": "System health data is temporarily unavailable. ",
                "camera_summary": "Cameras: {online} of {total} online.",
            },
            ResponseLanguage.ARABIC: {
                "preamble": "موفّر الذكاء الاصطناعي غير متاح، لذا يعتمد هذا الرد على بيانات Aegis الموثقة. ",
                "response_received": "تم استلام الرد.",
                "unknown_camera": "كاميرا غير معروفة",
                "level_high": "عالي الخطورة",
                "level_critical": "حرج",
                "risk_summary": "تنبيهات المخاطر النشطة الموثقة: {critical} حرجة و{high} عالية. أحدث تنبيه {level} قرب الكاميرا {camera}. ",
                "no_active_risk": "لا توجد حالياً تنبيهات مخاطر عالية أو حرجة حديثة وغير مؤكدة.",
                "risk_unavailable": "بيانات المخاطر النشطة الموثقة غير متاحة مؤقتاً.",
                "health_summary": "حالة النظام: {system}. حالة قاعدة البيانات: {database}. حالة خط المعالجة: {pipeline}. ",
                "health_unavailable": "بيانات صحة النظام غير متاحة مؤقتاً. ",
                "camera_summary": "الكاميرات المتصلة: {online} من {total}.",
            },
            ResponseLanguage.TURKISH: {
                "preamble": "Yapay zekâ sağlayıcısı kullanılamıyor; bu yanıt doğrulanmış Aegis sistem verilerini kullanır. ",
                "response_received": "Yanıt alındı.",
                "unknown_camera": "bilinmeyen bir kamera",
                "level_high": "yüksek",
                "level_critical": "kritik",
                "risk_summary": "Doğrulanmış etkin risk uyarıları: {critical} kritik ve {high} yüksek. En son {level} uyarısı {camera} kamerası yakınında. ",
                "no_active_risk": "Şu anda yeni ve onaylanmamış YÜKSEK veya KRİTİK risk uyarısı yok.",
                "risk_unavailable": "Doğrulanmış etkin risk verileri geçici olarak kullanılamıyor.",
                "health_summary": "Sistem durumu: {system}. Veritabanı: {database}. İşlem hattı: {pipeline}. ",
                "health_unavailable": "Sistem sağlığı verileri geçici olarak kullanılamıyor. ",
                "camera_summary": "Çevrimiçi kameralar: {online}/{total}.",
            },
        }
        return copy[language][key]


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
