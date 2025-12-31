"""
AegisAI - Natural Language Query API

API endpoint for natural language questions using Gemini AI.
Allows users to ask questions about the surveillance data.

Copyright 2024 AegisAI Project
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, Dict, Any
import logging

from aegis.api.security import verify_api_key

router = APIRouter(prefix="/nlq", tags=["ai"])
logger = logging.getLogger(__name__)


class NLQRequest(BaseModel):
    """Natural language query request."""
    query: str
    context: Optional[str] = None


class NLQResponse(BaseModel):
    """Natural language query response."""
    answer: str
    model: str
    tokens_used: int
    latency_ms: float


@router.post("", response_model=NLQResponse, dependencies=[Depends(verify_api_key)])
async def natural_language_query(request: NLQRequest):
    """
    Process a natural language query using Gemini AI.
    
    Args:
        request: Query and optional context
        
    Returns:
        AI-generated answer
    """
    try:
        from aegis.ai.gemini_client import get_gemini_client
        
        client = get_gemini_client()
        
        system_prompt = """You are AegisAI, an intelligent surveillance analytics assistant.
        You help security operators understand video analytics data, risk assessments, 
        crowd patterns, and operational insights. Be concise and actionable in your responses.
        If asked about specific data you don't have, explain what would be needed to answer."""
        
        # Build prompt with context if provided
        prompt = request.query
        if request.context:
            prompt = f"Context: {request.context}\n\nQuestion: {request.query}"
        
        response = client.generate(
            prompt=prompt,
            system_prompt=system_prompt
        )
        
        return NLQResponse(
            answer=response.text,
            model=response.model,
            tokens_used=response.total_tokens,
            latency_ms=response.latency_ms
        )
        
    except ImportError:
        raise HTTPException(
            status_code=503, 
            detail="AI module not available. Check GEMINI_API_KEY."
        )
    except Exception as e:
        logger.error(f"NLQ error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/json", dependencies=[Depends(verify_api_key)])
async def structured_query(request: NLQRequest):
    """
    Process a query and return structured JSON response.
    
    Args:
        request: Query requesting structured data
        
    Returns:
        Parsed JSON response from AI
    """
    try:
        from aegis.ai.gemini_client import get_gemini_client
        
        client = get_gemini_client()
        
        result = client.generate_json(
            prompt=request.query,
            system_prompt="Return structured JSON data as requested."
        )
        
        return {"data": result}
        
    except Exception as e:
        logger.error(f"JSON query error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def gemini_health():
    """Check if Gemini AI is configured and working."""
    try:
        from aegis.ai.gemini_client import get_gemini_client
        
        client = get_gemini_client()
        response = client.generate("Say 'OK' and nothing else.")
        
        return {
            "status": "healthy",
            "model": client.config.model,
            "test_response": response.text,
            "latency_ms": response.latency_ms
        }
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }
