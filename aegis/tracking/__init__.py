"""
AegisAI Tracking Module

Provides multi-object tracking capabilities.
Phase 1 uses ByteTrack (CPU-optimized, IoU-based).
DeepSORT is available for backward compatibility.
"""

from aegis.tracking.bytetrack_tracker import ByteTrackTracker

# Keep DeepSORT available for backward compatibility
try:
    from aegis.tracking.deepsort_tracker import DeepSORTTracker
    _DEEPSORT_AVAILABLE = True
except ImportError:
    _DEEPSORT_AVAILABLE = False

__all__ = ["ByteTrackTracker"]

if _DEEPSORT_AVAILABLE:
    __all__.append("DeepSORTTracker")
