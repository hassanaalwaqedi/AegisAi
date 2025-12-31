"""
AegisAI - Mode API Routes

API endpoints for system mode management.

Endpoints:
- GET /mode - Get current mode
- POST /mode - Switch mode
- GET /mode/features - Get available features

Copyright 2024 AegisAI Project
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Dict, Any

from aegis.core.mode_manager import (
    get_mode_manager,
    SystemMode,
    get_current_mode,
    set_mode
)
from aegis.core.feature_router import get_feature_router, load_mode_modules
from aegis.api.security import verify_api_key

router = APIRouter(prefix="/mode", tags=["mode"])


class ModeResponse(BaseModel):
    """Current mode response."""
    mode: str
    display_name: str
    description: str


class ModeChangeRequest(BaseModel):
    """Request to change system mode."""
    mode: str  # "city" or "restaurant"


class FeaturesResponse(BaseModel):
    """Available features for current mode."""
    mode: str
    features: Dict[str, bool]
    available_routes: List[str]


@router.get("", response_model=ModeResponse)
async def get_mode():
    """
    Get current system operating mode.
    
    Returns:
        Current mode information
    """
    mode = get_current_mode()
    
    descriptions = {
        SystemMode.CITY: "Smart City Risk Monitoring - crowd analysis, risk scoring, alerts",
        SystemMode.RESTAURANT: "Employee & Operational Intelligence - staff tracking, queues, KPIs"
    }
    
    display_names = {
        SystemMode.CITY: "Smart City",
        SystemMode.RESTAURANT: "Restaurant & Retail"
    }
    
    return ModeResponse(
        mode=mode.value,
        display_name=display_names[mode],
        description=descriptions[mode]
    )


@router.post("", response_model=ModeResponse, dependencies=[Depends(verify_api_key)])
async def change_mode(request: ModeChangeRequest):
    """
    Change system operating mode.
    
    Args:
        request: New mode to switch to
        
    Returns:
        Updated mode information
    """
    try:
        new_mode = SystemMode.from_string(request.mode)
        set_mode(new_mode)
        
        # Load modules for new mode
        load_mode_modules(new_mode)
        
        return await get_mode()
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/features", response_model=FeaturesResponse)
async def get_features():
    """
    Get available features for current mode.
    
    Returns:
        Feature flags and available routes
    """
    manager = get_mode_manager()
    mode = manager.mode
    
    return FeaturesResponse(
        mode=mode.value,
        features={
            name: value
            for name, value in manager.features.__dict__.items()
        },
        available_routes=manager.get_api_routes()
    )


@router.get("/modules")
async def get_modules():
    """
    Get loaded modules for current mode.
    
    Returns:
        List of module names and their status
    """
    router = get_feature_router()
    
    return {
        "mode": get_current_mode().value,
        "available_modules": router.get_available_modules(),
        "loaded_modules": list(router.get_loaded_modules().keys())
    }


@router.get("/privacy")
async def get_privacy_settings():
    """
    Get current privacy configuration.
    
    Returns:
        Privacy settings
    """
    manager = get_mode_manager()
    
    return {
        "mode": manager.mode.value,
        "privacy": {
            name: value
            for name, value in manager.privacy.__dict__.items()
        }
    }
