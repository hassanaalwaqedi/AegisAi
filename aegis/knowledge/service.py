"""Shared, database-backed retrieval and administration for official Aegis knowledge."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import re
from typing import Any, Callable, ContextManager, Dict, Iterator, List, Optional, Sequence

from sqlalchemy.orm import Session

from aegis.database.connection import get_db_session
from aegis.database.models import SystemKnowledge, SystemKnowledgeAudit
from aegis.database.repositories import SystemKnowledgeRepository
from aegis.knowledge.schemas import (
    KnowledgeAdminRecord,
    KnowledgeAuditRecord,
    KnowledgeCategory,
    KnowledgePublicRecord,
    KnowledgeUpdate,
    KnowledgeVisibility,
    KnowledgeWrite,
)

logger = logging.getLogger(__name__)


NOT_DOCUMENTED = {
    "en": "This information is not currently documented in Aegis.",
    "ar": "هذه المعلومات غير موثقة حاليًا في نظام Aegis.",
    "tr": "Bu bilgi şu anda Aegis içinde belgelenmemiştir.",
}
UNAVAILABLE = {
    "en": "Official Aegis knowledge is temporarily unavailable.",
    "ar": "معرفة Aegis الرسمية غير متاحة مؤقتًا.",
    "tr": "Resmî Aegis bilgisi geçici olarak kullanılamıyor.",
}

_CATEGORY_TERMS = {
    "creator": ("creator_profile", "creator_contributions"),
    "contributions": ("creator_contributions",),
    "project": ("project_profile", "project_purpose"),
    "technology": ("project_technology",),
    "architecture": ("project_architecture",),
    "capabilities": ("project_capabilities",),
    "security": ("project_security",),
    "limitations": ("project_limitations",),
}

_INTENT_TERMS = {
    "creator": ("hassan", "creator", "created", "create", "designed", "design", "من أنشأ", "من صمم", "حسان", "kim oluştur", "kim tasarl", "oluşturdu", "tasarladı"),
    "contributions": ("what did hassan", "hassan do", "contribution", "worked on", "ماذا فعل", "مساهم", "ماذا عمل", "ne yaptı", "katkı", "üzerinde çalış"),
    "project": ("what is aegis", "about aegis", "what does aegis", "aegis nedir", "ما هو aegis", "ماهي aegis", "ما هو نظام"),
    "technology": ("technolog", "tech stack", "what is used", "hangi teknoloj", "teknoloji", "التقنيات", "تكنولوجيا"),
    "architecture": ("architecture", "how is aegis built", "backend frontend", "mimari", "بنية"),
    "capabilities": ("computer vision", "detection", "tracking", "ai assistant", "voice", "chat", "camera feed", "رؤية حاسوبية", "كشف", "تتبع", "صوت", "مساعد", "bilgisayarlı görü", "takip", "ses", "yapay zekâ"),
    "security": ("security", "authorization", "permission", "rbac", "أمان", "صلاحيات", "güvenlik", "yetkilendirme"),
    "limitations": ("limitation", "cannot aegis", "limits", "قيود", "محدود", "sınırlama"),
}
_STOP_WORDS = {
    "what", "is", "who", "did", "the", "a", "an", "and", "in", "of", "for", "to", "about", "tell", "me", "please", "aegis", "aegisai",
    "ما", "هو", "من", "في", "عن", "هل", "هذا", "نظام", "kim", "ne", "nedir", "ve", "bir", "bu", "için", "hakkında",
}


@dataclass(frozen=True)
class RetrievedKnowledge:
    key: str
    category: str
    title: str
    content: str
    priority: int
    version: int
    source: str


@dataclass(frozen=True)
class RetrievalResult:
    availability: str
    locale: str
    records: Sequence[RetrievedKnowledge]
    reason: Optional[str] = None
    is_official_question: bool = False

    @property
    def answer(self) -> str:
        return " ".join(record.content.strip() for record in self.records if record.content.strip())


@dataclass
class SeedReport:
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0

    def as_dict(self) -> Dict[str, int]:
        return {"inserted": self.inserted, "updated": self.updated, "skipped": self.skipped, "failed": self.failed}


class SeedFailed(RuntimeError):
    """A transactional seed error that still exposes its non-sensitive report."""

    def __init__(self, report: SeedReport) -> None:
        super().__init__("Official system-knowledge seed failed and was rolled back.")
        self.report = report


def detect_locale(text: str) -> str:
    """Use script and Turkish-specific terms; default is the configured English fallback."""
    if re.search(r"[\u0600-\u06ff]", text):
        return "ar"
    lowered = text.lower()
    if re.search(r"[çğıöşü]", lowered) or any(term in lowered for term in (" nedir", " kim", "hangi", "teknoloji", "oluştur", "tasarl", "katkı", "hakkında")):
        return "tr"
    return "en"


def _normalise(value: str) -> str:
    return " ".join(re.findall(r"[\wçğıöşüâîûء-ي]+", value.lower(), flags=re.UNICODE))


def _snapshot(record: SystemKnowledge) -> Dict[str, Any]:
    """JSON-safe record snapshot kept only in the administrative audit table."""
    return {
        "id": str(record.id), "key": record.key, "category": record.category,
        "title": record.title, "content": record.content, "content_ar": record.content_ar,
        "content_en": record.content_en, "content_tr": record.content_tr,
        "structured_data": record.structured_data or {}, "visibility": record.visibility,
        "priority": record.priority, "source": record.source, "is_active": record.is_active,
        "version": record.version, "created_by": record.created_by, "updated_by": record.updated_by,
    }


def _from_payload(payload: KnowledgeWrite, *, version: int, actor: str, is_active: bool = True) -> SystemKnowledge:
    now = datetime.now(timezone.utc)
    return SystemKnowledge(
        key=payload.key,
        category=payload.category.value,
        title=payload.title,
        content=payload.content,
        content_ar=payload.content_ar,
        content_en=payload.content_en or payload.content,
        content_tr=payload.content_tr,
        structured_data=payload.structured_data,
        visibility=payload.visibility.value,
        priority=payload.priority,
        source=payload.source,
        is_active=is_active,
        version=version,
        created_by=actor,
        updated_by=actor,
        published_at=now if is_active else None,
    )


class SystemKnowledgeService:
    """One retrieval path for chat, voice, API context, admin APIs, and Live tools."""

    def __init__(self, session_provider: Optional[Callable[[], ContextManager[Session]]] = None) -> None:
        self._session_provider = session_provider or get_db_session

    @contextmanager
    def _session(self, session: Optional[Session] = None) -> Iterator[Session]:
        if session is not None:
            yield session
            return
        with self._session_provider() as db:
            yield db

    @staticmethod
    def _intent(query: str) -> Optional[str]:
        normalised = _normalise(query)
        # Contributions must win over a generic creator match for a direct work question.
        for intent in ("contributions", "technology", "architecture", "security", "limitations", "capabilities", "creator", "project"):
            if any(term in normalised for term in _INTENT_TERMS[intent]):
                return intent
        return None

    @staticmethod
    def _localized(record: SystemKnowledge, locale: str) -> str:
        if locale == "ar" and record.content_ar:
            return record.content_ar
        if locale == "tr" and record.content_tr:
            return record.content_tr
        if locale == "en" and record.content_en:
            return record.content_en
        # The canonical content field is the configured English fallback.
        return record.content

    @staticmethod
    def _aliases(record: SystemKnowledge) -> List[str]:
        data = record.structured_data if isinstance(record.structured_data, dict) else {}
        aliases = data.get("aliases", [])
        return [str(alias) for alias in aliases if isinstance(alias, str)]

    def _score(self, record: SystemKnowledge, query: str, intent: Optional[str]) -> int:
        normalised = _normalise(query)
        score = record.priority
        if intent:
            wanted = _CATEGORY_TERMS[intent]
            if record.category in wanted:
                score += 10_000 - wanted.index(record.category) * 500
            else:
                return -1
        aliases = [_normalise(value) for value in self._aliases(record)]
        for alias in aliases:
            if alias and alias in normalised:
                score += 2_000 if alias == normalised else 500
        haystack = _normalise(" ".join([record.title, record.content, record.content_ar or "", record.content_tr or ""]))
        terms = [term for term in normalised.split() if term not in _STOP_WORDS and len(term) > 2]
        score += sum(20 for term in terms if term in haystack)
        return score

    def retrieve(
        self,
        query: str,
        *,
        locale: Optional[str] = None,
        limit: int = 3,
        session: Optional[Session] = None,
    ) -> RetrievalResult:
        locale = locale if locale in {"ar", "en", "tr"} else detect_locale(query)
        intent = self._intent(query)
        official_subject = bool(intent) or "aegis" in _normalise(query) or "حسان" in query
        try:
            with self._session(session) as db:
                records = SystemKnowledgeRepository(db).list_active_public()
                ranked = [(self._score(record, query, intent), record) for record in records]
        except Exception as exc:
            logger.warning("Official knowledge retrieval unavailable: %s", type(exc).__name__)
            return RetrievalResult("unavailable", locale, (), "The system-knowledge database could not be read.", official_subject)

        ranked = [(score, record) for score, record in ranked if score >= 0]
        # An Aegis name alone must not turn an undocumented question into a general project answer.
        if intent is None:
            meaningful = [term for term in _normalise(query).split() if term not in _STOP_WORDS and len(term) > 2]
            ranked = [(score, record) for score, record in ranked if score > record.priority or any(term in _normalise(record.title + " " + record.content) for term in meaningful)]
        ranked.sort(key=lambda item: (item[0], item[1].priority, item[1].version), reverse=True)
        selected = [
            RetrievedKnowledge(
                key=record.key, category=record.category, title=record.title,
                content=self._localized(record, locale), priority=record.priority,
                version=record.version, source=record.source,
            )
            for _, record in ranked[:max(1, min(limit, 10))]
        ]
        return RetrievalResult("available", locale, selected, None if selected else "No relevant active public knowledge record was found.", official_subject)

    def public_search(self, query: str, *, locale: Optional[str] = None, limit: int = 3, session: Optional[Session] = None) -> RetrievalResult:
        return self.retrieve(query, locale=locale, limit=limit, session=session)

    @staticmethod
    def public_projection(record: RetrievedKnowledge) -> KnowledgePublicRecord:
        return KnowledgePublicRecord(
            key=record.key, category=KnowledgeCategory(record.category), title=record.title,
            content=record.content, priority=record.priority, version=record.version,
        )

    @staticmethod
    def admin_projection(record: SystemKnowledge) -> KnowledgeAdminRecord:
        return KnowledgeAdminRecord(
            id=record.id, key=record.key, category=KnowledgeCategory(record.category), title=record.title,
            content=record.content, content_ar=record.content_ar, content_en=record.content_en,
            content_tr=record.content_tr, structured_data=record.structured_data or {},
            visibility=KnowledgeVisibility(record.visibility), priority=record.priority, source=record.source,
            is_active=record.is_active, version=record.version, created_by=record.created_by,
            updated_by=record.updated_by, published_at=record.published_at,
            created_at=record.created_at, updated_at=record.updated_at,
        )

    @staticmethod
    def _audit(repo: SystemKnowledgeRepository, record: SystemKnowledge, *, action: str, actor: str, before: Optional[Dict[str, Any]], after: Optional[Dict[str, Any]]) -> None:
        repo.add_audit(SystemKnowledgeAudit(record_id=record.id, key=record.key, action=action, actor=actor, before=before, after=after))

    def create(self, payload: KnowledgeWrite, *, actor: str, session: Optional[Session] = None) -> SystemKnowledge:
        with self._session(session) as db:
            repo = SystemKnowledgeRepository(db)
            if repo.get_versions(payload.key):
                raise ValueError("A knowledge key already exists; create a new version instead.")
            record = repo.add(_from_payload(payload, version=1, actor=actor))
            self._audit(repo, record, action="created", actor=actor, before=None, after=_snapshot(record))
            return record

    def create_version(self, record_id, payload: KnowledgeUpdate, *, actor: str, session: Optional[Session] = None, action: str = "version_created") -> SystemKnowledge:
        with self._session(session) as db:
            repo = SystemKnowledgeRepository(db)
            current = repo.get(record_id)
            if current is None:
                raise LookupError("Knowledge record was not found.")
            before = _snapshot(current)
            versions = repo.get_versions(current.key)
            next_version = max(item.version for item in versions) + 1
            # Administrators may create a version from an older record (for
            # example via restore).  Retire whichever version is currently
            # active so one key never has competing public facts.
            active_version = repo.get_current_by_key(current.key)
            if active_version is not None:
                active_before = _snapshot(active_version)
                active_version.is_active = False
                active_version.updated_by = actor
                self._audit(repo, active_version, action="superseded", actor=actor, before=active_before, after=_snapshot(active_version))
            update = payload.model_dump(exclude_unset=True)
            clone_data = {
                "key": current.key, "category": update.get("category", KnowledgeCategory(current.category)),
                "title": update.get("title", current.title), "content": update.get("content", current.content),
                "content_ar": update.get("content_ar", current.content_ar), "content_en": update.get("content_en", current.content_en),
                "content_tr": update.get("content_tr", current.content_tr),
                "structured_data": update.get("structured_data", current.structured_data or {}),
                "visibility": update.get("visibility", KnowledgeVisibility(current.visibility)),
                "priority": update.get("priority", current.priority), "source": update.get("source", current.source),
            }
            new_record = repo.add(_from_payload(KnowledgeWrite(**clone_data), version=next_version, actor=actor))
            self._audit(repo, new_record, action=action, actor=actor, before=before, after=_snapshot(new_record))
            return new_record

    def set_active(self, record_id, *, is_active: bool, actor: str, session: Optional[Session] = None) -> SystemKnowledge:
        with self._session(session) as db:
            repo = SystemKnowledgeRepository(db)
            record = repo.get(record_id)
            if record is None:
                raise LookupError("Knowledge record was not found.")
            before = _snapshot(record)
            if is_active:
                previous = repo.get_current_by_key(record.key)
                if previous and previous.id != record.id:
                    previous_before = _snapshot(previous)
                    previous.is_active = False
                    previous.updated_by = actor
                    self._audit(repo, previous, action="superseded", actor=actor, before=previous_before, after=_snapshot(previous))
                record.deleted_at = None
                record.published_at = record.published_at or datetime.now(timezone.utc)
            record.is_active = is_active
            record.updated_by = actor
            self._audit(repo, record, action="activated" if is_active else "deactivated", actor=actor, before=before, after=_snapshot(record))
            return record

    def restore(self, record_id, *, actor: str, session: Optional[Session] = None) -> SystemKnowledge:
        """Restore through a new immutable version rather than mutating history."""
        with self._session(session) as db:
            repo = SystemKnowledgeRepository(db)
            record = repo.get(record_id)
            if record is None:
                raise LookupError("Knowledge record was not found.")
            payload = KnowledgeUpdate(
                category=KnowledgeCategory(record.category), title=record.title, content=record.content,
                content_ar=record.content_ar, content_en=record.content_en, content_tr=record.content_tr,
                structured_data=record.structured_data or {}, visibility=KnowledgeVisibility(record.visibility),
                priority=record.priority, source=record.source,
            )
            return self.create_version(record.id, payload, actor=actor, session=db, action="restored")

    def list_admin(self, *, category: Optional[str] = None, visibility: Optional[str] = None, active_only: bool = False, session: Optional[Session] = None) -> List[SystemKnowledge]:
        with self._session(session) as db:
            return SystemKnowledgeRepository(db).list(category=category, visibility=visibility, active_only=active_only)

    def get_admin(self, record_id, *, session: Optional[Session] = None) -> Optional[SystemKnowledge]:
        with self._session(session) as db:
            return SystemKnowledgeRepository(db).get(record_id)

    def versions(self, key: str, *, session: Optional[Session] = None) -> List[SystemKnowledge]:
        with self._session(session) as db:
            return SystemKnowledgeRepository(db).get_versions(key)

    def audit_history(self, record_id, *, session: Optional[Session] = None) -> List[KnowledgeAuditRecord]:
        with self._session(session) as db:
            audits = SystemKnowledgeRepository(db).audit_history(record_id)
            return [KnowledgeAuditRecord(action=item.action, actor=item.actor, created_at=item.created_at, before=item.before, after=item.after) for item in audits]

    def seed_official(self, records: Sequence[Dict[str, Any]], *, force: bool = False, actor: str = "official_seed", session: Optional[Session] = None) -> SeedReport:
        report = SeedReport()
        with self._session(session) as db:
            repo = SystemKnowledgeRepository(db)
            for raw in records:
                try:
                    payload = KnowledgeWrite(**raw)
                    versions = repo.get_versions(payload.key)
                    if not versions:
                        record = repo.add(_from_payload(payload, version=1, actor=actor))
                        self._audit(repo, record, action="seeded", actor=actor, before=None, after=_snapshot(record))
                        report.inserted += 1
                    elif not force:
                        report.skipped += 1
                    else:
                        current = max(versions, key=lambda item: item.version)
                        update = KnowledgeUpdate(**payload.model_dump(exclude={"key"}))
                        self.create_version(current.id, update, actor=actor, session=db, action="seed_forced")
                        report.updated += 1
                except Exception:
                    logger.exception("Failed to seed official knowledge key=%s", raw.get("key", "unknown"))
                    report.failed += 1
                    raise SeedFailed(report)
        return report


_service: Optional[SystemKnowledgeService] = None


def get_system_knowledge_service() -> SystemKnowledgeService:
    global _service
    if _service is None:
        _service = SystemKnowledgeService()
    return _service
