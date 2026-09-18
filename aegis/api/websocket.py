"""
AegisAI - WebSocket Module

Real-time WebSocket endpoint for live dashboard updates.

Sprint 2: Production Hardening
"""

import json
import asyncio
import logging
import time
from typing import Set, Dict, Any
from datetime import datetime

from fastapi import APIRouter, Depends, Header, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from aegis.api.security import (
    WEBSOCKET_AUTH_PROTOCOL,
    create_websocket_access_token,
    verify_api_key,
    verify_websocket_auth,
    websocket_subprotocol_token,
)
from aegis.api.state import get_state

# Configure module logger
logger = logging.getLogger(__name__)

# WebSocket router
ws_router = APIRouter()

# Connected clients
_clients: Set[WebSocket] = set()
_broadcast_task = None


class ConnectionManager:
    """
    Manages WebSocket connections.
    
    Handles client connections, disconnections, and broadcasting.
    """
    
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket, *, subprotocol: str | None = None) -> None:
        """Accept and track new connection."""
        await websocket.accept(subprotocol=subprotocol)
        async with self._lock:
            self.active_connections.add(websocket)
        logger.info(f"WebSocket connected. Total: {len(self.active_connections)}")
    
    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove disconnected client."""
        async with self._lock:
            self.active_connections.discard(websocket)
        logger.info(f"WebSocket disconnected. Total: {len(self.active_connections)}")
    
    async def broadcast(self, message: Dict[str, Any]) -> None:
        """Send message to all connected clients."""
        if not self.active_connections:
            return
        
        data = json.dumps(message, default=str)
        disconnected = set()
        
        async with self._lock:
            for connection in self.active_connections:
                try:
                    await connection.send_text(data)
                except Exception:
                    disconnected.add(connection)
            
            # Remove disconnected clients
            self.active_connections -= disconnected
    
    @property
    def client_count(self) -> int:
        """Number of connected clients."""
        return len(self.active_connections)


# Global connection manager
manager = ConnectionManager()


def build_live_state_message(state: Any) -> Dict[str, Any]:
    """Build a truthful dashboard update from the current shared state.

    An idle pipeline is not an event stream.  Clients receive a heartbeat and
    current system status until there are actual tracks or events to publish.
    This prevents empty arrays from being mistaken for simulated live data.
    """
    status = state.get_status()
    tracks = state.get_tracks()
    events = state.get_events(limit=20)
    timestamp = datetime.now().isoformat()
    if not tracks and not events:
        return {
            "type": "heartbeat",
            "timestamp": timestamp,
            "status": status,
        }
    return {
        "type": "update",
        "timestamp": timestamp,
        "status": status,
        "tracks": tracks,
        "events": events,
        "statistics": state.get_statistics(),
    }


@ws_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time updates.
    
    Sends system state updates every 500ms.
    
    Message format:
    {
        "type": "update",
        "timestamp": "ISO datetime",
        "status": {...},
        "tracks": [...],
        "events": [...],
        "statistics": {...}
    }
    """
    if not await verify_websocket_auth(websocket):
        return

    selected_protocol = (
        WEBSOCKET_AUTH_PROTOCOL if websocket_subprotocol_token(websocket) else None
    )
    await manager.connect(websocket, subprotocol=selected_protocol)
    
    try:
        while True:
            # Send current state
            state = get_state()
            
            message = build_live_state_message(state)
            
            await websocket.send_json(message)
            
            # Wait before next update
            await asyncio.sleep(0.5)
            
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await manager.disconnect(websocket)


@ws_router.get("/ws/clients")
async def get_client_count(_: bool = Depends(verify_api_key)):
    """Get number of connected WebSocket clients."""
    return {"count": manager.client_count}


@ws_router.post("/ws/token")
async def create_dashboard_websocket_token(
    x_aegis_actor: str | None = Header(default=None),
    _: bool = Depends(verify_api_key),
):
    """Exchange server-authenticated API access for a short-lived WS token."""
    token, expires_at = create_websocket_access_token()
    from aegis.audit import record_audit

    record_audit(
        "auth.websocket_token_issued",
        actor_id=(str(x_aegis_actor or "").strip()[:160] or "api-key-operator"),
        resource_type="authentication",
        resource_id="dashboard-websocket",
        details={"ttl_seconds": max(0, expires_at - int(time.time()))},
    )
    return JSONResponse(
        content={
            "token": token,
            "protocol": WEBSOCKET_AUTH_PROTOCOL,
            "expires_at": expires_at,
        },
        headers={"Cache-Control": "no-store"},
    )


async def broadcast_event(event: Dict[str, Any]) -> None:
    """
    Broadcast an event to all connected clients.
    
    Use this to push immediate alerts.
    
    Args:
        event: Event data to broadcast
    """
    message = {
        "type": "event",
        "timestamp": datetime.now().isoformat(),
        "event": event
    }
    await manager.broadcast(message)


async def broadcast_alert(alert: Dict[str, Any]) -> None:
    """
    Broadcast a high-priority alert.
    
    Args:
        alert: Alert data to broadcast
    """
    message = {
        "type": "alert",
        "timestamp": datetime.now().isoformat(),
        "alert": alert,
        "priority": "high"
    }
    await manager.broadcast(message)
