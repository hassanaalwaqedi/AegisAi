"""Optional local-only vehicle make/model provider interface."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import numpy as np

from aegis.video.vehicle_types import MakeModelEstimate


class MakeModelProvider(Protocol):
    def classify(self, crop: np.ndarray) -> MakeModelEstimate: ...


class LocalVehicleMakeModelService:
    """Reports unavailable until an explicitly configured local specialist model exists.

    The service intentionally does not load ImageNet weights or request models
    from Hugging Face, because either would be a misleading vehicle identity
    classifier and would trigger an implicit download.
    """

    def __init__(self, *, enabled: bool, model_path: str = "", labels_path: str = "", architecture: str = "") -> None:
        self.enabled = enabled
        self.model_path = Path(model_path) if model_path else None
        self.labels_path = Path(labels_path) if labels_path else None
        self.architecture = architecture

    def classify(self, crop: np.ndarray) -> MakeModelEstimate:
        del crop
        if not self.enabled:
            return MakeModelEstimate(reason="disabled")
        if not self.model_path or not self.labels_path or not self.architecture:
            return MakeModelEstimate(reason="model_not_configured")
        if not self.model_path.exists() or not self.labels_path.exists():
            return MakeModelEstimate(reason="model_path_missing")
        return MakeModelEstimate(reason="local_provider_not_initialized")
