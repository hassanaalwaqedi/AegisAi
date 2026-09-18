"""
AegisAI - Smart City Risk Intelligence System
API Security Module

Provides API key authentication and rate limiting middleware.

Sprint 1: Security & Testing Foundation
"""

import os
import logging
import secrets
import base64
import hashlib
import hmac
import time
import threading
from collections import defaultdict, deque
from functools import wraps
from typing import Callable, Optional, Tuple

from fastapi import Request, HTTPException, WebSocket, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Configure module logger
logger = logging.getLogger(__name__)


# Browsers cannot attach arbitrary HTTP headers during a WebSocket upgrade.
# The dashboard therefore exchanges its server-side API credential for this
# short-lived, signed token and sends it as a WebSocket subprotocol.  Keeping
# the credential itself out of the browser bundle is essential.
WEBSOCKET_AUTH_PROTOCOL = "aegis-api-v1"
WEBSOCKET_TOKEN_TTL_SECONDS = 60
DASHBOARD_PROXY_HEADER = "X-Aegis-Internal-Proxy"
_DASHBOARD_PROXY_AUDIENCE = b"aegis-dashboard-proxy-v1"


def get_api_key() -> Optional[str]:
    """
    Get API key from environment.
    
    Returns:
        API key string or None if not configured
    """
    value = os.getenv("AEGIS_API_KEY", "").strip()
    return value or None


def dashboard_proxy_signature() -> Optional[str]:
    """Return the server-to-server dashboard proof derived from the API key.

    This is not an additional browser credential.  It is only used between
    the Next.js server-side proxy and the backend to distinguish its pooled
    loopback traffic from direct API clients for rate-limit accounting.
    """
    api_key = get_api_key()
    if not api_key:
        return None
    return hmac.new(api_key.encode("utf-8"), _DASHBOARD_PROXY_AUDIENCE, hashlib.sha256).hexdigest()


def is_trusted_dashboard_proxy(request: Request) -> bool:
    """Validate a dashboard proxy marker without trusting an arbitrary header."""
    provided = request.headers.get(DASHBOARD_PROXY_HEADER)
    expected = dashboard_proxy_signature()
    return bool(provided and expected and secrets.compare_digest(provided, expected))


def get_admin_api_key() -> Optional[str]:
    """Return the distinct server-side key required for administrative writes."""
    return os.getenv("AEGIS_ADMIN_API_KEY")


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


def api_authentication_configured() -> bool:
    """Return whether protected API access has a configured credential."""
    return bool(get_api_key())


def api_authentication_readiness() -> Tuple[bool, str]:
    """Expose configuration health without ever revealing the credential."""
    if api_authentication_configured():
        return True, "API-key authentication is configured."
    return False, "AEGIS_API_KEY is not configured; protected API and WebSocket access are disabled."


def _record_auth_failure(action: str, *, path: str, reason: str) -> None:
    """Best-effort audit for rejected credentials without retaining a key or IP."""
    try:
        from aegis.audit import record_audit

        record_audit(
            action,
            resource_type="authentication",
            resource_id=path[:160],
            details={"reason": reason},
        )
    except Exception:
        # Authentication must keep its original fail-closed semantics even
        # when the database/audit subsystem is not available.
        return


# Create rate limiter instance
limiter = Limiter(key_func=get_remote_address)


class GlobalRateLimitMiddleware(BaseHTTPMiddleware):
    """Enforce the configured API-wide per-client limit before route work.

    SlowAPI remains registered for endpoint-specific limits.  This lightweight
    guard closes the historic gap where no route had a SlowAPI decorator, so
    the configured limit was never actually enforced.  State is intentionally
    process-local; multi-instance deployments should use the existing Redis
    integration or a shared edge rate limiter.
    """

    def __init__(self, app) -> None:
        super().__init__(app)
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    @staticmethod
    def _configuration() -> tuple[int, float]:
        try:
            limit = max(1, int(os.getenv("AEGIS_RATE_LIMIT", "60")))
        except (TypeError, ValueError):
            limit = 60
        try:
            window = max(1.0, float(os.getenv("AEGIS_RATE_LIMIT_WINDOW", "60")))
        except (TypeError, ValueError):
            window = 60.0
        return limit, window

    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)

        # Browser requests are pooled through Next.js and reach the backend
        # from one loopback address. Counting every camera poll from every UI
        # session in a single IP bucket causes false 429s and makes cameras
        # appear to connect/disconnect. The marker is an HMAC that only a
        # server which already holds the API key can generate; it is never
        # exposed to browser JavaScript.
        if is_trusted_dashboard_proxy(request):
            return await call_next(request)

        limit, window = self._configuration()
        client = request.client.host if request.client else "unknown"
        now = time.monotonic()
        with self._lock:
            bucket = self._requests[client]
            while bucket and now - bucket[0] >= window:
                bucket.popleft()
            if len(bucket) >= limit:
                retry_after = max(1, int(window - (now - bucket[0])))
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"error": "Rate limit exceeded", "retry_after": retry_after},
                    headers={"Retry-After": str(retry_after)},
                )
            bucket.append(now)

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        return response


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
    
    # Never run protected routes in an open mode.  A missing server-side
    # credential is a deployment error, not a development convenience.
    if not expected_key:
        logger.error("Protected API request rejected because AEGIS_API_KEY is not configured")
        _record_auth_failure(
            "auth.api_key_rejected",
            path=request.url.path,
            reason="api_key_not_configured",
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API authentication is not configured.",
        )
    
    # Get key from header
    provided_key = request.headers.get("X-API-Key")
    
    if not provided_key:
        logger.warning(f"Missing API key from {get_remote_address(request)}")
        _record_auth_failure("auth.api_key_rejected", path=request.url.path, reason="missing_api_key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Provide X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"}
        )
    
    if not secrets.compare_digest(provided_key, expected_key):
        logger.warning(f"Invalid API key from {get_remote_address(request)}")
        _record_auth_failure("auth.api_key_rejected", path=request.url.path, reason="invalid_api_key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
            headers={"WWW-Authenticate": "ApiKey"}
        )
    
    return True


