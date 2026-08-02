"""Authenticated public retrieval and fail-closed administrator APIs for system knowledge."""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from aegis.api.security import verify_admin_api_key, verify_api_key
from aegis.knowledge.schemas import (
    KnowledgeActivation,
    KnowledgeAdminRecord,
    KnowledgeAuditRecord,
    KnowledgeSearchResponse,
    KnowledgeUpdate,
    KnowledgeWrite,
)
from aegis.knowledge.service import get_system_knowledge_service


router = APIRouter(prefix="/api/system-knowledge", tags=["system knowledge"])
admin_router = APIRouter(prefix="/api/admin/system-knowledge", tags=["system knowledge administration"])


@router.get("/search", response_model=KnowledgeSearchResponse)
async def search_system_knowledge(
    q: str = Query(min_length=1, max_length=500),
    locale: Optional[str] = Query(default=None, pattern="^(ar|en|tr)$"),
    limit: int = Query(default=3, ge=1, le=10),
    _: bool = Depends(verify_api_key),
) -> KnowledgeSearchResponse:
    """Return only active public records with safe, localised projections."""
    result = get_system_knowledge_service().public_search(q, locale=locale, limit=limit)
    return KnowledgeSearchResponse(
        availability=result.availability,
        locale=result.locale,
        records=[get_system_knowledge_service().public_projection(record) for record in result.records],
        reason=result.reason,
    )


@admin_router.get("", response_model=List[KnowledgeAdminRecord])
async def list_system_knowledge(
    category: Optional[str] = Query(default=None),
    visibility: Optional[str] = Query(default=None, pattern="^(public|private)$"),
    active_only: bool = Query(default=False),
    _: str = Depends(verify_admin_api_key),
) -> List[KnowledgeAdminRecord]:
    service = get_system_knowledge_service()
    return [service.admin_projection(record) for record in service.list_admin(category=category, visibility=visibility, active_only=active_only)]


@admin_router.post("", response_model=KnowledgeAdminRecord, status_code=201)
async def create_system_knowledge(payload: KnowledgeWrite, actor: str = Depends(verify_admin_api_key)) -> KnowledgeAdminRecord:
    service = get_system_knowledge_service()
    try:
        return service.admin_projection(service.create(payload, actor=actor))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@admin_router.get("/{record_id}", response_model=KnowledgeAdminRecord)
async def get_system_knowledge(record_id: UUID, _: str = Depends(verify_admin_api_key)) -> KnowledgeAdminRecord:
    service = get_system_knowledge_service()
    record = service.get_admin(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Knowledge record was not found.")
    return service.admin_projection(record)


@admin_router.patch("/{record_id}", response_model=KnowledgeAdminRecord)
async def update_system_knowledge(record_id: UUID, payload: KnowledgeUpdate, actor: str = Depends(verify_admin_api_key)) -> KnowledgeAdminRecord:
    service = get_system_knowledge_service()
    try:
        return service.admin_projection(service.create_version(record_id, payload, actor=actor))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@admin_router.post("/{record_id}/versions", response_model=KnowledgeAdminRecord, status_code=201)
async def create_system_knowledge_version(record_id: UUID, payload: KnowledgeUpdate, actor: str = Depends(verify_admin_api_key)) -> KnowledgeAdminRecord:
    return await update_system_knowledge(record_id, payload, actor)


@admin_router.get("/{record_id}/versions", response_model=List[KnowledgeAdminRecord])
async def get_system_knowledge_versions(record_id: UUID, _: str = Depends(verify_admin_api_key)) -> List[KnowledgeAdminRecord]:
    service = get_system_knowledge_service()
    record = service.get_admin(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Knowledge record was not found.")
    return [service.admin_projection(item) for item in service.versions(record.key)]


@admin_router.post("/{record_id}/restore", response_model=KnowledgeAdminRecord, status_code=201)
async def restore_system_knowledge(record_id: UUID, actor: str = Depends(verify_admin_api_key)) -> KnowledgeAdminRecord:
    service = get_system_knowledge_service()
    try:
        return service.admin_projection(service.restore(record_id, actor=actor))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@admin_router.patch("/{record_id}/activation", response_model=KnowledgeAdminRecord)
async def set_system_knowledge_activation(record_id: UUID, payload: KnowledgeActivation, actor: str = Depends(verify_admin_api_key)) -> KnowledgeAdminRecord:
    service = get_system_knowledge_service()
    try:
        return service.admin_projection(service.set_active(record_id, is_active=payload.is_active, actor=actor))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@admin_router.get("/{record_id}/audit", response_model=List[KnowledgeAuditRecord])
async def get_system_knowledge_audit(record_id: UUID, _: str = Depends(verify_admin_api_key)) -> List[KnowledgeAuditRecord]:
    service = get_system_knowledge_service()
    if service.get_admin(record_id) is None:
        raise HTTPException(status_code=404, detail="Knowledge record was not found.")
    return service.audit_history(record_id)
