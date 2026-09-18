"""Evidence-backed command execution for the Aegis Intelligence workspace."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import re
from urllib.parse import urlencode

from aegis.ai.language import ResponseLanguage, detect_response_language
from aegis.ai.orchestrator import classify_intent, get_orchestrator
from aegis.ai.schemas import (
    ChatRequest,
    Intent,
    OperatorCommandRequest,
    OperatorExecutionResponse,
    OperatorTraceStep,
    SourceReference,
)
from aegis.ai.tools import get_active_tracks, get_camera_status, get_recent_events
from aegis.intelligence.context_service import get_intelligence_context_service
from aegis.semantic.evidence_search import EvidenceSearchRequest, SearchUnavailable, evidence_search, public_evidence
from aegis.database.connection import get_db_session
from aegis.database.repositories import EventRepository


logger = logging.getLogger(__name__)


_EVIDENCE_TERMS = (
    "evidence", "find", "search", "similar", "weapon", "restricted zone",
    "دليل", "أدلة", "ابحث", "سلاح", "منطقة محظورة",
)


def _copy(language: ResponseLanguage, key: str, **values) -> str:
    text = {
        ResponseLanguage.ENGLISH: {
            "camera": "Opened {camera}. Its current runtime status is {status}.",
            "camera_missing": "I could not match that request to a configured camera.",
            "events": "Found {count} verified event records matching this request.",
            "evidence": "Found {count} indexed evidence records matching this request.",
            "tracks": "Found {count} current track records.",
            "system": "Aegis system status is {status}.",
            "analytics": "Current analytics contain {events} recent events, {tracks} tracks, and {detections} recent detections.",
            "unavailable": "The required Aegis data source is currently unavailable.",
            "understood": "Request understood",
            "camera_source": "Resolved configured camera",
            "event_source": "Queried verified event records",
            "evidence_source": "Searched the persisted evidence index",
            "track_source": "Read current tracking state",
            "system_source": "Read current system health",
            "completed": "Result ready",
        },
        ResponseLanguage.ARABIC: {
            "camera": "تم فتح {camera}. حالة التشغيل الحالية: {status}.",
            "camera_missing": "تعذر ربط الطلب بكاميرا مهيأة.",
            "events": "تم العثور على {count} سجل أحداث موثق يطابق الطلب.",
            "evidence": "تم العثور على {count} سجل أدلة مفهرس يطابق الطلب.",
            "tracks": "تم العثور على {count} سجل تتبع حالي.",
            "system": "حالة نظام Aegis هي {status}.",
            "analytics": "تتضمن التحليلات الحالية {events} أحداث حديثة و{tracks} مسارات و{detections} اكتشافات حديثة.",
            "unavailable": "مصدر بيانات Aegis المطلوب غير متاح حاليًا.",
            "understood": "تم فهم الطلب",
            "camera_source": "تم تحديد الكاميرا المهيأة",
            "event_source": "تم الاستعلام عن سجلات الأحداث الموثقة",
            "evidence_source": "تم البحث في فهرس الأدلة المحفوظة",
            "track_source": "تمت قراءة حالة التتبع الحالية",
            "system_source": "تمت قراءة صحة النظام الحالية",
            "completed": "النتيجة جاهزة",
        },
        ResponseLanguage.TURKISH: {
            "camera": "{camera} açıldı. Geçerli çalışma durumu: {status}.",
            "camera_missing": "İstek yapılandırılmış bir kamerayla eşleştirilemedi.",
            "events": "İstekle eşleşen {count} doğrulanmış olay kaydı bulundu.",
            "evidence": "İstekle eşleşen {count} dizinlenmiş kanıt kaydı bulundu.",
            "tracks": "{count} güncel iz kaydı bulundu.",
            "system": "Aegis sistem durumu: {status}.",
            "analytics": "Güncel analizlerde {events} yakın olay, {tracks} iz ve {detections} yakın algılama var.",
            "unavailable": "Gerekli Aegis veri kaynağı şu anda kullanılamıyor.",
            "understood": "İstek anlaşıldı",
            "camera_source": "Yapılandırılmış kamera çözümlendi",
            "event_source": "Doğrulanmış olay kayıtları sorgulandı",
            "evidence_source": "Kalıcı kanıt dizini arandı",
            "track_source": "Güncel izleme durumu okundu",
            "system_source": "Güncel sistem sağlığı okundu",
            "completed": "Sonuç hazır",
        },
    }[language][key]
    return text.format(**values)


def _trace(language: ResponseLanguage, source_key: str, count: int | None = None):
    label = _copy(language, source_key)
    if count is not None:
        label = f"{label} · {count}"
    return [
        OperatorTraceStep(key="understood", label=_copy(language, "understood")),
        OperatorTraceStep(key="source", label=label),
        OperatorTraceStep(key="completed", label=_copy(language, "completed")),
    ]


def _time_cutoff(message: str) -> tuple[datetime | None, str | None]:
    lowered = message.casefold()
    now = datetime.now(timezone.utc)
    if any(term in lowered for term in ("last hour", "past hour", "ساعة", "son saat")):
        return now - timedelta(hours=1), "1h"
    if any(term in lowered for term in ("today", "اليوم", "bugün")):
        return now.replace(hour=0, minute=0, second=0, microsecond=0), "today"
    if any(term in lowered for term in ("24 hours", "24h", "24 ساعة", "24 saat")):
        return now - timedelta(hours=24), "24h"
    if any(term in lowered for term in ("week", "أسبوع", "hafta")):
        return now - timedelta(days=7), "7d"
    return None, None


def _as_time(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _risk_filter(message: str) -> set[str] | None:
    lowered = message.casefold()
    if any(term in lowered for term in ("critical", "حرج", "kritik")):
        return {"CRITICAL"}
    if any(term in lowered for term in ("high risk", "high-risk", "عالي", "yüksek")):
        return {"HIGH", "CRITICAL"}
    if any(term in lowered for term in ("medium", "متوسط", "orta")):
        return {"MEDIUM", "CANDIDATE_MEDIUM"}
    if any(term in lowered for term in ("low risk", "منخفض", "düşük")):
        return {"LOW"}
    return None


def _camera_result(request: OperatorCommandRequest, language: ResponseLanguage):
    payload = get_camera_status()
    cameras = payload.get("cameras", []) if payload.get("availability") == "available" else []
    lowered = request.message.casefold()
    match = next(
        (
            camera
            for camera in cameras
            if camera.get("camera_id")
            and str(camera["camera_id"]).casefold() in lowered
        ),
        None,
    )
    if match is None:
        match = next((camera for camera in cameras if camera.get("name") and str(camera["name"]).casefold() in lowered), None)
    if match is None:
        number_match = re.search(r"(?:camera|cam|كاميرا)\s*#?\s*(\d+)", lowered)
        if number_match:
            number = int(number_match.group(1))
            match = next((camera for camera in cameras if str(camera.get("camera_id")) == str(number)), None)
            if match is None and 1 <= number <= len(cameras):
                match = sorted(cameras, key=lambda item: str(item.get("camera_id")))[number - 1]
    if match is None:
        return OperatorExecutionResponse(
            action="CAMERA_OPEN", intent=Intent.CAMERA, panel="camera", answer=_copy(language, "camera_missing"),
            result={"cameras": cameras}, trace=_trace(language, "camera_source", len(cameras)), response_language=language,
        )
    camera_id = str(match["camera_id"])
    target = f"/cameras?{urlencode({'camera': camera_id, 'view': 'focus'})}"
    return OperatorExecutionResponse(
        action="CAMERA_OPEN", intent=Intent.CAMERA, panel="camera", target=target,
        answer=_copy(language, "camera", camera=match.get("name") or camera_id, status=match.get("status") or "unknown"),
        result={"camera": match}, sources=[SourceReference(type="camera", id=camera_id, label=match.get("name") or camera_id)],
        trace=_trace(language, "camera_source", 1), response_language=language,
    )


def _event_result(request: OperatorCommandRequest, language: ResponseLanguage):
    events = get_recent_events(limit=100)
    cutoff, range_key = _time_cutoff(request.message)
    risk_levels = _risk_filter(request.message)
    filtered = []
    for event in events:
        if risk_levels and str(event.get("risk_level") or "").upper() not in risk_levels:
            continue
        timestamp = _as_time(event.get("timestamp"))
        if cutoff and (timestamp is None or timestamp < cutoff):
            continue
        filtered.append(event)
    if re.search(r"highest[- ]risk|most dangerous", request.message, re.I):
        rank = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "CANDIDATE_MEDIUM": 1, "LOW": 0}
        filtered.sort(key=lambda event: (rank.get(str(event.get("risk_level", "")).upper(), -1), float(event.get("risk_score") or 0)), reverse=True)
        filtered = filtered[:1]
    query = {"range": range_key} if range_key else {}
    if risk_levels:
        query["risk"] = "critical" if risk_levels == {"CRITICAL"} else "high" if "HIGH" in risk_levels else next(iter(risk_levels)).lower()
    target = f"/events?{urlencode(query)}" if query else "/events"
    return OperatorExecutionResponse(
        action="RISK_QUERY" if risk_levels else "EVENT_SEARCH", intent=Intent.RISK if risk_levels else Intent.INVESTIGATION,
        panel="events", target=target, answer=_copy(language, "events", count=len(filtered)),
        result={"events": filtered[:12], "total": len(filtered), "range": range_key, "risk_levels": sorted(risk_levels or [])},
        sources=[SourceReference(type="event", id=str(event.get("event_id") or event.get("id") or "") or None, label=str(event.get("message") or event.get("event_type") or "event")) for event in filtered[:8]],
        trace=_trace(language, "event_source", len(filtered)), response_language=language,
    )


def _evidence_result(request: OperatorCommandRequest, language: ResponseLanguage):
    if "related" in request.message.casefold():
        if not request.previous_evidence_id:
            return OperatorExecutionResponse(action="EVIDENCE_SEARCH", intent=Intent.SEARCH, panel="evidence", answer="Select an event first so I can show its evidence.", result={"evidence": [], "total": 0}, response_language=language)
        # Resolve the selected opaque ID again; never trust browser-supplied evidence.
        with get_db_session() as session:
            event = EventRepository(session).get_by_event_id(request.previous_evidence_id)
            items = [public_evidence(event)] if event else []
        return OperatorExecutionResponse(action="EVIDENCE_SEARCH", intent=Intent.SEARCH, panel="evidence", answer=_copy(language, "evidence", count=len(items)), result={"evidence": items, "total": len(items)}, target=f"/events?{urlencode({'event': request.previous_evidence_id})}", trace=_trace(language, "evidence_source", len(items)), response_language=language)
    similar = request.previous_evidence_id if "similar" in request.message.casefold() else None
    semantic_request = EvidenceSearchRequest(
        query="" if similar else request.message,
        similar_to=similar,
        start=_time_cutoff(request.message)[0],
        risk_level="CRITICAL" if _risk_filter(request.message) == {"CRITICAL"} else None,
        page=1, page_size=8, min_similarity=0.18,
    )
    search = evidence_search.search(semantic_request)
    items = search["results"]
    target = f"/semantic?{urlencode({'similar': similar})}" if similar else f"/semantic?{urlencode({'q': request.message})}"
    return OperatorExecutionResponse(
        action="EVIDENCE_SEARCH", intent=Intent.SEARCH, panel="evidence", target=target,
        answer=_copy(language, "evidence", count=search["total"]),
        result={"evidence": items, "total": search["total"], "pending_evidence": search["pending_evidence"]},
        sources=[SourceReference(type="event", id=item["event_id"], label=item.get("reason") or item.get("event_type") or item["event_id"]) for item in items],
        trace=_trace(language, "evidence_source", search["total"]), response_language=language,
    )


def _context_result(intent: Intent, language: ResponseLanguage, request: OperatorCommandRequest | None = None):
    context = get_intelligence_context_service().build().model_dump(by_alias=True, mode="json")
    if intent == Intent.TRACKING:
        tracks = get_active_tracks()
        rows = tracks.get("recent_detections", []) if tracks.get("availability") == "available" else []
        track_id = request.selected_track_id if request and "this person" in request.message.casefold() else None
        if request:
            explicit = re.search(r"\btrack\s+([\w:-]+)", request.message, re.I)
            if explicit and explicit.group(1).lower() not in {"this", "person", "details", "evidence"}:
                track_id = explicit.group(1)
        if track_id:
            rows = [row for row in rows if str(row.get("track_id") or row.get("id")) == track_id]
        count = len(rows)
        return OperatorExecutionResponse(
            action="TRACK_LOOKUP", intent=intent, panel="tracks", target="/tracks",
            answer=_copy(language, "tracks", count=count), result={"tracks": rows, "summary": tracks},
            trace=_trace(language, "track_source", tracks.get("total_recent_tracks", len(rows))), response_language=language,
        )
    if intent == Intent.ANALYTICS:
        detections = context["detections"].get("recentCount")
        answer = _copy(language, "analytics", events=len(context["events"]), tracks=len(context["tracks"]), detections=detections if detections is not None else "—")
        return OperatorExecutionResponse(action="ANALYTICS_QUERY", intent=intent, panel="analytics", target="/analytics", answer=answer, result={"context": context}, trace=_trace(language, "system_source"), response_language=language)
    return OperatorExecutionResponse(
        action="SYSTEM_STATUS", intent=Intent.HEALTH, panel="system", target="/analytics",
        answer=_copy(language, "system", status=context["overall"]["status"]), result={"context": context},
        trace=_trace(language, "system_source"), response_language=language,
    )


def execute_operator_command(request: OperatorCommandRequest) -> OperatorExecutionResponse:
    language = detect_response_language(request.message)
    lowered = request.message.casefold()
    intent = classify_intent(request.message)
    try:
        if any(term in lowered for term in _EVIDENCE_TERMS) and not any(term in lowered for term in ("open camera", "افتح الكاميرا")):
            return _evidence_result(request, language)
        if intent == Intent.CAMERA or any(term in lowered for term in ("camera", "cam ", "كاميرا")):
            return _camera_result(request, language)
        if intent in {Intent.RISK, Intent.INVESTIGATION, Intent.INCIDENT} or _risk_filter(request.message) or any(term in lowered for term in ("event", "حدث", "أحداث")):
            return _event_result(request, language)
        if intent in {Intent.TRACKING, Intent.ANALYTICS, Intent.HEALTH}:
            if intent == Intent.TRACKING and "this person" in lowered and not request.selected_track_id:
                return OperatorExecutionResponse(action="TRACK_LOOKUP", intent=intent, panel="tracks", answer="Select a track with an observed identifier before asking me to track this person.", result={"tracks": []}, response_language=language)
            return _context_result(intent, language, request)

        chat = get_orchestrator().process(ChatRequest(message=request.message))
        safe_target = next((item.target for item in chat.actions if item.type == "navigate" and item.target.split("?", 1)[0] in {"/cameras", "/events", "/semantic", "/tracks", "/analytics"}), None)
        return OperatorExecutionResponse(
            action="ANSWER", intent=chat.intent, panel="answer", target=safe_target, answer=chat.answer,
            sources=chat.sources, result={"confidence": chat.confidence},
            trace=[OperatorTraceStep(key="understood", label=_copy(language, "understood")), OperatorTraceStep(key="completed", label=_copy(language, "completed"))],
            response_language=language, error=chat.error,
        )
    except (SearchUnavailable, LookupError):
        return OperatorExecutionResponse(
            action="ERROR", intent=intent, panel="error", answer=_copy(language, "unavailable"),
            trace=[OperatorTraceStep(key="understood", label=_copy(language, "understood")), OperatorTraceStep(key="source", label=_copy(language, "unavailable"), status="error")],
            response_language=language, error="Required operational source unavailable",
        )
    except Exception:
        logger.exception("Operator command execution failed for intent %s", intent.value)
        return OperatorExecutionResponse(
            action="ERROR",
            intent=intent,
            panel="error",
            answer=_copy(language, "unavailable"),
            trace=[
                OperatorTraceStep(key="understood", label=_copy(language, "understood")),
                OperatorTraceStep(
                    key="source",
                    label=_copy(language, "unavailable"),
                    status="error",
                ),
            ],
            response_language=language,
            error="Operator execution unavailable",
        )
