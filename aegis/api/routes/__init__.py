"""
AegisAI - Smart City Risk Intelligence System
API Module - Routes Package

Phase 4: Response & Productization Layer
Phase 5: Semantic Intelligence Layer
Phase 6: Mode Selection System
Phase 7: Gemini AI Integration
"""

from aegis.api.routes.status import router as status_router
from aegis.api.routes.events import router as events_router
from aegis.api.routes.tracks import router as tracks_router
from aegis.api.routes.statistics import router as statistics_router
from aegis.api.routes.semantic import router as semantic_router
from aegis.api.routes.export import router as export_router
from aegis.api.routes.mode import router as mode_router
from aegis.api.routes.operations import router as operations_router
from aegis.api.routes.nlq import router as nlq_router
from aegis.api.routes.analyze import router as analyze_router
from aegis.api.routes.cameras import router as cameras_router
from aegis.api.routes.detections import router as detections_router
from aegis.api.routes.alerts import router as alerts_router
from aegis.api.routes.recordings import router as recordings_router

__all__ = [
    "status_router",
    "events_router",
    "tracks_router",
    "statistics_router",
    "semantic_router",
    "export_router",
    "mode_router",
    "operations_router",
    "nlq_router",
    "analyze_router",
    "cameras_router",
    "detections_router",
    "alerts_router",
    "recordings_router",
]

