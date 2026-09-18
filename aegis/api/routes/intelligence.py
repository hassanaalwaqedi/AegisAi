"""
Intelligence API Endpoints

Production endpoints for NLQ, personalization, and analytics.
Works without database if unavailable.
"""

from fastapi import APIRouter, Body, HTTPException, status
from pydantic import BaseModel
from typing import Optional
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/intelligence", tags=["Intelligence"])


def _unavailable(feature: str) -> None:
    """Never substitute fabricated intelligence when a verified source is absent."""
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "code": "verified_data_unavailable",
            "message": f"{feature} is disabled because it has no verified persisted data source.",
        },
    )


# Request/Response Models
class NLQRequest(BaseModel):
    query: str


class NLQResponse(BaseModel):
    query: str
    query_type: str
    answer: str
    confidence: float


class PersonalizationRequest(BaseModel):
    session_id: str
    user_intent: str = "exploring"
    scroll_depth: float = 0.0
    event_count: int = 0
    rage_clicks: int = 0
    hesitation_count: int = 0
    is_returning: bool = False
    device_type: str = "desktop"


class AnalyticsEventRequest(BaseModel):
    session_id: str
    event_type: str
    properties: dict = {}


@router.post("/nlq", response_model=NLQResponse)
async def process_nlq(request: NLQRequest):
    """Legacy NLQ is disabled until it has verified data sources."""
    del request
    _unavailable("Legacy intelligence NLQ")


@router.get("/nlq/history")
async def get_nlq_history(limit: int = 10):
    """Get recent NLQ query history."""
    del limit
    _unavailable("Legacy intelligence NLQ history")


@router.post("/personalization")
async def get_personalization(request: PersonalizationRequest):
    """Get personalized UI recommendations based on user behavior."""
    try:
        from aegis.intelligence.personalization import PersonalizationEngine, PersonalizationContext
        
        engine = PersonalizationEngine()
        context = PersonalizationContext(
            session_id=request.session_id,
            user_intent=request.user_intent,
            scroll_depth=request.scroll_depth,
            event_count=request.event_count,
            rage_clicks=request.rage_clicks,
            hesitation_count=request.hesitation_count,
            is_returning=request.is_returning,
            device_type=request.device_type,
        )
        result = engine.get_personalization(context)
        return result.to_dict()
    except Exception as e:
        logger.error(f"Personalization error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Personalization is unavailable because its verified data source failed.",
        ) from e


@router.post("/analytics/event")
async def track_analytics_event(request: AnalyticsEventRequest):
    """Track a behavioral analytics event."""
    del request
    _unavailable("Legacy behavioral analytics")


@router.get("/analytics/session/{session_id}")
async def get_session_analytics(session_id: str):
    """Get analytics for a specific session."""
    del session_id
    _unavailable("Legacy behavioral analytics")


@router.post("/privacy/sanitize")
async def sanitize_data(data: dict = Body(...)):
    """Sanitize data by removing/masking PII."""
    try:
        from aegis.intelligence.privacy import PIIIsolator, AccessContext, AccessLevel
        
        isolator = PIIIsolator()
        context = AccessContext(
            user_id="api_user",
            access_level=AccessLevel.AUTHENTICATED,
            purpose="api_sanitization",
        )
        sanitized = isolator.sanitize_dict(data, context)
        return {"sanitized": sanitized}
    except Exception as e:
        logger.error(f"Sanitize error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PII sanitization is temporarily unavailable.",
        ) from e


@router.get("/privacy/audit")
async def get_privacy_audit(limit: int = 50):
    """Get PII access audit log."""
    del limit
    _unavailable("Privacy audit history")
