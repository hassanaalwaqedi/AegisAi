"""
AegisAI - Smart City Risk Intelligence System
API Security Module

Provides API key authentication and rate limiting middleware.

Sprint 1: Security & Testing Foundation
"""

import os
import logging
from functools import wraps
from typing import Callable, Optional

from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Configure module logger
logger = logging.getLogger(__name__)


def get_api_key() -> Optional[str]:
    """
    Get API key from environment.
    
    Returns:
        API key string or None if not configured
    """
    return os.getenv("AEGIS_API_KEY")


def get_allowed_origins() -> list:
    """
    Get allowed CORS origins from environment.
    
    Returns:
        List of allowed origin URLs
    """
    origins = os.getenv("AEGIS_ALLOWED_ORIGINS", "")
    if not origins:
        # Default to localhost only if not specified
        return ["http://localhost:8080", "http://127.0.0.1:8080"]
    return [o.strip() for o in origins.split(",") if o.strip()]


def get_rate_limit() -> str:
    """
    Get rate limit configuration.
    
    Returns:
        Rate limit string (e.g., "60/minute")
    """
    limit = os.getenv("AEGIS_RATE_LIMIT", "60")
    window = os.getenv("AEGIS_RATE_LIMIT_WINDOW", "60")
    
    # Convert window seconds to period
    if window == "60":
        return f"{limit}/minute"
    elif window == "3600":
        return f"{limit}/hour"
    else:
        return f"{limit}/minute"


def is_debug_mode() -> bool:
    """Check if debug mode is enabled."""
    return os.getenv("AEGIS_DEBUG", "false").lower() == "true"


# Create rate limiter instance
limiter = Limiter(key_func=get_remote_address)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """Handle rate limit exceeded errors."""
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "error": "Rate limit exceeded",
            "detail": str(exc.detail),
            "retry_after": getattr(exc, "retry_after", 60)
        }
    )


async def verify_api_key(request: Request) -> bool:
    """
    Verify API key from request header.
    
    Args:
        request: FastAPI request object
        
    Returns:
        True if valid, raises HTTPException otherwise
    """
    expected_key = get_api_key()
    
    # If no API key configured, allow all requests (dev mode)
    if not expected_key:
        if is_debug_mode():
            logger.warning("No API key configured - running in open mode")
        return True
    
    # Get key from header
    provided_key = request.headers.get("X-API-Key")
    
    if not provided_key:
        logger.warning(f"Missing API key from {get_remote_address(request)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Provide X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"}
        )
    
    if provided_key != expected_key:
        logger.warning(f"Invalid API key from {get_remote_address(request)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
            headers={"WWW-Authenticate": "ApiKey"}
        )
    
    return True


def require_api_key(func: Callable) -> Callable:
    """
    Decorator to require API key for an endpoint.
    
    Usage:
        @router.get("/protected")
        @require_api_key
        async def protected_endpoint():
            ...
    """
    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        await verify_api_key(request)
        return await func(request, *args, **kwargs)
    return wrapper
