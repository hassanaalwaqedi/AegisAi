"""Unit tests for the Gemini Live gateway's truthful and safe boundaries."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from aegis.intelligence.context_schemas import (
    AIContext,
    AlertsContext,
    Availability,
    CameraItem,
    CamerasContext,
    DetectionSummary,
    EvidenceRef,
    Freshness,
    IncidentsCapability,
    IntelligenceContext,
    OverallContext,
    PipelineContext,
    RiskAlertItem,
    SemanticContext,
    VoiceCapability,
)
from aegis.intelligence.live_schemas import BrowserVoiceEnvelope, LiveCitation, ServerVoiceEnvelope, UICommandKind
from aegis.intelligence.live_service import (
    GeminiLiveVoiceSession,
    LiveCapabilityError,
    LiveSessionManager,
    _receive_provider_turns,
    _voice_envelope_payload,
    get_live_capabilities,
)
from aegis.settings import GeminiLiveSettings
from aegis.intelligence.live_tools import LiveToolRegistry, ToolNotAllowedError
from aegis.api.routes.intelligence_live import ws_router


def now() -> datetime:
    return datetime.now(timezone.utc)


def fresh(status: Availability = Availability.LIVE, reason: str | None = None) -> Freshness:
    return Freshness(observed_at=now(), status=status, reason=reason)


def live_settings(*, enabled: bool = True, api_key: str = "test-key"):
    return SimpleNamespace(
        gemini=SimpleNamespace(api_key=api_key),
        gemini_live=SimpleNamespace(
            enabled=enabled,
            model="gemini-3.1-flash-live-preview",
            voice="Kore",
            session_ttl_seconds=120,
            max_session_seconds=900,
            transcript_retention_seconds=0,
            tool_audit_retention_seconds=3600,
        ),
    )


def context_with_cameras(*, unavailable: bool = False) -> IntelligenceContext:
    observed = now()
    camera_status = Availability.UNAVAILABLE if unavailable else Availability.LIVE
    camera_freshness = Freshness(
        observed_at=observed,
        status=camera_status,
        reason="Camera runtime manager is unavailable." if unavailable else None,
    )
    cameras = CamerasContext(
        total=None if unavailable else 2,
        total_configured=None if unavailable else 2,
        online=None if unavailable else 1,
        offline=None if unavailable else 1,
        stale=None if unavailable else 0,
        unavailable=None if unavailable else 0,
        items=[] if unavailable else [
            CameraItem(camera_id="gate-2", name="Gate 2", runtime=Availability.LIVE, last_frame_at=observed, freshness=fresh()),
            CameraItem(camera_id="parking-east", name="Parking East", runtime=Availability.OFFLINE, last_frame_at=None, freshness=fresh(Availability.OFFLINE, "Camera reported offline.")),
        ],
        freshness=camera_freshness,
    )
    return IntelligenceContext(
        context_id="live-test",
        generated_at=observed,
        refresh_after_seconds=15,
        overall=OverallContext(status=camera_status, degraded_reasons=[]),
        cameras=cameras,
        alerts=AlertsContext(active_count=0 if not unavailable else None, freshness=fresh(camera_status, camera_freshness.reason)),
        incidents=IncidentsCapability(capability=Availability.UNAVAILABLE, reason="Incident domain is not available."),
        events=[],
        tracks=[],
        detections=DetectionSummary(recent_count=0 if not unavailable else None, freshness=fresh(camera_status, camera_freshness.reason)),
        semantic=SemanticContext(capability=Availability.UNAVAILABLE, reason="Semantic engine is unavailable.", freshness=fresh(Availability.UNAVAILABLE, "Semantic engine is unavailable.")),
        pipeline=PipelineContext(running=None, freshness=fresh(Availability.UNAVAILABLE, "Pipeline is unavailable.")),
        ai=AIContext(chat=Availability.UNAVAILABLE, provider_configured=False, evidence_grounding=Availability.UNAVAILABLE, voice=VoiceCapability(push_to_talk=Availability.UNAVAILABLE, hands_free=Availability.UNAVAILABLE)),
        suggestions=[],
    )


def test_live_capability_is_unavailable_when_disabled_or_missing_key():
    disabled = get_live_capabilities(live_settings(enabled=False), sdk_available=lambda: True)
    missing_key = get_live_capabilities(live_settings(api_key=""), sdk_available=lambda: True)

    assert disabled.availability == Availability.UNAVAILABLE
    assert "disabled" in (disabled.reason or "").lower()
    assert missing_key.availability == Availability.UNAVAILABLE
    assert "GEMINI_API_KEY" in (missing_key.reason or "")


def test_native_audio_capability_contract_exposes_rates_but_not_provider_internals():
    capability = get_live_capabilities(live_settings(), sdk_available=lambda: True)
    payload = capability.model_dump(by_alias=True, exclude_none=True)

    assert payload["nativeAudio"] is True
    assert payload["inputSampleRate"] == 16_000
    assert payload["outputSampleRate"] == 24_000
    assert "model" not in payload
    assert "voice" not in payload


def test_native_audio_sample_rates_are_validated_at_configuration_boundary():
    with pytest.raises(ValueError):
        GeminiLiveSettings(input_sample_rate=7_999)
    with pytest.raises(ValueError):
        GeminiLiveSettings(output_sample_rate=48_001)


def test_browser_protocol_supports_typed_interruption_without_audio_persistence():
    event = BrowserVoiceEnvelope.model_validate({"version": "1.0", "type": "interrupt"})

    assert event.type == "interrupt"
    assert "audio" not in event.model_dump(exclude_none=True)


def test_unauthenticated_websocket_handshake_is_rejected():
    app = FastAPI()
    app.include_router(ws_router)
    client = TestClient(app)

    with pytest.raises(WebSocketDisconnect) as disconnected:
        with client.websocket_connect("/ws/intelligence/live/unknown-session"):
            pass

    assert disconnected.value.code == 4401


@pytest.mark.asyncio
async def test_voice_session_creation_and_teardown_invalidates_connection_token():
    manager = LiveSessionManager(settings_getter=live_settings, sdk_available=lambda: True)

    created = await manager.create("api-key-authenticated-operator")
    claimed = await manager.claim_connection(created.session_id, created.connection_token)

    assert created.capabilities.native_audio is True
    assert claimed is not None
    assert await manager.close(created.session_id) is True
    assert await manager.claim_connection(created.session_id, created.connection_token) is None


def context_with_verified_alert(*, level: str = "HIGH", freshness_status: Availability = Availability.LIVE) -> IntelligenceContext:
    context = context_with_cameras()
    observed = now()
    alert = RiskAlertItem(
        alert_id="alert-verified-1",
        level=level,
        acknowledged=False,
        freshness=Freshness(observed_at=observed, status=freshness_status),
        evidence=[
            EvidenceRef(
                kind="alert",
                id="alert-verified-1",
                label="Validated North Gate risk alert",
                camera_id="north-gate",
                server_validated=True,
                validated_at=observed,
            )
        ],
    )
    return context.model_copy(update={
        "alerts": AlertsContext(
            active_count=1,
            items=[alert],
            freshness=Freshness(observed_at=observed, status=Availability.LIVE),
        ),
    })


@pytest.mark.asyncio
async def test_audible_alert_session_revalidates_fresh_high_risk_context_server_side():
    manager = LiveSessionManager(
        settings_getter=live_settings,
        sdk_available=lambda: True,
        context_getter=context_with_verified_alert,
    )

    created = await manager.create("api-key-authenticated-operator", audible_alert_id="alert-verified-1")
    claimed = await manager.claim_connection(created.session_id, created.connection_token)

    assert claimed is not None
    assert claimed.audible_alert is not None
    assert claimed.audible_alert.level == "HIGH"
    assert claimed.audible_alert.text == "High-risk event detected near north-gate. Evidence has been saved. Operator review is required."


@pytest.mark.asyncio
async def test_audible_alert_is_allowed_when_another_capability_degrades_the_overall_context():
    context = context_with_verified_alert()
    context = context.model_copy(
        update={"overall": context.overall.model_copy(update={"status": Availability.DEGRADED})}
    )
    manager = LiveSessionManager(
        settings_getter=live_settings,
        sdk_available=lambda: True,
        context_getter=lambda: context,
    )

    created = await manager.create("api-key-authenticated-operator", audible_alert_id="alert-verified-1")
    claimed = await manager.claim_connection(created.session_id, created.connection_token)

    assert claimed is not None
    assert claimed.audible_alert is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("level,freshness_status", [("MEDIUM", Availability.LIVE), ("CRITICAL", Availability.STALE)])
async def test_audible_alert_session_fails_closed_for_non_speakable_or_stale_records(level, freshness_status):
    manager = LiveSessionManager(
        settings_getter=live_settings,
        sdk_available=lambda: True,
        context_getter=lambda: context_with_verified_alert(level=level, freshness_status=freshness_status),
    )

    with pytest.raises(LiveCapabilityError):
        await manager.create("api-key-authenticated-operator", audible_alert_id="alert-verified-1")


@pytest.mark.asyncio
async def test_completed_provider_turn_keeps_the_live_relay_open_for_the_next_turn():
    second_receive_started = asyncio.Event()
    release_second_receive = asyncio.Event()
    stopped = asyncio.Event()
    handled = []

    async def handle(message):
        handled.append(message)

    class TurnScopedReceiveSession:
        receive_calls = 0

        def receive(self):
            self.receive_calls += 1
            call_number = self.receive_calls

            async def stream():
                if call_number == 1:
                    yield "first completed provider turn"
                    return
                second_receive_started.set()
                await release_second_receive.wait()

            return stream()

    session = TurnScopedReceiveSession()
    task = asyncio.create_task(_receive_provider_turns(session, stopped, handle))

    await asyncio.wait_for(second_receive_started.wait(), timeout=1)
    assert handled == ["first completed provider turn"]
    assert not task.done()

    stopped.set()
    release_second_receive.set()
    await asyncio.wait_for(task, timeout=1)


@pytest.mark.asyncio
async def test_native_audio_frames_are_forwarded_as_binary_and_turn_completion_is_typed():
    emitted = []
    output_frames = []
    managed = SimpleNamespace(correlation_id="correlation-audio")

    async def emit(envelope):
        emitted.append(envelope)

    async def send_audio(frame: bytes):
        output_frames.append(frame)

    bridge = GeminiLiveVoiceSession(
        managed_session=managed,
        gemini_session=object(),
        emit=emit,
        send_audio=send_audio,
        input_sample_rate=16_000,
        output_sample_rate=24_000,
    )
    turn_id = bridge.begin_turn()
    await bridge.forward_native_audio(b"\x00\x00\x01\x00")
    await bridge.finish_turn()

    assert output_frames == [b"\x00\x00\x01\x00"]
    assert [event.type for event in emitted] == ["turn_complete", "state"]
    assert emitted[0].turn_id == turn_id
    assert emitted[1].state.value == "ready"


@pytest.mark.asyncio
async def test_native_audio_bridge_rejects_invalid_chunk_size_without_retaining_audio():
    bridge = GeminiLiveVoiceSession(
        managed_session=SimpleNamespace(correlation_id="correlation-audio"),
        gemini_session=object(),
        emit=lambda _: asyncio.sleep(0),
        send_audio=lambda _: asyncio.sleep(0),
        input_sample_rate=16_000,
        output_sample_rate=24_000,
    )

    with pytest.raises(ValueError):
        await bridge.forward_native_audio(b"x" * (64 * 1024 + 1))


def test_camera_status_tool_uses_actual_runtime_context_and_audits_correlation_id():
    audits = []
    registry = LiveToolRegistry(
        session_id="session-1",
        operator_id="api-key-authenticated-operator",
        correlation_id="correlation-1",
        context_getter=context_with_cameras,
        audit_sink=audits.append,
    )

    result = registry.execute("get_live_camera_status")

    assert result.data["total"] == 2
    assert result.data["online"] == 1
    assert result.data["offline"] == 1
    assert {citation.evidence_id for citation in result.citations} == {"camera:gate-2", "camera:parking-east"}
    assert audits[0].correlation_id == "correlation-1"
    assert audits[0].result_status == Availability.LIVE


def test_unavailable_runtime_never_becomes_a_zero_camera_answer():
    registry = LiveToolRegistry(
        session_id="session-2",
        operator_id="api-key-authenticated-operator",
        correlation_id="correlation-2",
        context_getter=lambda: context_with_cameras(unavailable=True),
    )

    result = registry.execute("get_live_camera_status")

    assert result.availability == Availability.UNAVAILABLE
    assert result.data["total"] is None
    assert result.data["online"] is None
    assert "unavailable" in (result.reason or "").lower()


def test_tool_allowlist_and_citation_validation_reject_unsafe_actions():
    registry = LiveToolRegistry(
        session_id="session-3",
        operator_id="api-key-authenticated-operator",
        correlation_id="correlation-3",
        context_getter=context_with_cameras,
    )

    with pytest.raises(ToolNotAllowedError):
        registry.execute("navigate", {"url": "javascript:alert(1)"})

    unknown = registry.execute("open_authorised_evidence", {"evidence_id": "event:unknown"})
    assert unknown.availability == Availability.UNAVAILABLE

    camera_result = registry.execute("get_live_camera_status")
    opened = registry.execute("open_authorised_evidence", {"evidence_id": camera_result.citations[0].evidence_id})
    assert opened.ui_command is not None
    assert opened.ui_command.kind == UICommandKind.OPEN_CAMERAS


def test_audit_records_have_no_audio_payload_and_are_correlated():
    manager = LiveSessionManager(settings_getter=live_settings, sdk_available=lambda: True)
    registry = LiveToolRegistry(
        session_id="session-4",
        operator_id="api-key-authenticated-operator",
        correlation_id="correlation-4",
        context_getter=context_with_cameras,
        audit_sink=manager.record_audit,
    )

    registry.execute("get_pipeline_health")
    audit = manager.audit_records()[0]

    assert audit.correlation_id == "correlation-4"
    assert audit.session_id == "session-4"
    assert "audio" not in audit.arguments
    assert audit.latency_ms >= 0


def test_gateway_serializes_timestamped_citations_before_websocket_delivery():
    observed_at = now()
    envelope = ServerVoiceEnvelope(
        type="citations",
        citations=[
            LiveCitation(
                evidence_id="camera:gate-2",
                kind="camera",
                label="Gate 2 runtime state",
                observed_at=observed_at,
                availability=Availability.LIVE,
            )
        ],
        correlation_id="correlation-5",
    )

    payload = _voice_envelope_payload(envelope)

    assert json.dumps(payload)
    assert payload["citations"][0]["observedAt"] == observed_at.isoformat().replace("+00:00", "Z")
