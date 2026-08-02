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
    recordings_router,
    health_router,
    metrics_router,
)
from aegis.api.routes.intelligence import router as intelligence_router
from aegis.api.routes.intelligence_context import router as intelligence_context_router
from aegis.api.routes.intelligence_live import router as intelligence_live_router, ws_router as intelligence_live_ws_router
from aegis.api.routes.system_knowledge import router as system_knowledge_router, admin_router as system_knowledge_admin_router
from aegis.api.security import (
    limiter,
    rate_limit_exceeded_handler,
    verify_api_key,
    get_allowed_origins,
    get_rate_limit,
    is_debug_mode,
)
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

# Load environment variables
load_dotenv()

# Configure module logger
logger = logging.getLogger(__name__)


def _env_enabled(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _initialize_semantic_state() -> None:
    """Initialise fast evidence search; visual DINO remains opt-in elsewhere."""
    state = get_state()
    if getattr(state, "semantic_query_engine", None) is not None:
        return

    try:
        from config import SemanticConfig
        from aegis.semantic.prompt_manager import PromptManager
        from aegis.semantic.query_engine import SemanticQueryEngine

        config = SemanticConfig()
        state.semantic_prompt_manager = PromptManager(cache_ttl=config.cache_ttl_seconds)
        state.semantic_query_engine = SemanticQueryEngine()
        state.unified_intelligence = []
        state.active_semantic_query = None
        state.active_semantic_prompt_id = None
        state.semantic_triggers = 0
        state.semantic_matches = 0
        logger.info("Semantic live-evidence query engine enabled")
    except Exception as exc:
        logger.warning("Semantic prompt manager could not be initialized: %s", exc)


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
        description="AI Security Operating System - REST API",
        version="5.0.0",
        docs_url="/docs" if is_debug_mode() else None,
        redoc_url="/redoc" if is_debug_mode() else None,
    )
    _initialize_semantic_state()

    # Add rate limiter
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    # Add CORS middleware with restricted origins (include frontend and local network)
    cors_origins = list(config.cors_origins) + [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",        # Vite dev server
        "http://127.0.0.1:5173",        # Vite dev server
        "http://192.168.137.1:3000",    # Local network access
        "http://192.168.137.1:5173",
        "http://192.168.1.1:3000",
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["X-API-Key", "X-Aegis-Admin-Key", "Content-Type", "Authorization"],
    )

    # Include REST routers with API key dependency
    app.include_router(status_router, dependencies=[Depends(verify_api_key)])
    app.include_router(events_router, dependencies=[Depends(verify_api_key)])
    app.include_router(tracks_router, dependencies=[Depends(verify_api_key)])
    app.include_router(statistics_router, dependencies=[Depends(verify_api_key)])
    app.include_router(intelligence_router, dependencies=[Depends(verify_api_key)])
    app.include_router(intelligence_context_router)
    app.include_router(intelligence_live_router)
    app.include_router(intelligence_live_ws_router)
    app.include_router(semantic_router, dependencies=[Depends(verify_api_key)])
    app.include_router(system_knowledge_router)
    app.include_router(system_knowledge_admin_router)
    app.include_router(export_router, dependencies=[Depends(verify_api_key)])

    # Mode and Operations routers (mode switch available without API key for frontend)
    app.include_router(mode_router)  # Public mode query
    app.include_router(operations_router, dependencies=[Depends(verify_api_key)])

    # AI/NLQ router (Gemini integration)
    app.include_router(nlq_router, dependencies=[Depends(verify_api_key)])

    # Browser frame analysis router
    app.include_router(analyze_router, dependencies=[Depends(verify_api_key)])

    # Camera management router. REST routes enforce API keys internally;
    # camera WebSockets use their own connection lifecycle.
    app.include_router(cameras_router)

    # Detection results router
    app.include_router(detections_router, dependencies=[Depends(verify_api_key)])

    # Alert management router
    app.include_router(alerts_router, dependencies=[Depends(verify_api_key)])

    # Recordings management router
    app.include_router(recordings_router, dependencies=[Depends(verify_api_key)])

    # Infrastructure-only Prometheus metrics. This carries no operator data or
    # sensitive labels and remains behind the same API-key boundary as APIs.
    app.include_router(metrics_router, dependencies=[Depends(verify_api_key)])

    # Health check endpoints (no auth — must be accessible by container orchestration)
    app.include_router(health_router)

    # Pipeline monitoring & control (auth required)
    try:
        from aegis.api.routes.pipeline import router as pipeline_router
        app.include_router(pipeline_router, dependencies=[Depends(verify_api_key)])
    except ImportError:
        logger.warning("Pipeline monitoring routes not available")

    # AI Orchestrator routes (Gemini integration)
    try:
        from aegis.ai.routes import router as ai_router
        app.include_router(ai_router)
        logger.info("AI orchestrator routes registered")
    except ImportError:
        logger.warning("AI orchestrator routes not available")

    # Include WebSocket router (no API key for WS, handled differently)
    try:
        from aegis.api.websocket import ws_router
        app.include_router(ws_router)
    except ImportError:
        logger.warning("WebSocket module not available")

    # Serve React SOC dashboard from frontend/dist (production build)
    if config.serve_dashboard:
        frontend_dist = Path(__file__).parent.parent.parent / "frontend" / "dist"
        frontend_assets = frontend_dist / "assets"
        frontend_index = frontend_dist / "index.html"

        if frontend_index.exists():
            # Serve static assets (JS, CSS, images)
            if frontend_assets.exists():
                app.mount(
                    "/assets",
                    StaticFiles(directory=str(frontend_assets)),
                    name="frontend-assets",
                )

            @app.get("/dashboard")
            async def dashboard():
                """Serve React SOC dashboard."""
                return FileResponse(str(frontend_index))
        else:
            logger.info(
                "Frontend dist not found: %s — use Vite dev server", frontend_dist
            )

    @app.get("/")
    async def root():
        """Root endpoint — serve React SOC dashboard or API info."""
        frontend_dist = Path(__file__).parent.parent.parent / "frontend" / "dist"
        idx = frontend_dist / "index.html"
        if idx.exists():
            return FileResponse(str(idx))
        return {
            "name": "AegisAI API",
            "version": "5.0.0",
            "status": "online",
            "dashboard": "/dashboard",
            "docs": "/docs" if is_debug_mode() else None,
            "healthz": "/healthz",
            "readyz": "/readyz",
            "endpoints": {
                "status": "/status",
                "alerts": "/alerts",
                "tracks": "/tracks",
                "statistics": "/statistics",
                "ws": "/ws",
            },
        }

    @app.get("/api")
    async def api_info():
        """API info endpoint."""
        return {
            "name": "AegisAI API",
            "version": "5.0.0",
            "endpoints": {
                "status": "/status",
                "events": "/events",
                "tracks": "/tracks",
                "statistics": "/statistics",
                "intelligence": "/intelligence",
                "intelligence_context": "/api/intelligence/context",
                "dashboard": "/dashboard",
                "healthz": "/healthz",
                "readyz": "/readyz",
                "docs": "/docs",
                "pipeline": "/pipeline/stats",
            },
        }

    # Pipeline lifecycle — start on app startup, stop on shutdown
    # Establish the schema for the active ``aegis.database`` persistence
    # stack before a pipeline can emit any risk alert. This is idempotent and
    # does not create operational records.
    @app.on_event("startup")
    async def _startup_database_schema():
        try:
            from aegis.database.connection import create_tables

            create_tables()
            logger.info("Database persistence schema is ready")
        except Exception as exc:
            logger.warning("Database schema initialization failed: %s", exc)

    @app.on_event("startup")
    async def _startup_pipeline():
        try:
            from aegis.pipeline.startup import create_pipeline
            from aegis.settings import get_settings
            settings = get_settings()
            create_pipeline(
                model_path=settings.detection.model_path,
                confidence=settings.detection.confidence_threshold,
                device=settings.get_device_string(),
                auto_start=_env_enabled("AEGIS_PIPELINE_AUTOSTART", default=False),
                warm_model=_env_enabled("AEGIS_PIPELINE_WARM_MODEL", default=True),
            )
            logger.info(
                "AI pipeline initialized (autostart=%s warm_model=%s)",
                _env_enabled("AEGIS_PIPELINE_AUTOSTART"),
                _env_enabled("AEGIS_PIPELINE_WARM_MODEL", default=True),
            )
        except Exception as exc:
            logger.warning("Pipeline initialization deferred: %s", exc)

    @app.on_event("shutdown")
    async def _shutdown_pipeline():
        try:
            from aegis.pipeline.startup import shutdown_pipeline
            from aegis.core.events import get_event_bus
            shutdown_pipeline()
            get_event_bus().close()
        except Exception as exc:
            logger.warning("Pipeline shutdown error: %s", exc)

    logger.info("FastAPI app created (host=%s, port=%s)", config.host, config.port)
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
        uvi_config = uvicorn.Config(
            self._app,
            host=self._config.host,
            port=self._config.port,
            log_level="warning",  # Reduce uvicorn logging
            access_log=False,
        )
        self._server = uvicorn.Server(uvi_config)

        # Start in background thread
        self._thread = threading.Thread(
            target=self._run_server,
            daemon=True,
            name="AegisAI-API",
        )
        self._thread.start()
        self._running = True

        logger.info(
            "API server started at http://%s:%s", self._config.host, self._config.port
        )

    def _run_server(self) -> None:
        """Run the uvicorn server (called in background thread)."""
        try:
            self._server.run()
        except Exception as e:
            logger.error("API server error: %s", e)
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
