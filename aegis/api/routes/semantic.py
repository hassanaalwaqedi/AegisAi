"""
AegisAI - Semantic Layer API Routes
Endpoints for Grounding DINO semantic queries

Provides REST API endpoints for:
- Submitting semantic text queries
- Getting semantic analysis results
- Managing active prompts

Phase 5: Semantic Intelligence Layer
"""

import logging
from typing import Optional, List, Literal, Union
from pydantic import BaseModel, Field

from fastapi import APIRouter, HTTPException, Query

from aegis.api.state import get_state
from aegis.intelligence.event_access import load_persisted_event_records, merge_event_records

# Configure module logger
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/semantic", tags=["semantic"])

# Stored-evidence retrieval is request-scoped. The legacy active live prompt
# remains available to existing agents and clients without sharing UI queries.
from aegis.semantic.evidence_search import EvidenceSearchRequest, SearchUnavailable, evidence_search


@router.get("/evidence/status")
def evidence_index_status():
    try:
        return evidence_search.status()
    except SearchUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/evidence/search")
def search_stored_evidence(request: EvidenceSearchRequest):
    try:
        return evidence_search.search(request)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SearchUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/evidence/{event_id}")
def evidence_search_detail(event_id: str):
    try:
        return evidence_search.detail(event_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.warning("Evidence detail unavailable: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Evidence is temporarily unavailable.") from exc


def _queryable_events(state, *, limit: int = 100) -> tuple[list[dict], str, Optional[str]]:
    """Return verified live events plus durable evidence and its availability.

    Runtime observations are valid live data, but they are not a substitute for
    stored evidence.  Carry the durable-store state into the API response so a
    zero-result search is never mistaken for a complete historical search.
    """
    runtime_events = state.get_events(limit=limit)
    if not isinstance(runtime_events, list):
        raise TypeError("Runtime event state returned a non-list payload")
    try:
        durable_events = load_persisted_event_records(limit=limit)
    except Exception as exc:
        logger.warning("Durable semantic evidence unavailable: %s", type(exc).__name__)
        durable_events = []
        return merge_event_records(durable_events, runtime_events), "unavailable", "Durable evidence storage is unavailable; only current runtime events were searched."
    return merge_event_records(durable_events, runtime_events), "available", None


# ═══════════════════════════════════════════════════════════
# REQUEST/RESPONSE MODELS
# ═══════════════════════════════════════════════════════════

class SemanticQueryRequest(BaseModel):
    """Request body for submitting a semantic query."""
    prompt: str = Field(
        ...,
        description="Natural language query (e.g., 'person with bag near entrance')",
        min_length=3,
        max_length=500
    )
    priority: int = Field(
        default=0,
        description="Query priority (higher = more important)",
        ge=0,
        le=100
    )
    ttl_seconds: Optional[int] = Field(
        default=None,
        description="Time-to-live for query in seconds (None = no expiry)"
    )


class SemanticQueryResponse(BaseModel):
    """Response after submitting a semantic query."""
    success: bool
    prompt_id: str
    message: str
    active_prompts: int
    matches: int = 0
    execution_ms: float = 0.0
    evidence_storage: Literal["available", "unavailable"] = "available"
    reason: Optional[str] = None


class SemanticResultItem(BaseModel):
    """Single semantic detection result."""
    track_id: Union[int, str]
    source: Literal["track", "event", "statistics"] = "track"
    base_class: str
    semantic_label: Optional[str]
    semantic_confidence: Optional[float]
    risk_score: float
    matched_phrase: Optional[str]
    behaviors: List[str]
    camera_id: Optional[str] = None
    zone: Optional[str] = None
    confidence: Optional[float] = None
    verification_status: Optional[str] = None
    timestamp: Optional[str] = None
    evidence: List[str] = Field(default_factory=list)


class SemanticResultsResponse(BaseModel):
    """Response with current semantic analysis results."""
    total_tracks: int
    semantic_matches: int
    results: List[SemanticResultItem]
    mode: Literal["live_evidence", "disabled"] = "live_evidence"
    query: Optional[str] = None
    evaluated_tracks: int = 0
    evaluated_events: int = 0
    execution_ms: float = 0.0
    updated_at: Optional[str] = None
    evidence_storage: Literal["available", "unavailable"] = "available"
    reason: Optional[str] = None


class PromptItem(BaseModel):
    """Active prompt details."""
    prompt_id: str
    text: str
    priority: int
    is_expired: bool


class ActivePromptsResponse(BaseModel):
    """Response with list of active prompts."""
    count: int
    prompts: List[PromptItem]


class SemanticStatsResponse(BaseModel):
    """Semantic layer statistics."""
    enabled: bool
    total_triggers: int
    total_matches: int
    cache_stats: dict


# ═══════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════

@router.post("/query", response_model=SemanticQueryResponse)
async def submit_semantic_query(request: SemanticQueryRequest):
    """
    Submit a natural language semantic query.
    
    The query will be used to analyze detected objects using
    Grounding DINO language-guided detection.
    
    Example prompts:
    - "person with a bag near restricted area"
    - "vehicle stopped in no-parking zone"
    - "person running away from entrance"
    """
    state = get_state()
    
    if not hasattr(state, "semantic_query_engine") or state.semantic_query_engine is None:
        raise HTTPException(
            status_code=503,
            detail="Semantic query engine is not available."
        )
    
    try:
        previous_prompt_id = getattr(state, "active_semantic_prompt_id", None)
        if previous_prompt_id:
            state.semantic_prompt_manager.remove_prompt(previous_prompt_id)

        prompt_id = state.semantic_prompt_manager.add_prompt(
            text=request.prompt,
            priority=request.priority,
            ttl=request.ttl_seconds
        )
        
        # Set as active query
        state.active_semantic_query = request.prompt
        state.active_semantic_prompt_id = prompt_id

        events, evidence_storage, reason = _queryable_events(state)
        execution = state.semantic_query_engine.search(
            prompt=request.prompt,
            tracks=state.get_tracks(),
            events=events,
            statistics=state.get_statistics(),
        )
        state.semantic_triggers += 1
        state.semantic_matches += len(execution.results)
        
        active_count = len(state.semantic_prompt_manager.get_active_prompts())
        
        logger.info(f"Semantic query submitted: '{request.prompt}' (ID: {prompt_id})")
        
        return SemanticQueryResponse(
            success=True,
            prompt_id=prompt_id,
            message=f"Query searched live evidence and found {len(execution.results)} match(es).",
            active_prompts=active_count,
            matches=len(execution.results),
            execution_ms=execution.execution_ms,
            evidence_storage=evidence_storage,
            reason=reason,
        )
        
    except Exception as e:
        logger.error(f"Failed to submit semantic query: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/query/{prompt_id}")
async def remove_semantic_query(prompt_id: str):
    """Remove a semantic query by ID."""
    state = get_state()
    
    if not hasattr(state, 'semantic_prompt_manager') or state.semantic_prompt_manager is None:
        raise HTTPException(status_code=503, detail="Semantic layer not available")
    
    success = state.semantic_prompt_manager.remove_prompt(prompt_id)
    
    if success:
        if getattr(state, "active_semantic_prompt_id", None) == prompt_id:
            state.active_semantic_prompt_id = None
            state.active_semantic_query = None
        return {"success": True, "message": f"Prompt {prompt_id} removed"}
    else:
        raise HTTPException(status_code=404, detail=f"Prompt {prompt_id} not found")


@router.get("/prompts", response_model=ActivePromptsResponse)
async def get_active_prompts():
    """Get list of active semantic prompts."""
    state = get_state()
    
    if not hasattr(state, 'semantic_prompt_manager') or state.semantic_prompt_manager is None:
        return ActivePromptsResponse(count=0, prompts=[])
    
    prompts = state.semantic_prompt_manager.get_active_prompts()
    
    prompt_items = [
        PromptItem(
            prompt_id=p.prompt_id,
            text=p.text,
            priority=p.priority,
            is_expired=p.is_expired()
        )
        for p in prompts
    ]
    
    return ActivePromptsResponse(count=len(prompt_items), prompts=prompt_items)


@router.get("/results", response_model=SemanticResultsResponse)
async def get_semantic_results(limit: int = Query(default=50, le=100)):
    """
    Get current semantic analysis results.
    
    Returns unified object intelligence combining:
    - YOLO base class detection
    - DeepSORT tracking ID
    - Grounding DINO semantic labels
    - Risk scores
    """
    state = get_state()
    
    engine = getattr(state, "semantic_query_engine", None)
    prompt = getattr(state, "active_semantic_query", None)
    if engine is None:
        return SemanticResultsResponse(
            total_tracks=0,
            semantic_matches=0,
            results=[],
            mode="disabled",
        )

    if not prompt:
        return SemanticResultsResponse(total_tracks=0, semantic_matches=0, results=[])

    events, evidence_storage, reason = _queryable_events(state)
    execution = engine.search(
        prompt=prompt,
        tracks=state.get_tracks(),
        events=events,
        statistics=state.get_statistics(),
        limit=limit,
    )
    results = [SemanticResultItem(**result) for result in execution.results]

    return SemanticResultsResponse(
        total_tracks=len(results),
        semantic_matches=len(results),
        results=results,
        query=execution.prompt,
        evaluated_tracks=execution.evaluated_tracks,
        evaluated_events=execution.evaluated_events,
        execution_ms=execution.execution_ms,
        updated_at=execution.updated_at,
        evidence_storage=evidence_storage,
        reason=reason,
    )


@router.get("/stats", response_model=SemanticStatsResponse)
async def get_semantic_stats():
    """Get semantic layer statistics."""
    state = get_state()
    
    enabled = hasattr(state, "semantic_query_engine") and state.semantic_query_engine is not None
    
    if not enabled:
        return SemanticStatsResponse(
            enabled=False,
            total_triggers=0,
            total_matches=0,
            cache_stats={}
        )
    
    cache_stats = state.semantic_prompt_manager.get_cache_stats() if getattr(state, "semantic_prompt_manager", None) else {}
    
    return SemanticStatsResponse(
        enabled=True,
        total_triggers=getattr(state, 'semantic_triggers', 0),
        total_matches=getattr(state, 'semantic_matches', 0),
        cache_stats=cache_stats
    )
