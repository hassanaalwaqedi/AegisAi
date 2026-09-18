"""Read-only, source-backed tool registry used by Gemini Live sessions.

Gemini receives only these minimal results. It never receives a database
session, camera-manager object, internal route, credential, or callable that
can mutate Aegis state.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional

from aegis.intelligence.context_schemas import Availability, IntelligenceContext
from aegis.intelligence.event_access import load_persisted_event_records, merge_event_records
from aegis.intelligence.live_schemas import (
    LiveCitation,
    LiveToolResult,
    SafeUICommand,
    ToolAuditRecord,
    UICommandKind,
)

logger = logging.getLogger(__name__)


class ToolNotAllowedError(ValueError):
    """Raised when a model attempts a capability outside the Live allowlist."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _json_value(value: Any) -> Any:
    """Keep provider tool responses serialisable without leaking runtime objects."""
    if hasattr(value, "model_dump"):
        return value.model_dump(by_alias=True, mode="json")
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


class LiveToolRegistry:
    """Session-scoped allowlist with auditable, source-fresh outputs."""

    ALLOWED_TOOLS = {
        "get_intelligence_context",
        "get_live_camera_status",
        "get_active_risk_alerts",
        "get_recent_events",
        "get_track_details",
        "get_risk_explanation",
        "search_live_evidence",
        "get_pipeline_health",
        "get_official_system_knowledge",
        "open_authorised_evidence",
        "project_operator_result",
    }

    def __init__(
        self,
        *,
        session_id: str,
        operator_id: str,
        correlation_id: str,
        context_getter: Optional[Callable[[], IntelligenceContext]] = None,
        audit_sink: Optional[Callable[[ToolAuditRecord], None]] = None,
    ) -> None:
        self.session_id = session_id
        self.operator_id = operator_id
        self.correlation_id = correlation_id
        self._context_getter = context_getter or self._default_context
        self._audit_sink = audit_sink or self._log_audit
        self._ephemeral_evidence: Dict[str, LiveCitation] = {}
        from aegis.intelligence.operator_scene import OperatorSceneContext
        self.scene_context = OperatorSceneContext()

    @staticmethod
    def _default_context() -> IntelligenceContext:
        from aegis.intelligence.context_service import get_intelligence_context_service

        return get_intelligence_context_service().build()

    @staticmethod
    def declarations() -> List[Dict[str, Any]]:
        """Provider-neutral Gemini function declarations for the strict allowlist."""
        return [
            {
                "name": "project_operator_result",
                "description": "Present real cameras, events, risks, evidence, tracks, or system status inside the persistent Intelligence scene. Use for show/open/find/track commands and follow-ups. Pass the user's complete original request verbatim, including ordinal references such as 'the second one'; the server resolves current scene selection. Summarize only the returned answer and records. This tool does not navigate or mutate operational state.",
                "parameters": {"type": "OBJECT", "properties": {"message": {"type": "STRING", "minLength": 2, "maxLength": 1000}}, "required": ["message"]},
            },
            {
                "name": "get_intelligence_context",
                "description": "Get the current source-fresh Aegis operational context before answering broad health or status questions.",
                "parameters": {"type": "OBJECT", "properties": {}},
            },
            {
                "name": "get_live_camera_status",
                "description": "Get current runtime camera states and observed timestamps. Never infer camera counts without this tool.",
                "parameters": {"type": "OBJECT", "properties": {}},
            },
            {
                "name": "get_active_risk_alerts",
                "description": "Get currently active risk alerts and their evidence references.",
                "parameters": {"type": "OBJECT", "properties": {}},
            },
            {
                "name": "get_recent_events",
                "description": "Get genuinely available recent events from the current intelligence context.",
                "parameters": {"type": "OBJECT", "properties": {"limit": {"type": "INTEGER", "minimum": 1, "maximum": 50}}},
            },
            {
                "name": "get_track_details",
                "description": "Get verified details for one currently available track.",
                "parameters": {"type": "OBJECT", "properties": {"track_id": {"type": "STRING"}}, "required": ["track_id"]},
            },
            {
                "name": "get_risk_explanation",
                "description": "Get source-provided risk fields for a currently available event or track. It does not infer intent or identity.",
                "parameters": {"type": "OBJECT", "properties": {"event_id": {"type": "STRING"}, "track_id": {"type": "STRING"}}},
            },
            {
                "name": "search_live_evidence",
                "description": "Perform a read-only search against the live semantic-evidence engine when it is available.",
                "parameters": {"type": "OBJECT", "properties": {"query": {"type": "STRING", "minLength": 1, "maxLength": 240}, "camera_id": {"type": "STRING"}, "time_range": {"type": "STRING", "maxLength": 100}}, "required": ["query"]},
            },
            {
                "name": "get_pipeline_health",
                "description": "Get current source-backed pipeline, database, Redis, model, and event-stream health.",
                "parameters": {"type": "OBJECT", "properties": {}},
            },
            {
                "name": "get_official_system_knowledge",
                "description": "Retrieve active public Aegis creator and project facts from the official database. Use for creator, purpose, architecture, capability, technology, security, or limitation questions.",
                "parameters": {"type": "OBJECT", "properties": {"query": {"type": "STRING", "minLength": 1, "maxLength": 500}, "locale": {"type": "STRING", "enum": ["ar", "en", "tr"]}}, "required": ["query"]},
            },
            {
                "name": "open_authorised_evidence",
                "description": "Resolve an evidence ID returned by an Aegis tool into a safe UI command. Never construct a URL.",
                "parameters": {"type": "OBJECT", "properties": {"evidence_id": {"type": "STRING"}}, "required": ["evidence_id"]},
            },
        ]

    def execute(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> LiveToolResult:
        if name not in self.ALLOWED_TOOLS:
            raise ToolNotAllowedError(f"Tool '{name}' is not authorised for Gemini Live.")

        arguments = arguments if isinstance(arguments, dict) else {}
        started = time.monotonic()
        try:
            handler = getattr(self, f"_{name}")
            result = handler(arguments)
        except ToolNotAllowedError:
            raise
        except Exception as exc:
            logger.exception("Live tool failed: %s", name)
            result = LiveToolResult(
                tool=name,
                availability=Availability.UNAVAILABLE,
                observed_at=_utc_now(),
                reason=f"Verified source could not be read: {type(exc).__name__}.",
            )

        audit = ToolAuditRecord(
            tool=name,
            correlation_id=self.correlation_id,
            operator_id=self.operator_id,
            session_id=self.session_id,
            arguments=_json_value(arguments),
            result_status=result.availability,
            latency_ms=round((time.monotonic() - started) * 1000, 2),
            evidence_ids=[citation.evidence_id for citation in result.citations],
            observed_at=_utc_now(),
        )
        self._audit_sink(audit)
        return result

    def _project_operator_result(self, arguments: Dict[str, Any]) -> LiveToolResult:
        from aegis.intelligence.operator_scene import execute_scene_command, OperatorSceneContext
        message = str(arguments.get("message", ""))[:1000]
        execution = execute_scene_command(message, self.scene_context)
        data = execution.model_dump(mode="json")
        rows = next((execution.result[key] for key in ("events", "evidence", "tracks", "cameras") if isinstance(execution.result.get(key), list)), [])
        if execution.result.get("camera"):
            rows = [execution.result["camera"]]
        ids = [str(row.get("event_id") or row.get("track_id") or row.get("camera_id") or row.get("id") or "") for row in rows if isinstance(row, dict)]
        self.scene_context = OperatorSceneContext(panel=execution.panel, query=message[:500], ordered_ids=ids[:50], selected_id=ids[0] if ids else None)
        return LiveToolResult(tool="project_operator_result", availability=Availability.UNAVAILABLE if execution.error else Availability.LIVE, observed_at=_utc_now(), data={"projection": data})

    def _context(self) -> IntelligenceContext:
        return self._context_getter()

    def _citation(
        self,
        *,
        kind: str,
        item_id: str,
        label: str,
        availability: Availability,
        camera_id: Optional[str] = None,
        observed_at: Optional[datetime] = None,
    ) -> LiveCitation:
        citation = LiveCitation(
            evidence_id=f"{kind}:{item_id}",
            kind=kind,
            label=label,
            camera_id=camera_id,
            observed_at=observed_at,
            availability=availability,
        )
        self._ephemeral_evidence[citation.evidence_id] = citation
        return citation

    def _nested_citations(self, evidence: Iterable[Any], freshness: Any) -> List[LiveCitation]:
        citations: List[LiveCitation] = []
        for ref in evidence:
            kind = getattr(ref, "kind", None)
            item_id = getattr(ref, "id", None)
            if not kind or not item_id:
                continue
            citations.append(
                self._citation(
                    kind=kind,
                    item_id=str(item_id),
                    label=getattr(ref, "label", f"{kind} {item_id}"),
                    availability=getattr(freshness, "status", Availability.UNAVAILABLE),
                    camera_id=getattr(ref, "camera_id", None),
                    observed_at=getattr(ref, "occurred_at", None) or getattr(freshness, "observed_at", None),
                )
            )
        return citations

    def _get_intelligence_context(self, _: Dict[str, Any]) -> LiveToolResult:
        context = self._context()
        citation = self._citation(
            kind="health",
            item_id="intelligence-context",
            label="Intelligence context snapshot",
            availability=context.overall.status,
            observed_at=context.generated_at,
        )
        return LiveToolResult(
            tool="get_intelligence_context",
            availability=context.overall.status,
            observed_at=context.generated_at,
            reason="; ".join(context.overall.degraded_reasons) or None,
            data=context.model_dump(by_alias=True, mode="json"),
            citations=[citation],
        )

    def _get_live_camera_status(self, _: Dict[str, Any]) -> LiveToolResult:
        context = self._context()
        cameras = context.cameras
        citations = [
            self._citation(
                kind="camera",
                item_id=item.camera_id,
                label=item.name or f"Camera {item.camera_id}",
                availability=item.runtime,
                camera_id=item.camera_id,
                observed_at=item.freshness.observed_at,
            )
            for item in cameras.items
        ]
        return LiveToolResult(
            tool="get_live_camera_status",
            availability=cameras.freshness.status,
            observed_at=cameras.freshness.observed_at,
            reason=cameras.freshness.reason,
            data={
                "total": cameras.total,
                "online": cameras.online,
                "offline": cameras.offline,
                "stale": cameras.stale,
                "unavailable": cameras.unavailable,
                "cameras": [_json_value(item) for item in cameras.items],
            },
            citations=citations,
            ui_command=SafeUICommand(kind=UICommandKind.OPEN_CAMERAS),
        )

    def _get_active_risk_alerts(self, _: Dict[str, Any]) -> LiveToolResult:
        context = self._context()
        alerts = context.alerts
        citations: List[LiveCitation] = []
        entries: List[Dict[str, Any]] = []
        for alert in alerts.items:
            alert_citation = self._citation(
                kind="alert",
                item_id=alert.alert_id,
                label=f"Risk alert {alert.alert_id}",
                availability=alert.freshness.status,
                observed_at=alert.freshness.observed_at,
            )
            item_citations = [alert_citation, *self._nested_citations(alert.evidence, alert.freshness)]
            citations.extend(item_citations)
            entries.append({
                "alertId": alert.alert_id,
                "level": alert.level,
                "acknowledged": alert.acknowledged,
                "freshness": _json_value(alert.freshness),
                "evidenceIds": [citation.evidence_id for citation in item_citations],
            })
        return LiveToolResult(
            tool="get_active_risk_alerts",
            availability=alerts.freshness.status,
            observed_at=alerts.freshness.observed_at,
            reason=alerts.freshness.reason,
            data={"activeCount": alerts.active_count, "alerts": entries},
            citations=citations,
            ui_command=SafeUICommand(kind=UICommandKind.SHOW_RISK_EVIDENCE),
        )

    def _get_recent_events(self, arguments: Dict[str, Any]) -> LiveToolResult:
        context = self._context()
        limit = arguments.get("limit", 10)
        if not isinstance(limit, int):
            limit = 10
        limit = max(1, min(limit, 50))
        entries: List[Dict[str, Any]] = []
        citations: List[LiveCitation] = []
        for event in context.events[:limit]:
            event_citation = self._citation(
                kind="event",
                item_id=event.event_id,
                label=f"Event {event.event_id}",
                availability=event.freshness.status,
                observed_at=event.freshness.observed_at,
            )
            item_citations = [event_citation, *self._nested_citations(event.evidence, event.freshness)]
            citations.extend(item_citations)
            entries.append({
                "eventId": event.event_id,
                "summary": event.summary,
                "riskScore": event.risk_score,
                "riskLevel": event.risk_level,
                "freshness": _json_value(event.freshness),
                "evidenceIds": [citation.evidence_id for citation in item_citations],
            })
        return LiveToolResult(
            tool="get_recent_events",
            availability=context.overall.status,
            observed_at=context.generated_at,
            reason=None if context.events else "No recent events are currently available from the configured runtime sources.",
            data={"events": entries},
            citations=citations,
        )

    def _get_track_details(self, arguments: Dict[str, Any]) -> LiveToolResult:
        track_id = str(arguments.get("track_id", "")).strip()
        context = self._context()
        track = next((item for item in context.tracks if item.track_id == track_id), None)
        if track is None:
            return LiveToolResult(
                tool="get_track_details",
                availability=Availability.UNAVAILABLE,
                observed_at=context.generated_at,
                reason="The requested track is not present in the current verified runtime snapshot.",
            )
        citation = self._citation(
            kind="track",
            item_id=track.track_id,
            label=f"{track.class_name} track {track.track_id}",
            availability=track.freshness.status,
            camera_id=track.camera_id,
            observed_at=track.freshness.observed_at,
        )
        citations = [citation, *self._nested_citations(track.evidence, track.freshness)]
        return LiveToolResult(
            tool="get_track_details",
            availability=track.freshness.status,
            observed_at=track.freshness.observed_at,
            reason=track.freshness.reason,
            data={
                "trackId": track.track_id,
                "cameraId": track.camera_id,
                "className": track.class_name,
                "riskScore": track.risk_score,
                "verificationStatus": track.verification_status,
                "freshness": _json_value(track.freshness),
            },
            citations=citations,
            ui_command=SafeUICommand(kind=UICommandKind.SHOW_TRACK_EVIDENCE, target_id=track.track_id, camera_id=track.camera_id),
        )

    def _get_risk_explanation(self, arguments: Dict[str, Any]) -> LiveToolResult:
        context = self._context()
        event_id = str(arguments.get("event_id", "")).strip()
        track_id = str(arguments.get("track_id", "")).strip()
        event = next((item for item in context.events if item.event_id == event_id), None) if event_id else None
        track = next((item for item in context.tracks if item.track_id == track_id), None) if track_id else None
        if event is None and track is None:
            return LiveToolResult(
                tool="get_risk_explanation",
                availability=Availability.UNAVAILABLE,
                observed_at=context.generated_at,
                reason="No requested event or track exists in the current verified runtime snapshot.",
            )
        if event is not None:
            citation = self._citation(kind="event", item_id=event.event_id, label=f"Event {event.event_id}", availability=event.freshness.status, observed_at=event.freshness.observed_at)
            citations = [citation, *self._nested_citations(event.evidence, event.freshness)]
            return LiveToolResult(
                tool="get_risk_explanation",
                availability=event.freshness.status,
                observed_at=event.freshness.observed_at,
                reason=event.freshness.reason,
                data={"eventId": event.event_id, "riskScore": event.risk_score, "riskLevel": event.risk_level, "sourceSummary": event.summary},
                citations=citations,
                ui_command=SafeUICommand(kind=UICommandKind.SHOW_RISK_EVIDENCE, target_id=event.event_id),
            )
        assert track is not None
        citation = self._citation(kind="track", item_id=track.track_id, label=f"{track.class_name} track {track.track_id}", availability=track.freshness.status, camera_id=track.camera_id, observed_at=track.freshness.observed_at)
        citations = [citation, *self._nested_citations(track.evidence, track.freshness)]
        return LiveToolResult(
            tool="get_risk_explanation",
            availability=track.freshness.status,
            observed_at=track.freshness.observed_at,
            reason=track.freshness.reason,
            data={"trackId": track.track_id, "riskScore": track.risk_score, "verificationStatus": track.verification_status},
            citations=citations,
            ui_command=SafeUICommand(kind=UICommandKind.SHOW_RISK_EVIDENCE, target_id=track.track_id, camera_id=track.camera_id),
        )

    def _search_live_evidence(self, arguments: Dict[str, Any]) -> LiveToolResult:
        query = str(arguments.get("query", "")).strip()
        context = self._context()
        if not query:
            return LiveToolResult(tool="search_live_evidence", availability=Availability.UNAVAILABLE, observed_at=context.generated_at, reason="A non-empty evidence query is required.")
        if context.semantic.capability != Availability.LIVE:
            return LiveToolResult(tool="search_live_evidence", availability=context.semantic.capability, observed_at=context.semantic.freshness.observed_at, reason=context.semantic.reason or "Live semantic evidence search is unavailable.")
        try:
            from aegis.api.state import get_state

            engine = getattr(get_state(), "semantic_query_engine", None)
            if engine is None:
                raise RuntimeError("semantic query engine is not initialized")
            state = get_state()
            try:
                durable_events = load_persisted_event_records(limit=100)
            except Exception:
                durable_events = []
            execution = engine.search(
                prompt=query,
                tracks=state.get_tracks(),
                events=merge_event_records(durable_events, state.get_events(limit=100)),
                statistics=state.get_statistics(),
            )
            raw_results = getattr(execution, "results", execution)
            if not isinstance(raw_results, list):
                raise TypeError("semantic engine returned an invalid result payload")
        except Exception as exc:
            return LiveToolResult(tool="search_live_evidence", availability=Availability.UNAVAILABLE, observed_at=context.semantic.freshness.observed_at, reason=f"Live semantic evidence source is unavailable: {type(exc).__name__}.")

        camera_filter = str(arguments.get("camera_id", "")).strip() or None
        entries: List[Dict[str, Any]] = []
        citations: List[LiveCitation] = []
        for raw in raw_results[:50]:
            if not isinstance(raw, dict):
                continue
            camera_id = raw.get("camera_id")
            if camera_filter and camera_id != camera_filter:
                continue
            evidence_id = raw.get("evidence_id") or raw.get("detection_id") or raw.get("track_id")
            if evidence_id is None:
                continue
            kind = "track" if raw.get("track_id") is not None else "detection"
            citation = self._citation(
                kind=kind,
                item_id=str(evidence_id),
                label=str(raw.get("semantic_label") or raw.get("class_name") or f"Semantic evidence {evidence_id}"),
                availability=context.semantic.freshness.status,
                camera_id=str(camera_id) if camera_id is not None else None,
                observed_at=context.semantic.freshness.observed_at,
            )
            citations.append(citation)
            entries.append(_json_value(raw))
        return LiveToolResult(
            tool="search_live_evidence",
            availability=context.semantic.freshness.status,
            observed_at=context.semantic.freshness.observed_at,
            reason=context.semantic.freshness.reason,
            data={"query": query, "cameraId": camera_filter, "timeRange": arguments.get("time_range"), "results": entries},
            citations=citations,
            ui_command=SafeUICommand(kind=UICommandKind.OPEN_SEMANTIC_EVIDENCE),
        )

    def _get_pipeline_health(self, _: Dict[str, Any]) -> LiveToolResult:
        context = self._context()
        citations = [
            self._citation(kind="health", item_id=check.name, label=f"{check.name.replace('_', ' ')} health", availability=check.status, observed_at=check.observed_at)
            for check in context.overall.checks
        ]
        return LiveToolResult(
            tool="get_pipeline_health",
            availability=context.overall.status,
            observed_at=context.generated_at,
            reason="; ".join(context.overall.degraded_reasons) or None,
            data={"checks": _json_value(context.overall.checks), "pipeline": _json_value(context.pipeline)},
            citations=citations,
            ui_command=SafeUICommand(kind=UICommandKind.FOCUS_HEALTH),
        )

    def _get_official_system_knowledge(self, arguments: Dict[str, Any]) -> LiveToolResult:
        """Expose only safe public facts; IDs, sources, and audit metadata stay server-side."""
        query = str(arguments.get("query", "")).strip()
        locale = str(arguments.get("locale", "")).strip() or None
        observed_at = _utc_now()
        if not query:
            return LiveToolResult(
                tool="get_official_system_knowledge",
                availability=Availability.UNAVAILABLE,
                observed_at=observed_at,
                reason="A non-empty official knowledge query is required.",
            )
        try:
            from aegis.knowledge.service import get_system_knowledge_service

            result = get_system_knowledge_service().retrieve(query, locale=locale)
        except Exception as exc:
            logger.warning("Official knowledge Live tool unavailable: %s", type(exc).__name__)
            return LiveToolResult(
                tool="get_official_system_knowledge",
                availability=Availability.UNAVAILABLE,
                observed_at=observed_at,
                reason="Official knowledge is temporarily unavailable.",
            )
        if result.availability != "available":
            return LiveToolResult(
                tool="get_official_system_knowledge",
                availability=Availability.UNAVAILABLE,
                observed_at=observed_at,
                reason="Official knowledge is temporarily unavailable.",
            )
        return LiveToolResult(
            tool="get_official_system_knowledge",
            availability=Availability.LIVE,
            observed_at=observed_at,
            reason=result.reason,
            data={
                "locale": result.locale,
                "facts": [{"category": item.category, "title": item.title, "content": item.content} for item in result.records],
                "notDocumented": not bool(result.records),
            },
        )

    def _open_authorised_evidence(self, arguments: Dict[str, Any]) -> LiveToolResult:
        evidence_id = str(arguments.get("evidence_id", "")).strip()
        citation = self._ephemeral_evidence.get(evidence_id)
        context = self._context()
        if citation is None:
            return LiveToolResult(tool="open_authorised_evidence", availability=Availability.UNAVAILABLE, observed_at=context.generated_at, reason="The evidence ID was not returned by an authorised tool in this voice session.")
        commands = {
            "camera": UICommandKind.OPEN_CAMERAS,
            "track": UICommandKind.SHOW_TRACK_EVIDENCE,
            "event": UICommandKind.SHOW_RISK_EVIDENCE,
            "alert": UICommandKind.SHOW_RISK_EVIDENCE,
            "detection": UICommandKind.SHOW_TRACK_EVIDENCE,
            "recording": UICommandKind.SHOW_RISK_EVIDENCE,
            "statistics": UICommandKind.FOCUS_HEALTH,
            "health": UICommandKind.FOCUS_HEALTH,
        }
        _, _, target_id = evidence_id.partition(":")
        return LiveToolResult(
            tool="open_authorised_evidence",
            availability=citation.availability,
            observed_at=citation.observed_at or context.generated_at,
            data={"evidenceId": citation.evidence_id, "label": citation.label},
            citations=[citation],
            ui_command=SafeUICommand(kind=commands[citation.kind], target_id=target_id or None, camera_id=citation.camera_id),
        )

    @staticmethod
    def _log_audit(record: ToolAuditRecord) -> None:
        # The event contains tool metadata only. Raw microphone audio is never
        # accepted by this class and therefore can never enter audit logs.
        logger.info("gemini_live_tool_audit=%s", json.dumps(record.model_dump(by_alias=True, mode="json"), separators=(",", ":")))
