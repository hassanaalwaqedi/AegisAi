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
from typing import Optional, List
from pydantic import BaseModel, Field

from fastapi import APIRouter, HTTPException, Query

from aegis.api.state import get_state

# Configure module logger
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/semantic", tags=["semantic"])


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


class SemanticResultItem(BaseModel):
    """Single semantic detection result."""
    track_id: int
    base_class: str
    semantic_label: Optional[str]
    semantic_confidence: Optional[float]
    risk_score: float
    matched_phrase: Optional[str]
    behaviors: List[str]


class SemanticResultsResponse(BaseModel):
    """Response with current semantic analysis results."""
    total_tracks: int
    semantic_matches: int
    results: List[SemanticResultItem]


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
    
    # Check if semantic layer is available
    if not hasattr(state, 'semantic_prompt_manager') or state.semantic_prompt_manager is None:
        raise HTTPException(
            status_code=503,
            detail="Semantic layer not available. Enable with --enable-semantic"
        )
    
    try:
        prompt_id = state.semantic_prompt_manager.add_prompt(
            text=request.prompt,
            priority=request.priority,
            ttl=request.ttl_seconds
        )
        
        # Set as active query
        state.active_semantic_query = request.prompt
        
        active_count = len(state.semantic_prompt_manager.get_active_prompts())
        
        logger.info(f"Semantic query submitted: '{request.prompt}' (ID: {prompt_id})")
        
        return SemanticQueryResponse(
            success=True,
            prompt_id=prompt_id,
            message=f"Query submitted. Will analyze tracks matching: '{request.prompt}'",
            active_prompts=active_count
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
    
    if not hasattr(state, 'unified_intelligence') or state.unified_intelligence is None:
        return SemanticResultsResponse(
            total_tracks=0,
            semantic_matches=0,
            results=[]
        )
    
    intel = state.unified_intelligence[:limit]
    
    results = [
        SemanticResultItem(
            track_id=obj.track_id,
            base_class=obj.base_class,
            semantic_label=obj.semantic_label,
            semantic_confidence=obj.semantic_confidence,
            risk_score=obj.risk_score,
            matched_phrase=obj.matched_phrase,
            behaviors=obj.behaviors
        )
        for obj in intel
    ]
    
    semantic_count = sum(1 for r in results if r.semantic_label is not None)
    
    return SemanticResultsResponse(
        total_tracks=len(results),
        semantic_matches=semantic_count,
        results=results
    )


@router.get("/stats", response_model=SemanticStatsResponse)
async def get_semantic_stats():
    """Get semantic layer statistics."""
    state = get_state()
    
    enabled = hasattr(state, 'semantic_prompt_manager') and state.semantic_prompt_manager is not None
    
    if not enabled:
        return SemanticStatsResponse(
            enabled=False,
            total_triggers=0,
            total_matches=0,
            cache_stats={}
        )
    
    cache_stats = state.semantic_prompt_manager.get_cache_stats() if enabled else {}
    
    return SemanticStatsResponse(
        enabled=True,
        total_triggers=getattr(state, 'semantic_triggers', 0),
        total_matches=getattr(state, 'semantic_matches', 0),
        cache_stats=cache_stats
    )
