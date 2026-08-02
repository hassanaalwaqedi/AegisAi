"""Authenticated, versioned operational context for the Intelligence page."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from aegis.api.security import verify_api_key
from aegis.intelligence.context_schemas import IntelligenceContext
from aegis.intelligence.context_service import get_intelligence_context_service


router = APIRouter(prefix="/api/intelligence", tags=["intelligence"])


@router.get("/context", response_model=IntelligenceContext, response_model_by_alias=True)
async def get_intelligence_context(
    _: bool = Depends(verify_api_key),
) -> IntelligenceContext:
    """Return one source-fresh snapshot; unavailable data remains unavailable."""

    return get_intelligence_context_service().build()
