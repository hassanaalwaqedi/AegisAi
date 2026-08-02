"""Server-side Gemini Live gateway and short-lived session manager.

The browser communicates only with this gateway. Gemini credentials remain on
the FastAPI host; raw microphone audio is forwarded in memory and is neither
logged nor persisted by this module.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import logging
import os
import secrets
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

from fastapi import WebSocket, WebSocketDisconnect

from aegis.api.security import get_allowed_origins
from aegis.intelligence.context_schemas import Availability, IntelligenceContext
from aegis.intelligence.live_prompt import AEGIS_LIVE_SYSTEM_INSTRUCTION
from aegis.intelligence.live_schemas import (
    BrowserVoiceEnvelope,
    LiveCapabilities,
    LiveSessionResponse,
    ServerVoiceEnvelope,
    ToolAuditRecord,
    VoiceState,
)
from aegis.intelligence.live_tools import LiveToolRegistry, ToolNotAllowedError

logger = logging.getLogger(__name__)

# The Gemini SDK uses ``websockets`` underneath. At DEBUG level that library
# logs request headers, including the server-only API key. Keep those transport
# loggers above DEBUG even when an operator enables broad application debugging.
logging.getLogger("websockets").setLevel(logging.WARNING)
logging.getLogger("websockets.client").setLevel(logging.WARNING)

LIVE_WS_PROTOCOL = "aegis-live-v1"
_MAX_AUDIO_CHUNK_BYTES = 64 * 1024


def _voice_envelope_payload(envelope: ServerVoiceEnvelope) -> Dict[str, Any]:
    """Produce a WebSocket-safe payload without retaining any audio data.

    Citations include UTC timestamps. Starlette's WebSocket ``send_json`` uses
    the standard JSON encoder, which cannot serialize Python ``datetime``
    objects. Pydantic JSON mode converts those values before they reach the
    socket, so a valid evidence citation cannot terminate a live session.
    """
    return envelope.model_dump(by_alias=True, exclude_none=True, mode="json")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _sdk_available() -> bool:
    try:
        from google import genai  # noqa: F401

        return True
    except ImportError:
        return False


def get_live_capabilities(settings: Any = None, sdk_available: Callable[[], bool] = _sdk_available) -> LiveCapabilities:
    """Return a configuration-derived capability state without probing Gemini.

    A Live WebSocket connection performs the authoritative model/voice
    validation. This keeps the capability endpoint free of paid network calls
    and reports a clear reason if Gemini rejects configuration later.
    """
    if settings is None:
        from aegis.settings import get_settings

        settings = get_settings()

    live = getattr(settings, "gemini_live", None)
    gemini = getattr(settings, "gemini", None)
    enabled = bool(getattr(live, "enabled", False))
    # ``GeminiSettings`` resolves GEMINI_API_KEY itself. Do not fall back to a
    # process environment value after a settings object was injected: that can
    # accidentally cross an explicit capability boundary in tests or workers.
    api_key = str(getattr(gemini, "api_key", "")).strip()
    model = str(getattr(live, "model", "") or os.getenv("GEMINI_LIVE_MODEL", "")).strip()
    voice = str(getattr(live, "voice", "") or os.getenv("GEMINI_LIVE_VOICE", "")).strip()
    input_sample_rate = int(getattr(live, "input_sample_rate", 16_000))
    output_sample_rate = int(getattr(live, "output_sample_rate", 24_000))

    reason: Optional[str] = None
    if not enabled:
        reason = "Gemini Live is disabled. Set GEMINI_LIVE_ENABLED=true on the backend to enable it."
    elif not api_key:
        reason = "Gemini Live is unavailable because GEMINI_API_KEY is not configured on the backend."
    elif not model:
        reason = "Gemini Live is unavailable because GEMINI_LIVE_MODEL is empty."
    elif not voice:
        reason = "Gemini Live is unavailable because GEMINI_LIVE_VOICE is empty."
    elif not sdk_available():
        reason = "Gemini Live is unavailable because the google-genai server SDK is not installed."

    if reason:
        return LiveCapabilities(
            availability=Availability.UNAVAILABLE,
            reason=reason,
            native_audio=False,
            input_transcription=False,
            output_transcription=False,
            input_sample_rate=None,
            output_sample_rate=None,
            push_to_talk=Availability.UNAVAILABLE,
            websocket_protocol=LIVE_WS_PROTOCOL,
        )

    return LiveCapabilities(
        availability=Availability.LIVE,
        reason="Native Gemini audio is configured. Provider capability is verified when an authenticated session connects.",
        native_audio=True,
        input_transcription=True,
        output_transcription=True,
        input_sample_rate=input_sample_rate,
        output_sample_rate=output_sample_rate,
        push_to_talk=Availability.LIVE,
        websocket_protocol=LIVE_WS_PROTOCOL,
    )


@dataclass
class ManagedLiveSession:
    session_id: str
    connection_token: str
    expires_at: datetime
    correlation_id: str
    operator_id: str
    capabilities: LiveCapabilities
    audible_alert: Optional["VerifiedAudibleAlert"] = None
    connected: bool = False
    closed_at: Optional[datetime] = None
    transcripts: List[Dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class VerifiedAudibleAlert:
    """The only alert material allowed to enter a Gemini TTS turn.

    The message is produced by Aegis from fresh, server-validated context. It
    deliberately omits model-generated summaries and any unverified browser
    fields, so the provider cannot be prompted to narrate stale risk data.
    """

    alert_id: str
    level: str
    text: str


class LiveSessionManager:
    """In-memory short-lived session and audit registry.

    Current Aegis authentication is API-key based, so the operator identifier
    records that authenticated boundary rather than inventing a user identity.
    Future RBAC can replace ``operator_id`` at session creation without
    exposing it to Gemini.
    """

    def __init__(
        self,
        *,
        settings_getter: Optional[Callable[[], Any]] = None,
        sdk_available: Callable[[], bool] = _sdk_available,
        now: Callable[[], datetime] = _utc_now,
        context_getter: Optional[Callable[[], IntelligenceContext]] = None,
    ) -> None:
        self._settings_getter = settings_getter
        self._sdk_available = sdk_available
        self._now = now
        self._context_getter = context_getter
        self._sessions: Dict[str, ManagedLiveSession] = {}
        self._audit_records: List[ToolAuditRecord] = []
        self._lock = asyncio.Lock()

    def settings(self) -> Any:
        if self._settings_getter is not None:
            return self._settings_getter()
        from aegis.settings import get_settings

        return get_settings()

    def capabilities(self) -> LiveCapabilities:
        return get_live_capabilities(self.settings(), self._sdk_available)

    def _context(self) -> IntelligenceContext:
        if self._context_getter is not None:
            return self._context_getter()
        from aegis.intelligence.context_service import get_intelligence_context_service

        return get_intelligence_context_service().build()

    @staticmethod
    def _verified_evidence(record: Any) -> bool:
        freshness = getattr(record, "freshness", None)
        if getattr(freshness, "status", None) != Availability.LIVE:
            return False
        return any(getattr(evidence, "server_validated", False) for evidence in getattr(record, "evidence", []))

    def _verified_audible_alert(self, alert_id: str) -> VerifiedAudibleAlert:
        """Resolve one opaque ID from current context or fail closed.

        This is intentionally a new context read at session creation, rather
        than a trust in the client-side polling snapshot. Medium, stale,
        unverified, acknowledged, missing, and unavailable records are silent.
        """
        context = self._context()
        if context.overall.status != Availability.LIVE:
            raise LiveCapabilityError("Audible alerts are unavailable because Intelligence context is not live.")

        record: Any | None = next(
            (
                item
                for item in context.alerts.items
                if item.alert_id == alert_id and item.acknowledged is not True
            ),
            None,
        )
        level = str(getattr(record, "level", "") or "").strip().upper()
        if record is None:
            record = next((item for item in context.events if item.event_id == alert_id), None)
            level = str(getattr(record, "risk_level", "") or "").strip().upper()
        if record is None or level not in {"HIGH", "CRITICAL"} or not self._verified_evidence(record):
            raise LiveCapabilityError("The requested audible alert is unavailable.")

        evidence = next(
            (item for item in record.evidence if item.server_validated),
            None,
        )
        camera_id = str(getattr(evidence, "camera_id", "") or "").strip()
        location = f" near {camera_id}" if camera_id else ""
        if level == "CRITICAL":
            text = f"Critical attention required. Operator review needed immediately{location}."
        else:
            text = f"High priority alert. Operator review recommended{location}."
        return VerifiedAudibleAlert(alert_id=alert_id, level=level, text=text)

    async def create(self, operator_id: str, *, audible_alert_id: Optional[str] = None) -> LiveSessionResponse:
        await self.prune()
        capability = self.capabilities()
        if capability.availability != Availability.LIVE:
            raise LiveCapabilityError(capability.reason or "Gemini Live is unavailable.")

        settings = self.settings()
        ttl = int(getattr(getattr(settings, "gemini_live", None), "session_ttl_seconds", 120))
        verified_alert = self._verified_audible_alert(audible_alert_id) if audible_alert_id else None
        session = ManagedLiveSession(
            session_id=uuid.uuid4().hex,
            connection_token=secrets.token_urlsafe(32),
            expires_at=self._now() + timedelta(seconds=ttl),
            correlation_id=uuid.uuid4().hex,
            operator_id=operator_id,
            capabilities=capability,
            audible_alert=verified_alert,
        )
        async with self._lock:
            self._sessions[session.session_id] = session
        return LiveSessionResponse(
            session_id=session.session_id,
            connection_token=session.connection_token,
            expires_at=session.expires_at,
            correlation_id=session.correlation_id,
            capabilities=capability,
        )

    async def claim_connection(self, session_id: str, token: str) -> Optional[ManagedLiveSession]:
        await self.prune()
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None or session.connected or session.closed_at is not None:
                return None
            if session.expires_at <= self._now() or not secrets.compare_digest(session.connection_token, token):
                return None
            session.connected = True
            return session

    async def close(self, session_id: str) -> bool:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return False
            session.closed_at = self._now()
            session.connection_token = ""
            # Raw audio is never retained. By default transcripts also leave
            # memory immediately at close; optional retention remains process
            # local and is bounded by the configured value.
            retention = int(getattr(getattr(self.settings(), "gemini_live", None), "transcript_retention_seconds", 0))
            if retention == 0:
                session.transcripts.clear()
            return True

    async def prune(self) -> None:
        now = self._now()
        settings = self.settings()
        transcript_retention = int(getattr(getattr(settings, "gemini_live", None), "transcript_retention_seconds", 0))
        audit_retention = int(getattr(getattr(settings, "gemini_live", None), "tool_audit_retention_seconds", 3600))
        async with self._lock:
            discard = [
                session_id
                for session_id, session in self._sessions.items()
                if (not session.connected and session.expires_at <= now)
                or (session.closed_at is not None and (transcript_retention == 0 or session.closed_at + timedelta(seconds=transcript_retention) <= now))
            ]
            for session_id in discard:
                self._sessions.pop(session_id, None)
            cutoff = now - timedelta(seconds=audit_retention)
            self._audit_records = [record for record in self._audit_records if audit_retention > 0 and record.observed_at >= cutoff]

    def record_audit(self, record: ToolAuditRecord) -> None:
        """Store only bounded metadata; never audio bytes or audio payloads."""
        self._audit_records.append(record)
        logger.info(
            "gemini_live_tool_audit=%s",
            record.model_dump_json(by_alias=True, exclude_none=True),
        )

    def audit_records(self) -> List[ToolAuditRecord]:
        return list(self._audit_records)

    def append_transcript(self, session: ManagedLiveSession, speaker: str, text: str, is_final: bool) -> None:
        if not text:
            return
        session.transcripts.append({"speaker": speaker, "text": text, "isFinal": is_final, "observedAt": self._now().isoformat()})


class LiveCapabilityError(RuntimeError):
    pass


@dataclass
class GeminiLiveVoiceSession:
    """One persistent, backend-owned Gemini Live audio bridge.

    This adapter deliberately owns no browser credentials and retains neither
    incoming microphone frames nor outgoing audio.  A browser WebSocket maps
    to exactly one instance, so a binary PCM output frame is intrinsically
    associated with this authenticated Aegis session.  Turn identifiers are
    emitted on the adjacent typed JSON audit events.
    """

    managed_session: ManagedLiveSession
    gemini_session: Any
    emit: Callable[[ServerVoiceEnvelope], Awaitable[None]]
    send_audio: Callable[[bytes], Awaitable[None]]
    input_sample_rate: int
    output_sample_rate: int
    active_turn_id: Optional[str] = None

    def begin_turn(self) -> str:
        if self.active_turn_id is None:
            self.active_turn_id = uuid.uuid4().hex
        return self.active_turn_id

    async def emit_state(self, state: VoiceState) -> None:
        await self.emit(
            ServerVoiceEnvelope(
                type="state",
                state=state,
                turn_id=self.active_turn_id,
                correlation_id=self.managed_session.correlation_id,
            )
        )

    async def forward_native_audio(self, audio: bytes) -> None:
        """Forward a native signed-16-bit PCM chunk as a binary WS frame."""
        if not audio or len(audio) > _MAX_AUDIO_CHUNK_BYTES:
            raise ValueError("Gemini Live returned an invalid native audio chunk.")
        await self.send_audio(audio)

    async def finish_turn(self) -> None:
        turn_id = self.active_turn_id
        await self.emit(
            ServerVoiceEnvelope(
                type="turn_complete",
                turn_id=turn_id,
                correlation_id=self.managed_session.correlation_id,
            )
        )
        await self.emit_state(VoiceState.READY)
        self.active_turn_id = None


_manager: Optional[LiveSessionManager] = None


def get_live_session_manager() -> LiveSessionManager:
    global _manager
    if _manager is None:
        _manager = LiveSessionManager()
    return _manager


async def _receive_provider_turns(
    gemini_session: Any,
    stopped: asyncio.Event,
    handle_message: Callable[[Any], Awaitable[None]],
) -> None:
    """Keep consuming provider turns until the session is explicitly stopped.

    Gemini's SDK completes one ``receive()`` iterator at a turn boundary. The
    next invocation waits for the next turn on the same Live connection; it is
    not a provider disconnect.
    """
    empty_receive_cycles = 0
    while not stopped.is_set():
        received_message = False
        async for message in gemini_session.receive():
            received_message = True
            await handle_message(message)

        if stopped.is_set():
            return
        if received_message:
            empty_receive_cycles = 0
            continue

        empty_receive_cycles += 1
        if empty_receive_cycles >= 2:
            raise RuntimeError("Gemini Live receive stream ended without a turn.")
        await asyncio.sleep(0.05)


async def run_live_gateway(websocket: WebSocket, session_id: str, connection_token: str) -> None:
    """Authenticate a browser socket and bridge it to one Gemini Live session."""
    manager = get_live_session_manager()
    origin = websocket.headers.get("origin")
    allowed_origins = set(get_allowed_origins()) | {"http://localhost:3000", "http://127.0.0.1:3000"}
    if origin and origin not in allowed_origins:
        await websocket.close(code=4403)
        return

    session = await manager.claim_connection(session_id, connection_token)
    if session is None:
        await websocket.close(code=4401)
        return

    await websocket.accept(subprotocol=LIVE_WS_PROTOCOL)

    async def emit(envelope: ServerVoiceEnvelope) -> None:
        await websocket.send_json(_voice_envelope_payload(envelope))

    try:
        await emit(ServerVoiceEnvelope(type="state", state=VoiceState.CONNECTING, correlation_id=session.correlation_id))
        await _bridge_gemini_session(websocket, session, manager, emit)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Gemini Live gateway terminated for session %s", session.session_id)
        try:
            await emit(ServerVoiceEnvelope(type="error", code="LIVE_GATEWAY_ERROR", message="The secure voice gateway stopped unexpectedly.", correlation_id=session.correlation_id))
        except Exception:
            pass
    finally:
        await manager.close(session.session_id)
        try:
            await websocket.close()
        except Exception:
            pass


async def _bridge_gemini_session(
    websocket: WebSocket,
    session: ManagedLiveSession,
    manager: LiveSessionManager,
    emit: Callable[[ServerVoiceEnvelope], Awaitable[None]],
) -> None:
    """Relay typed browser envelopes and Gemini Live frames in memory only."""
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        await emit(ServerVoiceEnvelope(type="error", code="LIVE_SDK_UNAVAILABLE", message="Gemini Live server support is not installed.", correlation_id=session.correlation_id))
        return

    settings = manager.settings()
    api_key = str(getattr(getattr(settings, "gemini", None), "api_key", "") or os.getenv("GEMINI_API_KEY", "")).strip()
    live = getattr(settings, "gemini_live", None)
    model = str(getattr(live, "model", "")).strip()
    voice = str(getattr(live, "voice", "")).strip()
    input_sample_rate = int(getattr(live, "input_sample_rate", 16_000))
    output_sample_rate = int(getattr(live, "output_sample_rate", 24_000))
    max_session_seconds = int(getattr(live, "max_session_seconds", 900))
    if not api_key or not model or not voice:
        await emit(ServerVoiceEnvelope(type="error", code="LIVE_CONFIGURATION_INVALID", message="Gemini Live configuration is incomplete on the backend.", correlation_id=session.correlation_id))
        return

    live_config: Dict[str, Any] = {
        "response_modalities": ["AUDIO"],
        "speech_config": {"voice_config": {"prebuilt_voice_config": {"voice_name": voice}}},
        "system_instruction": AEGIS_LIVE_SYSTEM_INSTRUCTION,
        "input_audio_transcription": {},
        "output_audio_transcription": {},
        "tools": [{"function_declarations": LiveToolRegistry.declarations()}],
    }
    client = genai.Client(api_key=api_key)
    registry = LiveToolRegistry(
        session_id=session.session_id,
        operator_id=session.operator_id,
        correlation_id=session.correlation_id,
        audit_sink=manager.record_audit,
    )
    stopped = asyncio.Event()
    voice_session: Optional[GeminiLiveVoiceSession] = None

    async def send_audio(audio: bytes) -> None:
        # Output audio is intentionally a binary WebSocket frame rather than
        # base64 JSON. It is scoped to this single authenticated session and
        # is never written to logs, the audit record, or persistence.
        await websocket.send_bytes(audio)

    async def receive_browser(gemini_session: Any) -> None:
        while not stopped.is_set():
            raw = await websocket.receive_json()
            try:
                event = BrowserVoiceEnvelope.model_validate(raw)
            except Exception:
                await emit(ServerVoiceEnvelope(type="error", code="INVALID_VOICE_ENVELOPE", message="The browser sent an invalid voice message.", correlation_id=session.correlation_id))
                continue
            if event.type == "ping":
                await emit(ServerVoiceEnvelope(type="pong", correlation_id=session.correlation_id))
            elif event.type == "stop":
                stopped.set()
            elif event.type == "interrupt":
                # Gemini Live's VAD safely interrupts an active generation
                # when the subsequent realtime input arrives. Do not invent a
                # provider cancellation API: acknowledge the interruption and
                # let the native session process the operator's next frame.
                if voice_session is not None:
                    await emit(ServerVoiceEnvelope(type="interrupted", turn_id=voice_session.active_turn_id, correlation_id=session.correlation_id))
                    voice_session.active_turn_id = None
            elif event.type == "audio_end":
                await gemini_session.send_realtime_input(audio_stream_end=True)
            elif event.type == "text":
                if not event.data or len(event.data) > 2_000:
                    await emit(ServerVoiceEnvelope(type="error", code="INVALID_TEXT_INPUT", message="Voice text input is missing or too large.", correlation_id=session.correlation_id))
                    continue
                if voice_session is not None:
                    voice_session.begin_turn()
                    await voice_session.emit_state(VoiceState.THINKING)
                await gemini_session.send_realtime_input(text=event.data)
            elif event.type == "audio":
                if not event.data:
                    continue
                try:
                    audio = base64.b64decode(event.data, validate=True)
                except (binascii.Error, ValueError):
                    await emit(ServerVoiceEnvelope(type="error", code="INVALID_AUDIO", message="Audio input was not valid base64 PCM.", correlation_id=session.correlation_id))
                    continue
                if not audio or len(audio) > _MAX_AUDIO_CHUNK_BYTES:
                    await emit(ServerVoiceEnvelope(type="error", code="INVALID_AUDIO", message="Audio input size is invalid.", correlation_id=session.correlation_id))
                    continue
                # Barge-in stops client playback immediately. The following
                # realtime PCM causes Gemini Live VAD to interrupt a current
                # response on the same persistent provider connection.
                if voice_session is not None:
                    voice_session.begin_turn()
                    await voice_session.emit_state(VoiceState.LISTENING)
                await gemini_session.send_realtime_input(
                    audio=types.Blob(data=audio, mime_type=f"audio/pcm;rate={input_sample_rate}")
                )

    async def handle_gemini_message(gemini_session: Any, message: Any) -> None:
        server_content = getattr(message, "server_content", None)
        if server_content is not None:
            input_transcription = getattr(server_content, "input_transcription", None)
            if input_transcription and getattr(input_transcription, "text", None):
                text = str(input_transcription.text)
                manager.append_transcript(session, "operator", text, True)
                await emit(ServerVoiceEnvelope(type="transcript", speaker="operator", text=text, is_final=True, turn_id=voice_session.active_turn_id if voice_session else None, correlation_id=session.correlation_id))
            interim = getattr(server_content, "interim_input_transcription", None)
            if interim and getattr(interim, "text", None):
                await emit(ServerVoiceEnvelope(type="transcript", speaker="operator", text=str(interim.text), is_final=False, turn_id=voice_session.active_turn_id if voice_session else None, correlation_id=session.correlation_id))
            output_transcription = getattr(server_content, "output_transcription", None)
            if output_transcription and getattr(output_transcription, "text", None):
                text = str(output_transcription.text)
                manager.append_transcript(session, "aegis", text, True)
                await emit(ServerVoiceEnvelope(type="transcript", speaker="aegis", text=text, is_final=True, turn_id=voice_session.active_turn_id if voice_session else None, correlation_id=session.correlation_id))
            if getattr(server_content, "interrupted", False):
                await emit(ServerVoiceEnvelope(type="interrupted", turn_id=voice_session.active_turn_id if voice_session else None, correlation_id=session.correlation_id))
            model_turn = getattr(server_content, "model_turn", None)
            for part in getattr(model_turn, "parts", []) if model_turn else []:
                inline_data = getattr(part, "inline_data", None)
                audio = getattr(inline_data, "data", None) if inline_data else None
                if audio:
                    try:
                        native_audio = base64.b64decode(audio, validate=True) if isinstance(audio, str) else bytes(audio)
                        if voice_session is None:
                            raise RuntimeError("Voice session is not ready for native audio.")
                        await voice_session.forward_native_audio(native_audio)
                    except (ValueError, TypeError, binascii.Error) as exc:
                        logger.warning("Gemini Live returned invalid audio (%s)", type(exc).__name__)
                        await emit(ServerVoiceEnvelope(type="error", code="NATIVE_AUDIO_UNAVAILABLE", message="Gemini Live did not return playable native audio for this response.", recoverable=True, turn_id=voice_session.active_turn_id if voice_session else None, correlation_id=session.correlation_id))
            if getattr(server_content, "turn_complete", False):
                if voice_session is not None:
                    await voice_session.finish_turn()

        tool_call = getattr(message, "tool_call", None)
        calls = getattr(tool_call, "function_calls", None) if tool_call else None
        if calls:
            responses = []
            for call in calls:
                name = str(getattr(call, "name", ""))
                arguments = getattr(call, "args", {}) or {}
                if voice_session is not None:
                    voice_session.begin_turn()
                    await emit(ServerVoiceEnvelope(type="tool_activity", tool=name, tool_status="calling", turn_id=voice_session.active_turn_id, correlation_id=session.correlation_id))
                try:
                    result = registry.execute(name, dict(arguments))
                except ToolNotAllowedError:
                    result = None
                    await emit(ServerVoiceEnvelope(type="tool_activity", tool=name, tool_status="failed", turn_id=voice_session.active_turn_id if voice_session else None, correlation_id=session.correlation_id))
                    await emit(ServerVoiceEnvelope(type="error", code="TOOL_NOT_ALLOWED", message="The requested capability is not authorised for voice use.", recoverable=True, turn_id=voice_session.active_turn_id if voice_session else None, correlation_id=session.correlation_id))
                if result is None:
                    responses.append({"name": name, "id": getattr(call, "id", None), "response": {"result": {"availability": "unavailable", "reason": "Tool is not authorised."}}})
                    continue
                if result.citations:
                    await emit(ServerVoiceEnvelope(type="citations", citations=result.citations, turn_id=voice_session.active_turn_id if voice_session else None, correlation_id=session.correlation_id))
                if result.ui_command:
                    await emit(ServerVoiceEnvelope(type="ui_command", ui_command=result.ui_command, turn_id=voice_session.active_turn_id if voice_session else None, correlation_id=session.correlation_id))
                await emit(ServerVoiceEnvelope(type="tool_activity", tool=name, tool_status="completed", turn_id=voice_session.active_turn_id if voice_session else None, correlation_id=session.correlation_id))
                responses.append({"name": name, "id": getattr(call, "id", None), "response": {"result": result.model_dump(by_alias=True, mode="json")}})
            await gemini_session.send_tool_response(function_responses=responses)

    async def receive_gemini(gemini_session: Any) -> None:
        await _receive_provider_turns(
            gemini_session,
            stopped,
            lambda message: handle_gemini_message(gemini_session, message),
        )

    async def timeout() -> None:
        await asyncio.sleep(max_session_seconds)
        if not stopped.is_set():
            await emit(ServerVoiceEnvelope(type="error", code="SESSION_TIMEOUT", message="The voice session reached its configured maximum duration.", correlation_id=session.correlation_id))
            stopped.set()

    try:
        async with client.aio.live.connect(model=model, config=live_config) as gemini_session:
            voice_session = GeminiLiveVoiceSession(
                managed_session=session,
                gemini_session=gemini_session,
                emit=emit,
                send_audio=send_audio,
                input_sample_rate=input_sample_rate,
                output_sample_rate=output_sample_rate,
            )
            await emit(ServerVoiceEnvelope(type="session_ready", session_id=session.session_id, input_sample_rate=input_sample_rate, output_sample_rate=output_sample_rate, correlation_id=session.correlation_id))
            await voice_session.emit_state(VoiceState.READY)
            if session.audible_alert is not None:
                # The text was resolved and templated by `_verified_audible_alert`
                # immediately before this short-lived session was created. Do
                # not accept alert wording, severity, or evidence from the
                # browser, and do not ask Gemini to add advisory content.
                voice_session.begin_turn()
                await voice_session.emit_state(VoiceState.THINKING)
                await gemini_session.send_realtime_input(
                    text=(
                        "Speak the following server-approved operator alert exactly. "
                        "Do not add, omit, infer, translate, or explain anything: "
                        f"{session.audible_alert.text}"
                    )
                )
            browser_task = asyncio.create_task(receive_browser(gemini_session))
            gemini_task = asyncio.create_task(receive_gemini(gemini_session))
            timeout_task = asyncio.create_task(timeout())
            done, pending = await asyncio.wait({browser_task, gemini_task, timeout_task}, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                exc = task.exception()
                if exc and not isinstance(exc, WebSocketDisconnect):
                    raise exc
    except Exception as exc:
        # Provider exceptions can contain transport details. Log only the type
        # so a credential can never be copied into application logs.
        logger.warning("Gemini Live connection failed (%s)", type(exc).__name__)
        await emit(ServerVoiceEnvelope(type="error", code="GEMINI_LIVE_CONNECTION_FAILED", message="Gemini Live could not validate the configured model or voice, or the provider connection is unavailable.", correlation_id=session.correlation_id))
    finally:
        stopped.set()