def _urlsafe_b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _urlsafe_b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def create_websocket_access_token(ttl_seconds: int = WEBSOCKET_TOKEN_TTL_SECONDS) -> Tuple[str, int]:
    """Issue a short-lived WebSocket token signed with the server API key.

    This is intentionally not a replacement for user authentication.  It only
    proves that the caller reached an already API-key-protected server route,
    without leaking ``AEGIS_API_KEY`` into a browser URL or bundle.
    """
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError("AEGIS_API_KEY is not configured")

    expires_at = int(time.time()) + max(1, min(int(ttl_seconds), 300))
    payload = f"{expires_at}:{secrets.token_urlsafe(18)}".encode("utf-8")
    signature = hmac.new(api_key.encode("utf-8"), payload, hashlib.sha256).digest()
    return f"{_urlsafe_b64encode(payload)}.{_urlsafe_b64encode(signature)}", expires_at


def verify_websocket_access_token(token: Optional[str]) -> bool:
    """Verify a dashboard WebSocket token without accepting expired tokens."""
    api_key = get_api_key()
    if not api_key or not token:
        return False
    try:
        encoded_payload, encoded_signature = token.split(".", 1)
        payload = _urlsafe_b64decode(encoded_payload)
        received_signature = _urlsafe_b64decode(encoded_signature)
        expected_signature = hmac.new(api_key.encode("utf-8"), payload, hashlib.sha256).digest()
        expires_at_raw, _nonce = payload.decode("utf-8").split(":", 1)
        expires_at = int(expires_at_raw)
    except (ValueError, UnicodeDecodeError, TypeError):
        return False
    return expires_at >= int(time.time()) and secrets.compare_digest(received_signature, expected_signature)


def websocket_subprotocol_token(websocket: WebSocket) -> Optional[str]:
    """Read the signed token from ``Sec-WebSocket-Protocol`` safely."""
    raw_protocols = websocket.headers.get("sec-websocket-protocol", "")
    protocols = [item.strip() for item in raw_protocols.split(",") if item.strip()]
    if WEBSOCKET_AUTH_PROTOCOL not in protocols:
        return None
    protocol_index = protocols.index(WEBSOCKET_AUTH_PROTOCOL)
    return protocols[protocol_index + 1] if protocol_index + 1 < len(protocols) else None


async def verify_websocket_auth(websocket: WebSocket) -> bool:
    """Fail closed before accepting a sensitive WebSocket connection.

    Non-browser service clients may authenticate with ``X-API-Key``. Browser
    clients must use a short-lived signed token as the second subprotocol.
    """
    expected_key = get_api_key()
    if not expected_key:
        logger.error("WebSocket rejected because AEGIS_API_KEY is not configured")
        _record_auth_failure(
            "auth.websocket_rejected",
            path=websocket.url.path,
            reason="api_key_not_configured",
        )
        await websocket.close(code=1013, reason="API authentication is not configured")
        return False

    provided_key = websocket.headers.get("X-API-Key")
    if provided_key and secrets.compare_digest(provided_key, expected_key):
        return True

    if verify_websocket_access_token(websocket_subprotocol_token(websocket)):
        return True

    logger.warning("Unauthenticated WebSocket connection rejected")
    _record_auth_failure(
        "auth.websocket_rejected",
        path=websocket.url.path,
        reason="invalid_or_missing_credential",
    )
    await websocket.close(code=4401, reason="WebSocket authentication required")
    return False


async def verify_admin_api_key(request: Request) -> str:
    """Require normal API access plus an explicitly configured admin credential.

    The project does not yet have a user/role identity provider.  Failing closed
    here prevents a normal operator API key from becoming a write credential.
    """
    await verify_api_key(request)
    expected_key = get_admin_api_key()
    if not expected_key:
        logger.error("Administrative system-knowledge endpoint requested without AEGIS_ADMIN_API_KEY configured")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Administrative knowledge access is not configured.",
        )
    provided_key = request.headers.get("X-Aegis-Admin-Key")
    if not provided_key or not secrets.compare_digest(provided_key, expected_key):
        logger.warning("Invalid administrative credential from %s", get_remote_address(request))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator permission is required.",
        )
    # There is no authenticated user identity in the current API-key scheme;
    # audit the approved administrative principal rather than a forged header.
    return "api-key-admin"


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
