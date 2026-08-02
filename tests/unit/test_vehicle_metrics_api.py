"""The Prometheus diagnostics endpoint stays API-key protected."""

from __future__ import annotations

import os

from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

from aegis.api.routes.metrics import router
from aegis.api.security import verify_api_key


def test_metrics_endpoint_requires_api_key(monkeypatch) -> None:
    monkeypatch.setenv("AEGIS_API_KEY", "metrics-test-key")
    app = FastAPI()
    app.include_router(router, dependencies=[Depends(verify_api_key)])
    client = TestClient(app)
    assert client.get("/metrics").status_code == 401
    response = client.get("/metrics", headers={"X-API-Key": "metrics-test-key"})
    assert response.status_code == 200
    assert "plate_text" not in response.text
