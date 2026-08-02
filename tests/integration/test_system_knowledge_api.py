"""Authorization and API regression tests for system knowledge integration."""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from aegis.database.connection import Base
import aegis.database.models  # noqa: F401
from aegis.knowledge.official_records import OFFICIAL_KNOWLEDGE
from aegis.knowledge.service import SystemKnowledgeService


@pytest.fixture()
def local_knowledge_service(tmp_path):
    # File-backed SQLite makes the fixture visible to TestClient's worker
    # thread without touching any project or production database.
    engine = create_engine(
        f"sqlite:///{tmp_path / 'system-knowledge-test.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    @contextmanager
    def session_provider():
        with Session.begin() as session:
            yield session
    with Session.begin() as session:
        service = SystemKnowledgeService(session_provider=session_provider)
        service.seed_official(OFFICIAL_KNOWLEDGE, session=session)
    yield service
    engine.dispose()


@pytest.fixture()
def knowledge_client(monkeypatch, local_knowledge_service):
    monkeypatch.setenv("AEGIS_API_KEY", "operator-key")
    monkeypatch.setenv("AEGIS_ADMIN_API_KEY", "admin-key")
    from aegis.api.routes import system_knowledge as knowledge_routes

    monkeypatch.setattr(knowledge_routes, "get_system_knowledge_service", lambda: local_knowledge_service)
    app = FastAPI()
    app.include_router(knowledge_routes.router)
    app.include_router(knowledge_routes.admin_router)
    return TestClient(app)


def test_public_search_is_authenticated_and_hides_sensitive_fields(knowledge_client):
    response = knowledge_client.get("/api/system-knowledge/search?q=Who%20created%20Aegis%3F", headers={"X-API-Key": "operator-key"})
    assert response.status_code == 200
    record = response.json()["records"][0]
    assert record["key"] == "aegis.creator.profile"
    assert "id" not in record
    assert "source" not in record
    assert "created_by" not in record


def test_normal_user_cannot_modify_knowledge(knowledge_client):
    response = knowledge_client.post(
        "/api/admin/system-knowledge",
        headers={"X-API-Key": "operator-key"},
        json={"key": "test.new", "category": "project_profile", "title": "Test", "content": "Test", "source": "test"},
    )
    assert response.status_code == 403


def test_admin_can_create_version_restore_and_view_audit(knowledge_client):
    headers = {"X-API-Key": "operator-key", "X-Aegis-Admin-Key": "admin-key"}
    created = knowledge_client.post(
        "/api/admin/system-knowledge", headers=headers,
        json={"key": "test.admin-record", "category": "project_profile", "title": "Test", "content": "Original", "source": "test"},
    )
    assert created.status_code == 201
    record = created.json()
    changed = knowledge_client.patch(f"/api/admin/system-knowledge/{record['id']}", headers=headers, json={"content": "Changed"})
    assert changed.status_code == 200
    assert changed.json()["version"] == 2
    audit = knowledge_client.get(f"/api/admin/system-knowledge/{changed.json()['id']}/audit", headers=headers)
    assert audit.status_code == 200
    assert any(item["action"] == "version_created" for item in audit.json())
    restored = knowledge_client.post(f"/api/admin/system-knowledge/{record['id']}/restore", headers=headers)
    assert restored.status_code == 201
    assert restored.json()["content"] == "Original"


def test_chat_and_voice_use_shared_database_retrieval(monkeypatch, local_knowledge_service):
    monkeypatch.setenv("AEGIS_API_KEY", "operator-key")
    import aegis.ai.orchestrator as orchestrator
    import aegis.ai.routes as ai_routes

    monkeypatch.setattr(orchestrator, "get_system_knowledge_service", lambda: local_knowledge_service)
    app = FastAPI()
    app.include_router(ai_routes.router)
    client = TestClient(app)
    headers = {"X-API-Key": "operator-key"}
    chat = client.post("/api/ai/chat", headers=headers, json={"message": "Who created Aegis?"})
    voice = client.post("/api/ai/voice", headers=headers, json={"text": "What did Hassan do in Aegis?"})
    assert chat.status_code == 200 and "Hassan" in chat.json()["answer"]
    assert voice.status_code == 200 and "semantic evidence search" in voice.json()["answer"]


def test_ai_context_exposes_only_safe_knowledge_capability_metadata(monkeypatch, local_knowledge_service):
    monkeypatch.setenv("AEGIS_API_KEY", "operator-key")
    import aegis.ai.routes as ai_routes
    import aegis.intelligence.context_service as context_service
    import aegis.knowledge.service as knowledge_service

    class Snapshot:
        def model_dump(self, **_kwargs):
            return {"generatedAt": "2026-07-31T00:00:00Z"}

    class ContextService:
        def build(self):
            return Snapshot()

    monkeypatch.setattr(context_service, "get_intelligence_context_service", lambda: ContextService())
    monkeypatch.setattr(knowledge_service, "get_system_knowledge_service", lambda: local_knowledge_service)
    app = FastAPI()
    app.include_router(ai_routes.router)
    response = TestClient(app).get("/api/ai/context", headers={"X-API-Key": "operator-key"})
    assert response.status_code == 200
    metadata = response.json()["officialKnowledge"]
    assert metadata["availability"] == "available"
    assert metadata["publicRecordsAvailable"] == 2
    assert "records" not in metadata
