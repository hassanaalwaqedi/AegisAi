"""Authenticated Gemini Live session surfaces for the Intelligence Center."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, WebSocket

from aegis.api.security import verify_api_key
from aegis.intelligence.live_schemas import LiveCapabilities, LiveSessionCreate, LiveSessionResponse
from aegis.intelligence.live_service import (
    LIVE_WS_PROTOCOL,
    LiveCapabilityError,
    get_live_session_manager,
    run_live_gateway,
)

router = APIRouter(prefix="/api/intelligence/live", tags=["intelligence-live"])
ws_router = APIRouter(tags=["intelligence-live"])


def _operator_id(request: Request) -> str:
    """Represent the current auth boundary without fabricating a user identity."""
    # Aegis currently authenticates dashboard calls with its server-side API
    # key. A future verified RBAC identity can replace this value here.
    return "api-key-authenticated-operator"


@router.get("/capabilities", response_model=LiveCapabilities, response_model_by_alias=True)
async def get_capabilities(_: bool = Depends(verify_api_key)) -> LiveCapabilities:
    """Return a truthful configuration capability state without opening Gemini."""
    return get_live_session_manager().capabilities()


@router.post("/sessions", response_model=LiveSessionResponse, response_model_by_alias=True, status_code=201)
async def create_session(
    payload: LiveSessionCreate,
    request: Request,
    __: bool = Depends(verify_api_key),
) -> LiveSessionResponse:
    """Create one short-lived browser connection token after API-key auth."""
    try:
        response = await get_live_session_manager().create(
            _operator_id(request),
            audible_alert_id=payload.audible_alert_id,
        )
    except LiveCapabilityError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return response


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    _: bool = Depends(verify_api_key),
) -> Response:
    # Idempotent close avoids revealing whether another session identifier ever
    # existed. It also immediately invalidates its browser connection token.
    await get_live_session_manager().close(session_id)
    return Response(status_code=204)


@ws_router.websocket("/ws/intelligence/live/{session_id}")
async def intelligence_live_socket(websocket: WebSocket, session_id: str) -> None:
    """Browser-compatible short-lived-token handshake; no API key in the URL."""
    protocols = [item.strip() for item in websocket.headers.get("sec-websocket-protocol", "").split(",") if item.strip()]
    connection_token = next((item for item in protocols if item != LIVE_WS_PROTOCOL), "")
    if LIVE_WS_PROTOCOL not in protocols or not connection_token:
        await websocket.close(code=4401)
        return
    # Token URL-safe alphabet is also valid as a WebSocket subprotocol token.
    if not all(char.isalnum() or char in "-_" for char in connection_token):
        await websocket.close(code=4401)
        return
    await run_live_gateway(websocket, session_id, connection_token)
