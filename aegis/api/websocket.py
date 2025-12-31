"""
AegisAI - WebSocket Module

Real-time WebSocket endpoint for live dashboard updates.

Sprint 2: Production Hardening
"""

import json
import asyncio
import logging
from typing import Set, Dict, Any
from datetime import datetime

from fastapi import WebSocket, WebSocketDisconnect
from fastapi.routing import APIRouter

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
    
    async def connect(self, websocket: WebSocket) -> None:
        """Accept and track new connection."""
        await websocket.accept()
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
    await manager.connect(websocket)
    
    try:
        while True:
            # Send current state
            state = get_state()
            
            message = {
                "type": "update",
                "timestamp": datetime.now().isoformat(),
                "status": state.get_status(),
                "tracks": state.get_tracks(),
                "events": state.get_events(limit=20),
                "statistics": state.get_statistics()
            }
            
            await websocket.send_json(message)
            
            # Wait before next update
            await asyncio.sleep(0.5)
            
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await manager.disconnect(websocket)


@ws_router.get("/ws/clients")
async def get_client_count():
    """Get number of connected WebSocket clients."""
    return {"count": manager.client_count}


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
