"""Focused tests for database-backed official creator and project knowledge."""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from aegis.database.connection import Base
import aegis.database.models  # noqa: F401 - register mapped tables
from aegis.knowledge.official_records import OFFICIAL_KNOWLEDGE
from aegis.knowledge.schemas import KnowledgeCategory, KnowledgeUpdate, KnowledgeVisibility, KnowledgeWrite
from aegis.knowledge.service import NOT_DOCUMENTED, SystemKnowledgeService


@pytest.fixture()
def knowledge_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session.begin() as session:
        service = SystemKnowledgeService()
        report = service.seed_official(OFFICIAL_KNOWLEDGE, session=session)
        assert report.inserted == 10
    with Session() as session:
        yield service, session
    engine.dispose()


def test_creator_question_english_returns_approved_database_facts(knowledge_db):
    service, session = knowledge_db
    result = service.retrieve("Who created Aegis?", session=session)
    assert result.availability == "available"
    assert result.locale == "en"
    assert [record.category for record in result.records] == ["creator_profile", "creator_contributions"]
    assert "created and designed by Hassan" in result.answer
    assert "worked on the overall AegisAI system architecture" in result.answer
    designed = service.retrieve("Who designed this system?", session=session)
    assert designed.records[0].category == "creator_profile"
    assert "Hassan" in designed.answer


def test_creator_question_arabic_uses_arabic_database_content(knowledge_db):
    service, session = knowledge_db
    result = service.retrieve("من أنشأ Aegis؟", session=session)
    assert result.locale == "ar"
    assert result.records[0].category == "creator_profile"
    assert "تم إنشاء وتصميم" in result.answer
    assert "حسان" in result.answer


def test_creator_question_turkish_uses_turkish_database_content(knowledge_db):
    service, session = knowledge_db
    result = service.retrieve("Aegis kim tarafından oluşturuldu?", session=session)
    assert result.locale == "tr"
    assert result.records[0].category == "creator_profile"
    assert "Hassan tarafından" in result.answer


def test_contribution_question_returns_only_stored_contributions(knowledge_db):
    service, session = knowledge_db
    result = service.retrieve("What did Hassan do in Aegis?", session=session)
    assert [record.category for record in result.records] == ["creator_contributions"]
    assert "semantic evidence search" in result.answer
    assert "only contributor" not in result.answer.lower()


def test_project_and_technology_questions_rank_matching_categories(knowledge_db):
    service, session = knowledge_db
    project = service.retrieve("What is Aegis?", session=session)
    technology = service.retrieve("What technologies were used?", session=session)
    assert project.records[0].category == "project_profile"
    assert "authorized camera feeds" in project.answer
    assert [record.category for record in technology.records] == ["project_technology"]
    assert "FastAPI" in technology.answer
    assert "Google Gemini" in technology.answer


def test_inactive_and_private_records_never_enter_public_retrieval(knowledge_db):
    service, session = knowledge_db
    profile = service.retrieve("Who created Aegis?", session=session).records[0]
    versions = service.versions(profile.key, session=session)
    service.set_active(versions[0].id, is_active=False, actor="test-admin", session=session)
    result = service.retrieve("Who created Aegis?", session=session)
    assert all(record.category != "creator_profile" for record in result.records)

    private = KnowledgeWrite(
        key="private.creator.note", category=KnowledgeCategory.CREATOR_PROFILE,
        title="Private", content="Secret creator detail", visibility=KnowledgeVisibility.PRIVATE,
        priority=1000, source="test", structured_data={"aliases": ["secret creator detail"]},
    )
    service.create(private, actor="test-admin", session=session)
    private_result = service.retrieve("secret creator detail", session=session)
    assert all(record.key != "private.creator.note" for record in private_result.records)
    assert "Secret creator detail" not in private_result.answer


def test_seed_is_idempotent_and_preserves_administrator_edit_without_force(knowledge_db):
    service, session = knowledge_db
    current = service.versions("aegis.creator.profile", session=session)[0]
    edited = service.create_version(
        current.id,
        KnowledgeUpdate(content="Administrator-approved creator profile.", content_en="Administrator-approved creator profile."),
        actor="test-admin", session=session,
    )
    report = service.seed_official(OFFICIAL_KNOWLEDGE, session=session)
    assert report.as_dict() == {"inserted": 0, "updated": 0, "skipped": 10, "failed": 0}
    assert service.versions("aegis.creator.profile", session=session)[0].id == edited.id
    assert service.versions("aegis.creator.profile", session=session)[0].content == "Administrator-approved creator profile."

    forced = service.seed_official(OFFICIAL_KNOWLEDGE, force=True, session=session)
    assert forced.updated == 10
    assert "created and designed by Hassan" in service.versions("aegis.creator.profile", session=session)[0].content


def test_versions_restore_and_audit_are_append_only(knowledge_db):
    service, session = knowledge_db
    original = service.versions("aegis.creator.profile", session=session)[0]
    updated = service.create_version(original.id, KnowledgeUpdate(title="Changed title"), actor="test-admin", session=session)
    restored = service.restore(original.id, actor="test-admin", session=session)
    versions = service.versions(original.key, session=session)
    assert [record.version for record in versions] == [3, 2, 1]
    assert restored.id != original.id
    assert restored.title == original.title
    assert sum(record.is_active for record in versions) == 1
    actions = [item.action for item in service.audit_history(updated.id, session=session)]
    assert "version_created" in actions


def test_missing_facts_do_not_hallucinate_and_localized_fallback_is_explicit(knowledge_db):
    service, session = knowledge_db
    missing = service.retrieve("Who funded Aegis?", session=session)
    assert missing.is_official_question
    assert not missing.records
    assert NOT_DOCUMENTED[missing.locale] == "This information is not currently documented in Aegis."

    english_only = KnowledgeWrite(
        key="aegis.project.custom-limit", category=KnowledgeCategory.PROJECT_LIMITATIONS,
        title="English-only limit", content="This is only documented in English.", content_en="This is only documented in English.",
        structured_data={"aliases": ["حد خاص"]}, source="test", priority=1000,
    )
    service.create(english_only, actor="test-admin", session=session)
    result = service.retrieve("ما هو الحد خاص؟", session=session)
    assert result.locale == "ar"
    assert result.records[0].content == "This is only documented in English."


def test_database_failure_returns_truthful_unavailable(monkeypatch, knowledge_db):
    service, session = knowledge_db
    from aegis.database.repositories import SystemKnowledgeRepository

    def fail(_self):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(SystemKnowledgeRepository, "list_active_public", fail)
    result = service.retrieve("Who created Aegis?", session=session)
    assert result.availability == "unavailable"
    assert not result.records


def test_live_voice_tool_uses_the_same_public_database_retrieval(monkeypatch, knowledge_db):
    service, session = knowledge_db
    import aegis.knowledge.service as knowledge_service
    from aegis.intelligence.live_tools import LiveToolRegistry

    class ServiceProxy:
        def retrieve(self, *args, **kwargs):
            return service.retrieve(*args, session=session, **kwargs)

    monkeypatch.setattr(knowledge_service, "get_system_knowledge_service", lambda: ServiceProxy())
    registry = LiveToolRegistry(session_id="test", operator_id="operator", correlation_id="correlation")
    result = registry.execute("get_official_system_knowledge", {"query": "Who created Aegis?", "locale": "en"})
    assert result.availability.value == "live"
    assert result.data["facts"][0]["content"].startswith("AegisAI was created and designed by Hassan")
    assert not result.citations
