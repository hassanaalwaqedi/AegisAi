"""Focused regression coverage for Phase 1 production blockers."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


def _client(monkeypatch: pytest.MonkeyPatch, api_key: str | None) -> TestClient:
    if api_key is None:
        # The shared test bootstrap provides a key. An explicit empty value
        # exercises the same missing-configuration path without reloading it.
        monkeypatch.setenv("AEGIS_API_KEY", "")
    else:
        monkeypatch.setenv("AEGIS_API_KEY", api_key)
    from aegis.api.app import create_app

    return TestClient(create_app())


def test_protected_api_fails_closed_without_configured_key(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch, None)

    response = client.get("/status")

    assert response.status_code == 503
    assert response.json()["detail"] == "API authentication is not configured."

    readiness = client.get("/readyz")
    assert readiness.status_code == 503
    assert readiness.json()["checks"]["api_authentication"]["status"] == "error"


def test_protected_api_rejects_wrong_and_accepts_correct_key(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch, "phase1-test-key")

    assert client.get("/status").status_code == 401
    assert client.get("/status", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get("/status", headers={"X-API-Key": "phase1-test-key"}).status_code == 200


def test_websocket_rejects_unauthenticated_client(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch, "phase1-test-key")

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws") as socket:
            socket.receive_json()


def test_websocket_accepts_authenticated_service_client(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch, "phase1-test-key")

    with client.websocket_connect("/ws", headers={"X-API-Key": "phase1-test-key"}) as socket:
        assert socket.receive_json()["type"] in {"update", "heartbeat"}


def test_camera_websocket_rejects_unauthenticated_client(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch, "phase1-test-key")

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/cameras/not-a-camera/frames") as socket:
            socket.receive_json()


def test_legacy_intelligence_and_operations_do_not_return_demo_data(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch, "phase1-test-key")
    headers = {"X-API-Key": "phase1-test-key"}

    nlq = client.post("/intelligence/nlq", headers=headers, json={"query": "How many critical alerts?"})
    operations = client.get("/operations/metrics", headers=headers)

    assert nlq.status_code == 503
    assert nlq.json()["detail"]["code"] == "verified_data_unavailable"
    assert operations.status_code == 503
    assert operations.json()["detail"]["code"] == "verified_data_unavailable"
