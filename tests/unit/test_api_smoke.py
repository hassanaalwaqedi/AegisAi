"""
AegisAI — API Smoke Tests

Validates that all critical API endpoints respond correctly.
These tests use FastAPI's TestClient (no live server needed).

NOTE: We mock cv2 to avoid importing the full ML pipeline,
since we only need the API layer for these tests.
"""

import os
import sys
import types
import pytest

# Set test environment before importing anything from aegis
os.environ["AEGIS_API_KEY"] = "test-key-12345"
os.environ["AEGIS_DEBUG"] = "true"

# Mock heavy ML dependencies that aren't needed for API tests
_mock_modules = [
    "cv2", "ultralytics", "supervision",
    "torch", "torchvision", "mediapipe",
]
for mod_name in _mock_modules:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)

from aegis.api.app import create_app
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    """Create a test client for the AegisAI API."""
    app = create_app()
    return TestClient(app)


@pytest.fixture(scope="module")
def auth_headers():
    """Headers with valid API key."""
    return {"X-API-Key": "test-key-12345"}


# ─── Health & Root ──────────────────────────────────────────

class TestRootEndpoints:
    """Test root and health endpoints (no auth required)."""

    def test_root_returns_200(self, client):
        """Root endpoint should return 200 with API info."""
        resp = client.get("/")
        assert resp.status_code == 200

    def test_api_info(self, client):
        """API info endpoint should return version and endpoint list."""
        resp = client.get("/api")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data
        assert "endpoints" in data


# ─── Status Endpoints ───────────────────────────────────────

class TestStatusEndpoints:
    """Test system status endpoints."""

    def test_status_returns_system_info(self, client, auth_headers):
        """GET /status should return system status object."""
        resp = client.get("/status", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "system" in data or "status" in data

    def test_status_health(self, client, auth_headers):
        """GET /status/health should return health check."""
        resp = client.get("/status/health", headers=auth_headers)
        assert resp.status_code == 200

    def test_status_performance(self, client, auth_headers):
        """GET /status/performance should return perf metrics."""
        resp = client.get("/status/performance", headers=auth_headers)
        assert resp.status_code == 200


# ─── Security ───────────────────────────────────────────────

class TestSecurity:
    """Test API security layer."""

    def test_missing_api_key_returns_401(self, client):
        """Requests without API key should get 401."""
        resp = client.get("/status")
        assert resp.status_code == 401

    def test_wrong_api_key_returns_401(self, client):
        """Requests with wrong API key should get 401."""
        resp = client.get("/status", headers={"X-API-Key": "wrong-key"})
        assert resp.status_code == 401

    def test_valid_api_key_passes(self, client, auth_headers):
        """Requests with correct API key should succeed."""
        resp = client.get("/status", headers=auth_headers)
        assert resp.status_code == 200


# ─── Data Endpoints ─────────────────────────────────────────

class TestDataEndpoints:
    """Test data retrieval endpoints."""

    def test_tracks_returns_list(self, client, auth_headers):
        """GET /tracks should return a list."""
        resp = client.get("/tracks", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), (list, dict))

    def test_events_returns_data(self, client, auth_headers):
        """GET /events should return events data."""
        resp = client.get("/events", headers=auth_headers)
        assert resp.status_code == 200

    def test_statistics_returns_data(self, client, auth_headers):
        """GET /statistics should return crowd/risk stats."""
        resp = client.get("/statistics", headers=auth_headers)
        assert resp.status_code == 200

    def test_alerts_returns_list(self, client, auth_headers):
        """GET /alerts should return alerts."""
        resp = client.get("/alerts", headers=auth_headers)
        assert resp.status_code == 200

    def test_alerts_summary(self, client, auth_headers):
        """GET /alerts/summary should return summary object."""
        resp = client.get("/alerts/summary", headers=auth_headers)
        assert resp.status_code == 200


# ─── Mode Endpoint ──────────────────────────────────────────

class TestModeEndpoint:
    """Test pipeline mode endpoint."""

    def test_get_mode(self, client):
        """GET /mode should return current pipeline mode (no auth)."""
        resp = client.get("/mode")
        assert resp.status_code == 200
        data = resp.json()
        assert "mode" in data


# ─── WebSocket ──────────────────────────────────────────────

class TestWebSocket:
    """Test WebSocket connectivity."""

    def test_ws_client_count(self, client):
        """GET /ws/clients should return connection count."""
        resp = client.get("/ws/clients")
        assert resp.status_code == 200
        assert "count" in resp.json()

    def test_ws_connects(self, client):
        """WebSocket should accept connections and send update."""
        with client.websocket_connect("/ws") as ws:
            data = ws.receive_json()
            assert data["type"] == "update"
            assert "timestamp" in data
