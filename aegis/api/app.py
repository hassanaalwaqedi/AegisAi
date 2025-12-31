"""
AegisAI - Smart City Risk Intelligence System
API Module - FastAPI Application

Main FastAPI application with CORS, routes, and dashboard serving.

Phase 4: Response & Productization Layer
Sprint 1: Security & Testing Foundation
"""

# Suppress numpy MINGW warning that crashes Python 3.14 on Windows
import warnings
warnings.filterwarnings('ignore', message='.*Numpy built with MINGW.*')

import os
import logging
import threading
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn

from aegis.api.state import get_state, APIState
from aegis.api.routes import (
    status_router,
    events_router,
    tracks_router,
    statistics_router,
    semantic_router,
    export_router,
    mode_router,
    operations_router,
    nlq_router,
    analyze_router,
    cameras_router,
    detections_router,
    alerts_router,
    recordings_router
)
from aegis.api.routes.intelligence import router as intelligence_router
from aegis.api.security import (
    limiter,
    rate_limit_exceeded_handler,
    verify_api_key,
    get_allowed_origins,
    get_rate_limit,
    is_debug_mode
)
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

# Load environment variables
load_dotenv()

# Configure module logger
logger = logging.getLogger(__name__)


@dataclass
class APIConfig:
    """
    API server configuration.
    
    Attributes:
        enabled: Whether API is enabled
        host: Server host address
        port: Server port
        cors_origins: Allowed CORS origins
        serve_dashboard: Whether to serve dashboard files
    """
    enabled: bool = True
    host: str = os.getenv("AEGIS_API_HOST", "127.0.0.1")
    port: int = int(os.getenv("AEGIS_API_PORT", "8080"))
    cors_origins: tuple = tuple(get_allowed_origins())
    serve_dashboard: bool = True


def create_app(config: Optional[APIConfig] = None) -> FastAPI:
    """
    Create FastAPI application with security middleware.
    
    Args:
        config: API configuration
        
    Returns:
        Configured FastAPI app
    """
    config = config or APIConfig()
    
    app = FastAPI(
        title="AegisAI API",
        description="Smart City Risk Intelligence System - REST API",
        version="4.2.0",
        docs_url="/docs" if is_debug_mode() else None,
        redoc_url="/redoc" if is_debug_mode() else None
    )
    
    # Add rate limiter
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    
    # Add CORS middleware with restricted origins (include frontend and local network)
    cors_origins = list(config.cors_origins) + [
        "http://localhost:3000", 
        "http://127.0.0.1:3000",
        "http://192.168.137.1:3000",  # Local network access
        "http://192.168.1.1:3000",
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["X-API-Key", "Content-Type", "Authorization"],
    )
    
    # Include REST routers with API key dependency
    app.include_router(status_router, dependencies=[Depends(verify_api_key)])
    app.include_router(events_router, dependencies=[Depends(verify_api_key)])
    app.include_router(tracks_router, dependencies=[Depends(verify_api_key)])
    app.include_router(statistics_router, dependencies=[Depends(verify_api_key)])
    app.include_router(intelligence_router, dependencies=[Depends(verify_api_key)])
    app.include_router(semantic_router, dependencies=[Depends(verify_api_key)])
    app.include_router(export_router, dependencies=[Depends(verify_api_key)])
    
    # Mode and Operations routers (mode switch available without API key for frontend)
    app.include_router(mode_router)  # Public mode query
    app.include_router(operations_router, dependencies=[Depends(verify_api_key)])
    
    # AI/NLQ router (Gemini integration)
    app.include_router(nlq_router, dependencies=[Depends(verify_api_key)])
    
    # Browser frame analysis router
    app.include_router(analyze_router, dependencies=[Depends(verify_api_key)])
    
    # Camera management router
    app.include_router(cameras_router, dependencies=[Depends(verify_api_key)])
    
    # Detection results router
    app.include_router(detections_router, dependencies=[Depends(verify_api_key)])
    
    # Alert management router
    app.include_router(alerts_router, dependencies=[Depends(verify_api_key)])
    
    # Recordings management router
    app.include_router(recordings_router, dependencies=[Depends(verify_api_key)])
    
    # Include WebSocket router (no API key for WS, handled differently)
    try:
        from aegis.api.websocket import ws_router
        app.include_router(ws_router)
    except ImportError:
        logger.warning("WebSocket module not available")

    
    # Serve dashboard if enabled
    if config.serve_dashboard:
        dashboard_path = Path(__file__).parent.parent / "dashboard"
        
        if dashboard_path.exists():
            app.mount(
                "/static",
                StaticFiles(directory=str(dashboard_path)),
                name="static"
            )
            
            @app.get("/dashboard")
            async def dashboard():
                """Serve dashboard HTML."""
                index_path = dashboard_path / "index.html"
                if index_path.exists():
                    return FileResponse(str(index_path))
                return {"error": "Dashboard not found"}
        else:
            logger.warning(f"Dashboard path not found: {dashboard_path}")
    
    @app.get("/")
    async def root():
        """API root endpoint."""
        return {
            "name": "AegisAI API",
            "version": "5.0.0",
            "endpoints": {
                "status": "/status",
                "events": "/events",
                "tracks": "/tracks",
                "statistics": "/statistics",
                "intelligence": "/intelligence",
                "dashboard": "/dashboard",
                "docs": "/docs"
            }
        }
    
    logger.info(f"FastAPI app created (host={config.host}, port={config.port})")
    return app


class APIServer:
    """
    API server wrapper for background execution.
    
    Runs the FastAPI server in a background thread
    alongside the main processing pipeline.
    
    Example:
        >>> server = APIServer(port=8080)
        >>> server.start()
        >>> # ... pipeline processing ...
        >>> server.stop()
    """
    
    def __init__(self, config: Optional[APIConfig] = None):
        """
        Initialize the API server.
        
        Args:
            config: API configuration
        """
        self._config = config or APIConfig()
        self._app = create_app(self._config)
        self._thread: Optional[threading.Thread] = None
        self._server: Optional[uvicorn.Server] = None
        self._running = False
    
    @property
    def state(self) -> APIState:
        """Get the shared API state."""
        return get_state()
    
    @property
    def is_running(self) -> bool:
        """Check if server is running."""
        return self._running
    
    def start(self) -> None:
        """Start the API server in a background thread."""
        if self._running:
            logger.warning("API server already running")
            return
        
        # Configure uvicorn
        config = uvicorn.Config(
            self._app,
            host=self._config.host,
            port=self._config.port,
            log_level="warning",  # Reduce uvicorn logging
            access_log=False
        )
        self._server = uvicorn.Server(config)
        
        # Start in background thread
        self._thread = threading.Thread(
            target=self._run_server,
            daemon=True,
            name="AegisAI-API"
        )
        self._thread.start()
        self._running = True
        
        logger.info(
            f"API server started at http://{self._config.host}:{self._config.port}"
        )
    
    def _run_server(self) -> None:
        """Run the uvicorn server (called in background thread)."""
        try:
            self._server.run()
        except Exception as e:
            logger.error(f"API server error: {e}")
            self._running = False
    
    def stop(self) -> None:
        """Stop the API server."""
        if not self._running:
            return
        
        if self._server:
            self._server.should_exit = True
        
        self._running = False
        logger.info("API server stopped")
    
    def __repr__(self) -> str:
        return (
            f"APIServer(host={self._config.host}, "
            f"port={self._config.port}, "
            f"running={self._running})"
        )


# Module-level app instance for standalone uvicorn usage:
# uvicorn aegis.api.app:app --reload
app = create_app()
