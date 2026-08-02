"""Validation and public response schemas for system knowledge."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class KnowledgeVisibility(str, Enum):
    PUBLIC = "public"
    PRIVATE = "private"


class KnowledgeCategory(str, Enum):
    CREATOR_PROFILE = "creator_profile"
    CREATOR_CONTRIBUTIONS = "creator_contributions"
    PROJECT_PROFILE = "project_profile"
    PROJECT_PURPOSE = "project_purpose"
    PROJECT_ARCHITECTURE = "project_architecture"
    PROJECT_CAPABILITIES = "project_capabilities"
    PROJECT_TECHNOLOGY = "project_technology"
    PROJECT_SECURITY = "project_security"
    PROJECT_LIMITATIONS = "project_limitations"


class KnowledgeWrite(BaseModel):
    """Fields an administrator may supply; identity/audit fields are protected."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    key: str = Field(min_length=3, max_length=160, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    category: KnowledgeCategory
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=20000)
    content_ar: Optional[str] = Field(default=None, max_length=20000)
    content_en: Optional[str] = Field(default=None, max_length=20000)
    content_tr: Optional[str] = Field(default=None, max_length=20000)
    structured_data: Dict[str, Any] = Field(default_factory=dict)
    visibility: KnowledgeVisibility = KnowledgeVisibility.PUBLIC
    priority: int = Field(default=100, ge=0, le=1000)
    source: str = Field(min_length=3, max_length=300)

    @field_validator("structured_data")
    @classmethod
    def require_json_object(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("structured_data must be a JSON object")
        return value


class KnowledgeUpdate(BaseModel):
    """Partial version payload. A new immutable version is created on change."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    category: Optional[KnowledgeCategory] = None
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    content: Optional[str] = Field(default=None, min_length=1, max_length=20000)
    content_ar: Optional[str] = Field(default=None, max_length=20000)
    content_en: Optional[str] = Field(default=None, max_length=20000)
    content_tr: Optional[str] = Field(default=None, max_length=20000)
    structured_data: Optional[Dict[str, Any]] = None
    visibility: Optional[KnowledgeVisibility] = None
    priority: Optional[int] = Field(default=None, ge=0, le=1000)
    source: Optional[str] = Field(default=None, min_length=3, max_length=300)


class KnowledgeActivation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_active: bool


class KnowledgePublicRecord(BaseModel):
    """Safe public projection: no IDs, source paths, authors, or audit data."""

    key: str
    category: KnowledgeCategory
    title: str
    content: str
    priority: int
    version: int


class KnowledgeAdminRecord(BaseModel):
    id: UUID
    key: str
    category: KnowledgeCategory
    title: str
    content: str
    content_ar: Optional[str] = None
    content_en: Optional[str] = None
    content_tr: Optional[str] = None
    structured_data: Dict[str, Any]
    visibility: KnowledgeVisibility
    priority: int
    source: str
    is_active: bool
    version: int
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class KnowledgeAuditRecord(BaseModel):
    action: str
    actor: str
    created_at: datetime
    before: Optional[Dict[str, Any]] = None
    after: Optional[Dict[str, Any]] = None


class KnowledgeSearchResponse(BaseModel):
    availability: Literal["available", "unavailable"]
    locale: Literal["ar", "en", "tr"]
    records: List[KnowledgePublicRecord] = Field(default_factory=list)
    reason: Optional[str] = None
