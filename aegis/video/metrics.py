"""Prometheus instrumentation for vehicle enrichment without PII labels."""

from __future__ import annotations

from typing import Any


class NoopVehicleMetrics:
    def request(self) -> None: pass
    def success(self) -> None: pass
    def plate_attempt(self) -> None: pass
    def plate_valid(self) -> None: pass
    def plate_failure(self) -> None: pass
    def duplicate(self) -> None: pass
    def duration(self, seconds: float) -> None: del seconds


def _collector(name: str, factory: Any, documentation: str) -> Any:
    from prometheus_client import REGISTRY
    existing = REGISTRY._names_to_collectors.get(name)  # prometheus registry's stable lookup
    return existing if existing is not None else factory(name, documentation)


class VehicleMetrics:
    def __init__(self) -> None:
        try:
            from prometheus_client import Counter, Histogram
            self._requests = _collector("aegis_vehicle_enrichment_requests", Counter, "Vehicle enrichment requests")
            self._success = _collector("aegis_vehicle_enrichment_success", Counter, "Vehicle enrichments that passed quality gating")
            self._plate_attempts = _collector("aegis_plate_ocr_attempts", Counter, "Plate OCR attempts")
            self._plate_valid = _collector("aegis_plate_ocr_valid_results", Counter, "Validated plate OCR results")
            self._plate_failures = _collector("aegis_plate_ocr_failures", Counter, "Plate OCR failures or invalid results")
            self._duplicates = _collector("aegis_evidence_duplicates_skipped", Counter, "Near duplicate evidence candidates skipped")
            self._duration = _collector("aegis_vehicle_enrichment_duration_seconds", Histogram, "Vehicle enrichment duration")
            self.available = True
        except ImportError:
            self.available = False

    def request(self) -> None:
        if self.available: self._requests.inc()
    def success(self) -> None:
        if self.available: self._success.inc()
    def plate_attempt(self) -> None:
        if self.available: self._plate_attempts.inc()
    def plate_valid(self) -> None:
        if self.available: self._plate_valid.inc()
    def plate_failure(self) -> None:
        if self.available: self._plate_failures.inc()
    def duplicate(self) -> None:
        if self.available: self._duplicates.inc()
    def duration(self, seconds: float) -> None:
        if self.available: self._duration.observe(seconds)


def metrics_payload() -> tuple[bytes, str]:
    try:
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
        return generate_latest(), CONTENT_TYPE_LATEST
    except ImportError:
        return b"# Prometheus client is not installed\n", "text/plain; charset=utf-8"
