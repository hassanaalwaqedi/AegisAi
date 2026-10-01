"""Source-backed and explicitly permissioned tools for Gemini Live sessions.

Gemini receives bounded results and a narrow set of reversible Aegis controls.
It never receives a database session, camera-manager object, credential,
arbitrary route, host command, destructive action, or external-system control.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional

from aegis.intelligence.context_schemas import Availability, IntelligenceContext
from aegis.intelligence.agent_control import control_camera_runtime, permission_manifest, workspace_target
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


def _safe_verification_payload(record: Any) -> Dict[str, Any]:
    """Legacy snake-case projection with filesystem paths removed."""
    metadata = record.evidence_metadata if isinstance(record.evidence_metadata, dict) else {}
    return {
        "verification_id": record.verification_id,
        "incident_id": record.incident_id,
        "event_id": record.event_id,
        "camera_id": record.camera_id,
        "provider": record.provider,
        "model": record.model,
        "status": record.status,
        "combined_state": record.combined_state,
        "verdict": record.verdict,
        "confidence": record.confidence,
        "severity": record.severity,
        "summary": record.summary,
        "subjects": list(record.subjects or []),
        "observations": list(record.observations or []),
        "supporting_evidence": list(record.supporting_evidence or []),
        "contradicting_evidence": list(record.contradicting_evidence or []),
        "uncertainties": list(record.uncertainties or []),
        "recommended_action": record.recommended_action,
        "evidence_metadata": {key: metadata[key] for key in ("keyframe_count", "keyframe_timestamps", "keyframe_frame_ids", "event_frame_id") if key in metadata},
        "latency_ms": record.latency_ms,
        "analysis_version": record.analysis_version,
        "created_at": _json_value(record.created_at),
        "updated_at": _json_value(record.updated_at),
    }


class LiveToolRegistry:
    """Session-scoped allowlist with auditable, source-fresh outputs."""

    ALLOWED_TOOLS = {
        "get_agent_permissions",
        "navigate_workspace",
        "close_operator_view",
        "control_camera_runtime",
        "get_intelligence_context",
        "get_live_camera_status",
        "get_active_risk_alerts",
        "get_recent_events",
        "get_track_details",
        "get_risk_explanation",
        "get_incident_verification",
        "get_event_verification",
        "get_recent_incidents",
        "get_incident",
        "get_incident_evidence",
        "get_incident_timeline",
        "get_track_trajectory",
        "generate_incident_report",
        "analyze_incident_with_vlm",
        "search_live_evidence",
        "get_pipeline_health",
        "get_gpu_usage",
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
                "name": "get_agent_permissions",
                "description": "Return the exact Aegis agent permission boundary: autonomous internal controls, actions requiring explicit confirmation, and actions that are always denied.",
                "parameters": {"type": "OBJECT", "properties": {}},
            },
            {
                "name": "navigate_workspace",
                "description": "Open an allow-listed workspace inside Aegis. Use when the operator explicitly asks to open or go to a page. This cannot open arbitrary URLs or external applications.",
                "parameters": {"type": "OBJECT", "properties": {"workspace": {"type": "STRING", "enum": ["dashboard", "cameras", "events", "tracks", "evidence", "semantic", "analytics", "intelligence"]}}, "required": ["workspace"]},
            },
            {
                "name": "close_operator_view",
                "description": "Close the current Aegis operator result or overlay. This does not stop monitoring, close the browser, or control the host operating system.",
                "parameters": {"type": "OBJECT", "properties": {}},
            },
            {
                "name": "control_camera_runtime",
                "description": "Start or stop one configured Aegis camera, or all configured cameras. This is an audited reversible runtime control. Use only when the operator explicitly says start, stop, enable, disable, pause, or resume monitoring. Never interpret 'close the camera view' as stopping a camera.",
                "parameters": {"type": "OBJECT", "properties": {"action": {"type": "STRING", "enum": ["start", "stop"]}, "scope": {"type": "STRING", "enum": ["one", "all"]}, "camera_id": {"type": "STRING", "maxLength": 80}}, "required": ["action", "scope"]},
            },
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
                "description": "Get current recent events, optionally filtered to persisted events from a camera and a bounded lookback in seconds. Use for questions such as what happened on a camera recently; event data remains a CV report, not a finding of intent.",
                "parameters": {"type": "OBJECT", "properties": {"limit": {"type": "INTEGER", "minimum": 1, "maximum": 50}, "camera_id": {"type": "STRING", "maxLength": 80}, "since_seconds": {"type": "INTEGER", "minimum": 1, "maximum": 2592000}}},
            },
            {
                "name": "get_recent_incidents",
                "description": "Find persisted incidents for investigation. Use before incident detail when the user says latest, recent, serious, or asks about a time window. Results are records from the incident database, not inferred incidents.",
                "parameters": {"type": "OBJECT", "properties": {"limit": {"type": "INTEGER", "minimum": 1, "maximum": 50}, "since_seconds": {"type": "INTEGER", "minimum": 1, "maximum": 2592000}, "severity": {"type": "STRING", "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"]}, "camera_id": {"type": "STRING", "maxLength": 80}}},
            },
            {
                "name": "get_incident",
                "description": "Retrieve one persisted incident with correlated CV events, involved track references, risk-engine assessments, stored VLM verification, evidence references, and operator lifecycle decision. Keep those sources separate.",
                "parameters": {"type": "OBJECT", "properties": {"incident_id": {"type": "STRING", "minLength": 1, "maxLength": 128}}, "required": ["incident_id"]},
            },
            {
                "name": "get_incident_evidence",
                "description": "Retrieve metadata-only incident evidence references: persisted snapshots, selected-keyframe metadata, and available clips/recordings. Never claim image content from metadata; use open_authorised_evidence for UI access.",
                "parameters": {"type": "OBJECT", "properties": {"incident_id": {"type": "STRING", "minLength": 1, "maxLength": 128}}, "required": ["incident_id"]},
            },
            {
                "name": "get_incident_timeline",
                "description": "Return a chronological timeline assembled only from persisted incident, CV event, risk-assessment, VLM-verification, and operator-decision timestamps. Missing timestamps are omitted.",
                "parameters": {"type": "OBJECT", "properties": {"incident_id": {"type": "STRING", "minLength": 1, "maxLength": 128}}, "required": ["incident_id"]},
            },
            {
                "name": "get_track_trajectory",
                "description": "Retrieve persisted observations and event history for one camera-local track. Pixel speed is a derived estimate, never calibrated physical speed. Cross-camera re-identification is unavailable.",
                "parameters": {"type": "OBJECT", "properties": {"track_id": {"type": "STRING", "minLength": 1, "maxLength": 160}, "camera_id": {"type": "STRING", "maxLength": 80}, "time_window": {"type": "STRING", "maxLength": 16, "description": "Optional bounded duration such as 30s, 10m, 2h, or 1d."}}, "required": ["track_id"]},
            },
            {
                "name": "generate_incident_report",
                "description": "Generate a structured evidence-grounded report for a persisted incident, preserving CV, risk-engine, VLM, uncertainty, operator-decision, timeline, and reference provenance.",
                "parameters": {"type": "OBJECT", "properties": {"incident_id": {"type": "STRING", "minLength": 1, "maxLength": 128}}, "required": ["incident_id"]},
            },
            {
                "name": "analyze_incident_with_vlm",
                "description": "Request asynchronous on-demand visual verification using already stored incident snapshots. This is an explicit external analysis request and is denied unless VLM_ENABLED is true and every relevant camera is in VLM_ALLOWED_CAMERA_IDS. Never claim analysis occurred unless a verification ID is returned.",
                "parameters": {"type": "OBJECT", "properties": {"incident_id": {"type": "STRING", "minLength": 1, "maxLength": 128}}, "required": ["incident_id"]},
            },
            {
                "name": "get_track_details",
                "description": "Get verified details for one currently available track.",
                "parameters": {"type": "OBJECT", "properties": {"track_id": {"type": "STRING"}}, "required": ["track_id"]},
            },
            {
                "name": "get_risk_explanation",
                "description": "Explain an incident, persisted event, or current track using only stored CV signals, risk assessments, VLM verification, and operator state. For escalation disagreements, also call get_event_verification. Never infer intent or identity.",
                "parameters": {"type": "OBJECT", "properties": {"incident_id": {"type": "STRING"}, "event_id": {"type": "STRING"}, "track_id": {"type": "STRING"}}},
            },
            {
                "name": "get_incident_verification",
                "description": "Get the latest stored Gemini visual verification for one incident. It is a secondary assessment and does not replace CV evidence.",
                "parameters": {"type": "OBJECT", "properties": {"incident_id": {"type": "STRING", "minLength": 1, "maxLength": 128}}, "required": ["incident_id"]},
            },
            {
                "name": "get_event_verification",
                "description": "Compare Aegis computer-vision assessment with Gemini visual verification for a persisted event candidate, and explain whether it was promoted to an incident. Use when asked why an event did or did not escalate, whether Gemini agreed with CV, or what evidence changed the assessment.",
                "parameters": {"type": "OBJECT", "properties": {"event_id": {"type": "STRING", "minLength": 1, "maxLength": 128}}, "required": ["event_id"]},
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
                "name": "get_gpu_usage",
                "description": "Get current PyTorch CUDA availability and allocated/total GPU memory from the existing runtime helper. Do not treat unavailable telemetry as zero utilization, and distinguish GPU memory from GPU utilization.",
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
            attempted_name = name if re.fullmatch(r"[A-Za-z0-9_]{1,80}", str(name)) else "unrecognized_tool"
            rejected = ToolAuditRecord(
                tool=attempted_name,
                correlation_id=self.correlation_id,
                operator_id=self.operator_id,
                session_id=self.session_id,
                arguments=self._safe_audit_arguments(arguments if isinstance(arguments, dict) else {}),
                result_status=Availability.UNAVAILABLE,
                success=False,
                latency_ms=0.0,
                observed_at=_utc_now(),
            )
            self._submit_audit(rejected)
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
            arguments=self._safe_audit_arguments(arguments),
            result_status=result.availability,
            success=result.availability != Availability.UNAVAILABLE,
            latency_ms=round((time.monotonic() - started) * 1000, 2),
            evidence_ids=[citation.evidence_id for citation in result.citations],
            observed_at=_utc_now(),
        )
        self._submit_audit(audit)
        return result

    def _submit_audit(self, audit: ToolAuditRecord) -> None:
        try:
            self._audit_sink(audit)
        except Exception as exc:
            logger.warning("Live tool audit sink failed (%s)", type(exc).__name__)
        self._persist_audit(audit)

    @staticmethod
    def _safe_audit_arguments(arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Keep stable identifiers and bounded filters; drop prompts and free text."""
        allowed = {"incident_id", "event_id", "camera_id", "track_id", "evidence_id", "limit", "since_seconds", "severity", "time_window", "locale", "action", "scope", "workspace"}
        safe: Dict[str, Any] = {}
        for key, value in arguments.items():
            if key not in allowed or value is None or isinstance(value, (dict, list, bytes)):
                continue
            if key in {"limit", "since_seconds"}:
                if isinstance(value, int) and not isinstance(value, bool):
                    safe[key] = max(1, min(value, 2_592_000 if key == "since_seconds" else 50))
            elif key == "severity":
                if str(value).upper() in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
                    safe[key] = str(value).upper()
            elif key == "locale":
                if str(value) in {"ar", "en", "tr"}:
                    safe[key] = str(value)
            elif key == "time_window":
                if re.fullmatch(r"\d{1,8}(?:s|m|h|d)", str(value), re.IGNORECASE):
                    safe[key] = str(value)[:16]
            else:
                normalized = str(value).strip()
                if normalized and len(normalized) <= 256 and not re.search(r"(?i)(?:AIza[0-9A-Za-z_-]{20,}|sk-[0-9A-Za-z_-]{20,}|bearer\s|api[_-]?key|secret=)", normalized):
                    safe[key] = normalized
        return safe

    @staticmethod
    def _persist_audit(record: ToolAuditRecord) -> None:
        resource_type = "agent_tool"
        resource_id = None
        for key, kind in (("incident_id", "incident"), ("event_id", "event"), ("camera_id", "camera"), ("track_id", "track"), ("evidence_id", "evidence")):
            if record.arguments.get(key):
                resource_type, resource_id = kind, str(record.arguments[key])
                break
        try:
            from aegis.audit import record_audit

            record_audit(
                "agent.tool_invoked",
                actor_id=record.operator_id,
                resource_type=resource_type,
                resource_id=resource_id,
                details={
                    "tool": record.tool,
                    "session_id": record.session_id,
                    "correlation_id": record.correlation_id,
                    "arguments": record.arguments,
                    "result_status": record.result_status.value,
                    "success": record.success,
                    "latency_ms": record.latency_ms,
                    "evidence_ids": record.evidence_ids,
                    "observed_at": record.observed_at.isoformat(),
                },
            )
        except Exception as exc:
            logger.warning("Durable Live tool audit unavailable (%s)", type(exc).__name__)

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

    def _get_agent_permissions(self, _: Dict[str, Any]) -> LiveToolResult:
        return LiveToolResult(
            tool="get_agent_permissions",
            availability=Availability.LIVE,
            observed_at=_utc_now(),
            data=permission_manifest(),
        )

    def _navigate_workspace(self, arguments: Dict[str, Any]) -> LiveToolResult:
        workspace = str(arguments.get("workspace", "")).strip().casefold()
        target = workspace_target(workspace)
        return LiveToolResult(
            tool="navigate_workspace",
            availability=Availability.LIVE,
            observed_at=_utc_now(),
            data={"workspace": workspace, "target": target, "permission": "autonomous_internal"},
            ui_command=SafeUICommand(kind=UICommandKind.OPEN_WORKSPACE, target_id=workspace),
        )

    def _close_operator_view(self, _: Dict[str, Any]) -> LiveToolResult:
        return LiveToolResult(
            tool="close_operator_view",
            availability=Availability.LIVE,
            observed_at=_utc_now(),
            data={"closed": "operator_view", "permission": "autonomous_internal"},
            ui_command=SafeUICommand(kind=UICommandKind.CLOSE_OPERATOR_VIEW),
        )

    def _control_camera_runtime(self, arguments: Dict[str, Any]) -> LiveToolResult:
        action = str(arguments.get("action", "")).strip().casefold()
        scope = str(arguments.get("scope", "one")).strip().casefold()
        camera_id = str(arguments.get("camera_id", "")).strip() or None
        result = control_camera_runtime(
            action=action,
            scope=scope,
            camera_id=camera_id,
            actor_id=self.operator_id,
        )
        availability = Availability.DEGRADED if result.failures else Availability.LIVE if result.cameras else Availability.UNAVAILABLE
        reason = f"{len(result.failures)} camera runtime action(s) failed." if result.failures else None if result.cameras else "No configured cameras matched the requested runtime action."
        return LiveToolResult(
            tool="control_camera_runtime",
            availability=availability,
            observed_at=_utc_now(),
            reason=reason,
            data={
                "action": result.action,
                "scope": result.requested_scope,
                "succeeded": result.succeeded,
                "cameras": list(result.cameras),
                "failures": list(result.failures),
                "permission": "autonomous_internal",
            },
            ui_command=SafeUICommand(kind=UICommandKind.OPEN_CAMERAS, camera_id=camera_id if scope == "one" else None),
        )

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
        camera_filter = str(arguments.get("camera_id", "")).strip() or None
        since_seconds = arguments.get("since_seconds")
        if isinstance(since_seconds, int) and not isinstance(since_seconds, bool):
            since_seconds = max(1, min(since_seconds, 2_592_000))
        else:
            since_seconds = None
        if camera_filter or since_seconds is not None:
            observed_at = _utc_now()
            try:
                from aegis.database.connection import get_db_session
                from aegis.database.repositories import EventRepository
                cutoff = observed_at.timestamp() - since_seconds if since_seconds is not None else None
                with get_db_session() as session:
                    records = EventRepository(session).get_recent_evidence(limit=200)
                    filtered = [record for record in records if (not camera_filter or record.camera_id == camera_filter) and (cutoff is None or record.timestamp is not None and (record.timestamp.replace(tzinfo=timezone.utc) if record.timestamp.tzinfo is None else record.timestamp).timestamp() >= cutoff)][:limit]
                    entries = [{
                        "eventId": record.event_id,
                        "incidentId": record.incident_id,
                        "eventType": record.event_type,
                        "cameraId": record.camera_id,
                        "timestamp": _json_value(record.timestamp),
                        "riskLevel": record.risk_level,
                        "riskScore": record.risk_score,
                        "summary": record.reason or record.message,
                        "factors": list(record.factors or []),
                        "trackId": record.track_key,
                        "snapshotAvailable": record.snapshot_status == "saved",
                        "assessmentSource": "computer_vision",
                    } for record in filtered]
                citations = [self._citation(kind="event", item_id=row["eventId"], label=f"Event {row['eventId']}", availability=Availability.LIVE, camera_id=row.get("cameraId"), observed_at=datetime.fromisoformat(row["timestamp"]) if row.get("timestamp") else observed_at) for row in entries]
                if entries and entries[0].get("incidentId"):
                    command = SafeUICommand(kind=UICommandKind.OPEN_INCIDENT, target_id=entries[0]["incidentId"])
                elif entries:
                    command = SafeUICommand(kind=UICommandKind.SHOW_RISK_EVIDENCE, target_id=entries[0]["eventId"], camera_id=entries[0].get("cameraId"))
                else:
                    command = None
                return LiveToolResult(tool="get_recent_events", availability=Availability.LIVE, observed_at=observed_at, reason=None if entries else "No persisted events match the requested camera and time filters.", data={"events": entries, "cameraId": camera_filter, "sinceSeconds": since_seconds}, citations=citations, ui_command=command)
            except Exception as exc:
                logger.warning("Filtered recent event Live tool unavailable (%s)", type(exc).__name__)
                return LiveToolResult(tool="get_recent_events", availability=Availability.UNAVAILABLE, observed_at=observed_at, reason="Persisted event storage is temporarily unavailable.")
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
        observed_at = _utc_now()
        incident_id = str(arguments.get("incident_id", "")).strip()
        event_id = str(arguments.get("event_id", "")).strip()
        track_id = str(arguments.get("track_id", "")).strip()
        if incident_id or event_id:
            try:
                from aegis.intelligence.incident_investigation import get_risk_explanation
                persisted = get_risk_explanation(incident_id=incident_id or None, event_id=event_id or None)
            except Exception as exc:
                logger.warning("Persisted risk explanation unavailable (%s)", type(exc).__name__)
                persisted = None
            if persisted is not None:
                citations: List[LiveCitation] = []
                if incident_id:
                    citations.append(self._citation(kind="incident", item_id=incident_id, label=f"Incident {incident_id} risk explanation", availability=Availability.LIVE, observed_at=observed_at))
                    for event in persisted.get("computerVisionEvents", []):
                        if event.get("eventId"):
                            citations.append(self._citation(kind="event", item_id=event["eventId"], label=f"Risk evidence {event['eventId']}", availability=Availability.LIVE, camera_id=event.get("cameraId")))
                else:
                    event = persisted.get("event") or {}
                    citations.append(self._citation(kind="event", item_id=event_id, label=f"Event {event_id} risk explanation", availability=Availability.LIVE, camera_id=event.get("cameraId"), observed_at=datetime.fromisoformat(event["timestamp"]) if event.get("timestamp") else observed_at))
                target = incident_id or event_id
                return LiveToolResult(tool="get_risk_explanation", availability=Availability.LIVE, observed_at=observed_at, data=persisted, citations=citations, ui_command=SafeUICommand(kind=UICommandKind.OPEN_INCIDENT, target_id=incident_id) if incident_id else SafeUICommand(kind=UICommandKind.SHOW_RISK_EVIDENCE, target_id=target))
        context = self._context()
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

    def _get_incident_verification(self, arguments: Dict[str, Any]) -> LiveToolResult:
        incident_id = str(arguments.get("incident_id", "")).strip()
        observed_at = _utc_now()
        if not incident_id:
            return LiveToolResult(tool="get_incident_verification", availability=Availability.UNAVAILABLE, observed_at=observed_at, reason="An incident ID is required.")
        try:
            from aegis.database.connection import get_db_session
            from aegis.database.repositories import IncidentRepository, IncidentVerificationRepository
            with get_db_session() as session:
                incident = IncidentRepository(session).get_by_incident_id(incident_id)
                record = IncidentVerificationRepository(session).latest_for_incident(incident_id)
                verification = _safe_verification_payload(record) if record else None
        except Exception as exc:
            logger.warning("Incident verification Live tool unavailable: %s", type(exc).__name__)
            return LiveToolResult(tool="get_incident_verification", availability=Availability.UNAVAILABLE, observed_at=observed_at, reason="Verification storage is temporarily unavailable.")
        if incident is None and verification is None:
            return LiveToolResult(tool="get_incident_verification", availability=Availability.UNAVAILABLE, observed_at=observed_at, reason="incident_not_found", data={"incidentId": incident_id})
        camera_id = incident.camera_id if incident is not None else verification.get("camera_id")
        citation = self._citation(
            kind="incident" if incident is not None else "event",
            item_id=incident_id if incident is not None else verification.get("event_id", incident_id),
            label=f"Incident {incident_id} visual verification" if incident is not None else f"Uncorrelated visual verification for {incident_id}",
            availability=Availability.LIVE,
            observed_at=observed_at,
            camera_id=camera_id,
        )
        if verification is None:
            return LiveToolResult(tool="get_incident_verification", availability=Availability.LIVE, observed_at=observed_at, reason="No visual-language verification has been stored for this incident.", data={"incidentId": incident_id, "verification": None}, citations=[citation])
        return LiveToolResult(
            tool="get_incident_verification",
            availability=Availability.LIVE,
            observed_at=observed_at,
            reason=None if incident is not None else "No correlated incident record exists; this separately persisted verification is still available.",
            data={"incidentId": incident_id, "incidentFound": incident is not None, "verification": verification},
            citations=[citation],
            ui_command=SafeUICommand(kind=UICommandKind.SHOW_RISK_EVIDENCE, target_id=verification.get("event_id") or incident_id, camera_id=camera_id),
        )

    def _get_event_verification(self, arguments: Dict[str, Any]) -> LiveToolResult:
        event_id = str(arguments.get("event_id", "")).strip()
        observed_at = _utc_now()
        if not event_id:
            return LiveToolResult(tool="get_event_verification", availability=Availability.UNAVAILABLE, observed_at=observed_at, reason="An event ID is required.")
        try:
            from aegis.database.connection import get_db_session
            from aegis.database.repositories import EventRepository, IncidentVerificationRepository
            with get_db_session() as session:
                event = EventRepository(session).get_by_event_id(event_id)
                verification = IncidentVerificationRepository(session).latest_for_event(event_id)
                if event is None:
                    return LiveToolResult(tool="get_event_verification", availability=Availability.UNAVAILABLE, observed_at=observed_at, reason="No persisted Aegis event has this ID.")
                metadata = event.event_metadata if isinstance(event.event_metadata, dict) else {}
                cv_assessment = {
                    "eventId": event.event_id,
                    "eventType": event.event_type,
                    "riskLevel": event.risk_level,
                    "riskScore": event.risk_score,
                    "tracks": metadata.get("track_ids") or ([event.track_key] if event.track_key else []),
                    "signals": list(event.factors or []),
                    "assessmentSource": "computer_vision",
                }
                semantic_assessment = _safe_verification_payload(verification) if verification else None
                camera_id = event.camera_id
                incident_id = event.incident_id
                if semantic_assessment and semantic_assessment.get("combined_state") == "CONTRADICTED":
                    escalation = "The CV event remains preserved, but no incident was promoted because visual verification contradicted the candidate."
                elif semantic_assessment and semantic_assessment.get("combined_state") == "SUPPORTED" and event.incident_id:
                    escalation = f"The candidate was supported and correlated to incident {incident_id}."
                elif semantic_assessment and semantic_assessment.get("status") == "FAILED":
                    escalation = "Visual verification failed; the original CV assessment remains authoritative and the normal CV fallback applies."
                elif semantic_assessment and semantic_assessment.get("combined_state") in {"UNCERTAIN", "INSUFFICIENT_EVIDENCE"}:
                    escalation = "Visual evidence was uncertain or insufficient; the original CV event is retained without automatic promotion."
                elif semantic_assessment and semantic_assessment.get("combined_state") == "SUPPORTED":
                    escalation = "Visual verification supported the candidate, but promotion requirements were not met or correlation was unavailable."
                else:
                    escalation = "No visual verification is stored for this event; only the computer-vision assessment is available."
        except Exception as exc:
            logger.warning("Event verification Live tool unavailable: %s", type(exc).__name__)
            return LiveToolResult(tool="get_event_verification", availability=Availability.UNAVAILABLE, observed_at=observed_at, reason="Event verification storage is temporarily unavailable.")

        citation = self._citation(kind="event", item_id=event_id, label=f"Event {event_id} CV and visual verification", availability=Availability.LIVE, observed_at=observed_at, camera_id=camera_id)
        return LiveToolResult(
            tool="get_event_verification",
            availability=Availability.LIVE,
            observed_at=observed_at,
            data={"eventId": event_id, "incidentId": incident_id, "cvAssessment": cv_assessment, "semanticVerification": semantic_assessment, "escalationExplanation": escalation},
            citations=[citation],
            ui_command=SafeUICommand(kind=UICommandKind.SHOW_RISK_EVIDENCE, target_id=event_id, camera_id=camera_id),
        )

    def _get_recent_incidents(self, arguments: Dict[str, Any]) -> LiveToolResult:
        observed_at = _utc_now()
        try:
            from aegis.intelligence.incident_investigation import get_recent_incidents
            payload = get_recent_incidents(
                limit=arguments.get("limit", 10) if isinstance(arguments.get("limit", 10), int) else 10,
                since_seconds=arguments.get("since_seconds") if isinstance(arguments.get("since_seconds"), int) else None,
                severity=arguments.get("severity"),
                camera_id=arguments.get("camera_id"),
            )
        except Exception as exc:
            logger.warning("Recent incident Live tool unavailable (%s)", type(exc).__name__)
            return LiveToolResult(tool="get_recent_incidents", availability=Availability.UNAVAILABLE, observed_at=observed_at, reason="Persisted incident storage is temporarily unavailable.")
        citations = [
            self._citation(kind="incident", item_id=row["incidentId"], label=f"Incident {row['incidentId']}", availability=Availability.LIVE, camera_id=row.get("cameraId"))
            for row in payload["incidents"]
        ]
        first = payload["incidents"][0] if payload["incidents"] else None
        return LiveToolResult(
            tool="get_recent_incidents", availability=Availability.LIVE, observed_at=observed_at,
            reason=None if first else "No persisted incidents match the requested filters.", data=payload, citations=citations,
            ui_command=SafeUICommand(kind=UICommandKind.OPEN_INCIDENT, target_id=first["incidentId"]) if first else None,
        )

    def _get_incident(self, arguments: Dict[str, Any]) -> LiveToolResult:
        incident_id = str(arguments.get("incident_id", "")).strip()
        observed_at = _utc_now()
        if not incident_id:
            return LiveToolResult(tool="get_incident", availability=Availability.UNAVAILABLE, observed_at=observed_at, reason="An incident ID is required.")
        try:
            from aegis.intelligence.incident_investigation import get_incident
            payload = get_incident(incident_id)
        except Exception as exc:
            logger.warning("Incident Live tool unavailable (%s)", type(exc).__name__)
            return LiveToolResult(tool="get_incident", availability=Availability.UNAVAILABLE, observed_at=observed_at, reason="Persisted incident storage is temporarily unavailable.")
        if payload is None:
            return LiveToolResult(tool="get_incident", availability=Availability.UNAVAILABLE, observed_at=observed_at, reason="incident_not_found", data={"incidentId": incident_id})
        citation = self._citation(kind="incident", item_id=incident_id, label=f"Incident {incident_id}", availability=Availability.LIVE, camera_id=payload["incident"]["cameraId"])
        citations = [citation]
        for event in payload["events"]:
            if event.get("eventId"):
                citations.append(self._citation(kind="event", item_id=event["eventId"], label=f"Event {event['eventId']}", availability=Availability.LIVE, camera_id=event.get("cameraId"), observed_at=datetime.fromisoformat(event["timestamp"]) if event.get("timestamp") else observed_at))
        return LiveToolResult(tool="get_incident", availability=Availability.LIVE, observed_at=observed_at, data=payload, citations=citations, ui_command=SafeUICommand(kind=UICommandKind.OPEN_INCIDENT, target_id=incident_id))

    def _get_incident_evidence(self, arguments: Dict[str, Any]) -> LiveToolResult:
        incident_id = str(arguments.get("incident_id", "")).strip()
        observed_at = _utc_now()
        try:
            from aegis.intelligence.incident_investigation import get_incident_evidence
            payload = get_incident_evidence(incident_id) if incident_id else None
        except Exception as exc:
            logger.warning("Incident evidence Live tool unavailable (%s)", type(exc).__name__)
            return LiveToolResult(tool="get_incident_evidence", availability=Availability.UNAVAILABLE, observed_at=observed_at, reason="Persisted incident evidence is temporarily unavailable.")
        if payload is None:
            return LiveToolResult(tool="get_incident_evidence", availability=Availability.UNAVAILABLE, observed_at=observed_at, reason="incident_not_found", data={"incidentId": incident_id})
        citations = [
            self._citation(kind="event", item_id=item["eventId"], label=f"Saved evidence for event {item['eventId']}", availability=Availability.LIVE, camera_id=item.get("cameraId"), observed_at=datetime.fromisoformat(item["timestamp"]) if item.get("timestamp") else observed_at)
            for item in payload["snapshots"] if item.get("eventId")
        ]
        command = SafeUICommand(kind=UICommandKind.SHOW_RISK_EVIDENCE, target_id=citations[0].evidence_id.split(":", 1)[1]) if citations else SafeUICommand(kind=UICommandKind.OPEN_INCIDENT, target_id=incident_id)
        return LiveToolResult(tool="get_incident_evidence", availability=Availability.LIVE, observed_at=observed_at, data=payload, citations=citations, ui_command=command)

    def _get_incident_timeline(self, arguments: Dict[str, Any]) -> LiveToolResult:
        incident_id = str(arguments.get("incident_id", "")).strip()
        observed_at = _utc_now()
        try:
            from aegis.intelligence.incident_investigation import get_incident_timeline
            payload = get_incident_timeline(incident_id) if incident_id else None
        except Exception as exc:
            logger.warning("Incident timeline Live tool unavailable (%s)", type(exc).__name__)
            return LiveToolResult(tool="get_incident_timeline", availability=Availability.UNAVAILABLE, observed_at=observed_at, reason="Persisted incident timeline is temporarily unavailable.")
        if payload is None:
            return LiveToolResult(tool="get_incident_timeline", availability=Availability.UNAVAILABLE, observed_at=observed_at, reason="incident_not_found", data={"incidentId": incident_id})
        citation = self._citation(kind="incident", item_id=incident_id, label=f"Incident {incident_id} timeline", availability=Availability.LIVE, observed_at=observed_at)
        return LiveToolResult(tool="get_incident_timeline", availability=Availability.LIVE, observed_at=observed_at, data=payload, citations=[citation], ui_command=SafeUICommand(kind=UICommandKind.OPEN_INCIDENT, target_id=incident_id))

    def _get_track_trajectory(self, arguments: Dict[str, Any]) -> LiveToolResult:
        observed_at = _utc_now()
        track_id = str(arguments.get("track_id", "")).strip()
        try:
            from aegis.intelligence.incident_investigation import get_track_trajectory
            payload = get_track_trajectory(track_id, camera_id=arguments.get("camera_id"), time_window=arguments.get("time_window"))
        except ValueError as exc:
            return LiveToolResult(tool="get_track_trajectory", availability=Availability.UNAVAILABLE, observed_at=observed_at, reason=str(exc))
        except Exception as exc:
            logger.warning("Track trajectory Live tool unavailable (%s)", type(exc).__name__)
            return LiveToolResult(tool="get_track_trajectory", availability=Availability.UNAVAILABLE, observed_at=observed_at, reason="Persisted track history is temporarily unavailable.")
        if payload.get("availability") != Availability.LIVE.value:
            return LiveToolResult(tool="get_track_trajectory", availability=Availability.UNAVAILABLE, observed_at=observed_at, reason=payload.get("error") or payload.get("reason") or "Persisted track history is unavailable.", data=payload)
        citations = [self._citation(kind="track", item_id=payload["trackId"], label=f"Track trajectory {payload['trackId']}", availability=Availability.LIVE, camera_id=payload.get("cameraId"), observed_at=observed_at)]
        for event in payload.get("associatedEvents", []):
            if event.get("eventId"):
                citations.append(self._citation(kind="event", item_id=event["eventId"], label=f"Associated event {event['eventId']}", availability=Availability.LIVE, camera_id=event.get("cameraId")))
        return LiveToolResult(tool="get_track_trajectory", availability=Availability.LIVE, observed_at=observed_at, data=payload, citations=citations, ui_command=SafeUICommand(kind=UICommandKind.SHOW_TRACK_EVIDENCE, target_id=payload["trackId"], camera_id=payload.get("cameraId")))

    def _generate_incident_report(self, arguments: Dict[str, Any]) -> LiveToolResult:
        incident_id = str(arguments.get("incident_id", "")).strip()
        observed_at = _utc_now()
        try:
            from aegis.intelligence.incident_investigation import generate_incident_report
            payload = generate_incident_report(incident_id) if incident_id else None
        except Exception as exc:
            logger.warning("Incident report Live tool unavailable (%s)", type(exc).__name__)
            return LiveToolResult(tool="generate_incident_report", availability=Availability.UNAVAILABLE, observed_at=observed_at, reason="Persisted incident report sources are temporarily unavailable.")
        if payload is None:
            return LiveToolResult(tool="generate_incident_report", availability=Availability.UNAVAILABLE, observed_at=observed_at, reason="incident_not_found", data={"incidentId": incident_id})
        citations = [self._citation(kind="incident", item_id=incident_id, label=f"Incident report {incident_id}", availability=Availability.LIVE, observed_at=observed_at)]
        citations.extend(self._citation(kind="event", item_id=item_id, label=f"Report event {item_id}", availability=Availability.LIVE, observed_at=observed_at) for item_id in payload["references"]["eventIds"])
        return LiveToolResult(tool="generate_incident_report", availability=Availability.LIVE, observed_at=observed_at, data=payload, citations=citations, ui_command=SafeUICommand(kind=UICommandKind.OPEN_INCIDENT, target_id=incident_id))

    def _analyze_incident_with_vlm(self, arguments: Dict[str, Any]) -> LiveToolResult:
        incident_id = str(arguments.get("incident_id", "")).strip()
        observed_at = _utc_now()
        if not incident_id:
            return LiveToolResult(tool="analyze_incident_with_vlm", availability=Availability.UNAVAILABLE, observed_at=observed_at, reason="An incident ID is required.")
        try:
            from aegis.ai.tools import analyze_incident_with_vlm
            payload = analyze_incident_with_vlm(incident_id)
        except Exception as exc:
            logger.warning("On-demand VLM request failed (%s)", type(exc).__name__)
            return LiveToolResult(tool="analyze_incident_with_vlm", availability=Availability.UNAVAILABLE, observed_at=observed_at, reason="Visual verification could not be requested; no result was created.", data={"incidentId": incident_id, "status": "not_performed"})
        if payload.get("error"):
            source_error = str(payload["error"]).lower()
            if "vlm_analysis_disabled" in source_error or "vlm_disabled" in source_error:
                code = "VLM_ANALYSIS_DISABLED"
                explanation = "Visual analysis was not performed because VLM_ENABLED is false."
            elif "vlm_analysis_not_authorized_for_camera" in source_error or "camera_not_allowlisted" in source_error:
                code = "VLM_ANALYSIS_NOT_AUTHORIZED_FOR_CAMERA"
                explanation = "Visual analysis was not performed because this camera is not in VLM_ALLOWED_CAMERA_IDS."
            elif "incident_not_found" in source_error:
                code = "INCIDENT_NOT_FOUND"
                explanation = "Visual analysis was not performed because the incident does not exist."
            else:
                code = "VLM_ANALYSIS_NOT_PERFORMED"
                explanation = "Visual analysis was not performed; no verification result was created."
            return LiveToolResult(tool="analyze_incident_with_vlm", availability=Availability.LIVE, observed_at=observed_at, reason=explanation, data={"incidentId": incident_id, "status": "not_performed", "code": code})
        if payload.get("availability") != "available" or not payload.get("verification_id"):
            return LiveToolResult(tool="analyze_incident_with_vlm", availability=Availability.UNAVAILABLE, observed_at=observed_at, reason="Visual verification could not be requested; no result was created.", data={"incidentId": incident_id, "status": "not_performed"})
        citation = self._citation(kind="incident", item_id=incident_id, label=f"Incident {incident_id} VLM analysis request", availability=Availability.LIVE, observed_at=observed_at)
        return LiveToolResult(tool="analyze_incident_with_vlm", availability=Availability.LIVE, observed_at=observed_at, data={"incidentId": incident_id, "verificationId": payload["verification_id"], "status": payload.get("status", "scheduled")}, citations=[citation])

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

    def _get_gpu_usage(self, _: Dict[str, Any]) -> LiveToolResult:
        observed_at = _utc_now()
        try:
            from aegis.ai.tools import get_gpu_usage
            payload = get_gpu_usage()
        except Exception as exc:
            logger.warning("GPU telemetry Live tool unavailable (%s)", type(exc).__name__)
            return LiveToolResult(tool="get_gpu_usage", availability=Availability.UNAVAILABLE, observed_at=observed_at, reason="GPU telemetry is temporarily unavailable.")
        available = bool(payload.get("available"))
        return LiveToolResult(
            tool="get_gpu_usage",
            availability=Availability.LIVE if available else Availability.DEGRADED,
            observed_at=observed_at,
            reason=None if available else str(payload.get("message") or "CUDA telemetry is unavailable; no GPU utilization value is inferred."),
            data=payload,
            citations=[self._citation(kind="health", item_id="gpu", label="GPU runtime telemetry", availability=Availability.LIVE if available else Availability.DEGRADED, observed_at=observed_at)],
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
            "incident": UICommandKind.OPEN_INCIDENT,
        }
        _, _, target_id = evidence_id.partition(":")
        if citation.kind == "alert":
            target_id = ""
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
