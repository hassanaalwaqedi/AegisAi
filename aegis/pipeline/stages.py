"""
AegisAI - Pipeline Stage Abstraction

Defines the base interface for pipeline stages and the stream names
used throughout the system. Each stage reads from one Redis stream,
processes, and writes to another.

Pipeline flow:
    Camera → [frames:{camera_id}] → DetectionStage → [detections] →
    TrackingStage → [tracks] → RiskStage → [events] → AlertStage
"""

from __future__ import annotations

import logging
import threading
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from aegis.core.events import EventBus, get_event_bus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Stream name constants
# ---------------------------------------------------------------------------

class Streams:
    """Canonical Redis stream names for the AI pipeline."""

    FRAMES = "frames"            # Raw frames: camera → inference worker
    DETECTIONS = "detections"    # Detection results from YOLO workers
    TRACKS = "tracks"            # Tracked objects with IDs
    RISKS = "risks"              # Risk-scored tracks
    EVENTS = "events"            # High-level events (alerts, status changes)
    METRICS = "metrics"          # Pipeline telemetry
    STATUS = "status"            # Camera status changes

    @staticmethod
    def camera_frames(camera_id: str) -> str:
        """Per-camera frame stream."""
        return f"frames:{camera_id}"


# ---------------------------------------------------------------------------
# Base pipeline stage
# ---------------------------------------------------------------------------

class PipelineStage(ABC):
    """
    Base class for a pipeline processing stage.

    Each stage runs in its own thread, reads from an input stream,
    processes messages, and publishes results to an output stream.
    Stages are designed to be stateless (per-camera state is managed
    via the message payload or external stores).
    """

    def __init__(
        self,
        name: str,
        input_stream: str,
        output_stream: Optional[str] = None,
        event_bus: Optional[EventBus] = None,
        consumer_name: Optional[str] = None,
        batch_size: int = 1,
        block_ms: int = 1000,
    ):
        self.name = name
        self.input_stream = input_stream
        self.output_stream = output_stream
        self._bus = event_bus
        self._consumer_name = consumer_name or f"{name}-0"
        self._batch_size = batch_size
        self._block_ms = block_ms
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._processed = 0
        self._errors = 0
        self._last_process_time: Optional[float] = None

    @property
    def bus(self) -> EventBus:
        if self._bus is None:
            self._bus = get_event_bus()
        return self._bus

    @abstractmethod
    def process(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Process a batch of messages.

        Args:
            messages: List of deserialized message payloads

        Returns:
            List of output payloads to publish to output_stream.
            Return empty list if nothing to publish.
        """
        ...

    def start(self) -> None:
        """Start the stage's processing loop in a background thread."""
        if self._running:
            return
        self._running = True

        # Ensure consumer group exists
        self.bus.ensure_group(self.input_stream)

        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name=f"stage-{self.name}",
        )
        self._thread.start()
        logger.info(
            "Pipeline stage started name=%s input=%s output=%s",
            self.name,
            self.input_stream,
            self.output_stream,
        )

    def stop(self) -> None:
        """Stop the stage's processing loop."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        logger.info("Pipeline stage stopped name=%s processed=%d", self.name, self._processed)

    def _loop(self) -> None:
        """Main processing loop."""
        while self._running:
            try:
                raw_messages = self.bus.read(
                    self.input_stream,
                    self._consumer_name,
                    count=self._batch_size,
                    block_ms=self._block_ms,
                )

                if not raw_messages:
                    continue

                msg_ids = [msg_id for msg_id, _ in raw_messages]
                payloads = [data for _, data in raw_messages]

                start = time.monotonic()
                results = self.process(payloads)
                self._last_process_time = time.monotonic() - start
                self._processed += len(payloads)

                # Publish results
                if results and self.output_stream:
                    self.bus.publish_many(self.output_stream, results)

                # Acknowledge processed messages
                if msg_ids:
                    self.bus.ack(self.input_stream, *msg_ids)

            except Exception as exc:
                self._errors += 1
                logger.exception(
                    "Pipeline stage error name=%s: %s", self.name, exc
                )
                # Back off on errors to avoid tight error loops
                time.sleep(min(1.0 * self._errors, 10.0))

    def get_stats(self) -> Dict[str, Any]:
        """Return stage metrics."""
        return {
            "name": self.name,
            "input_stream": self.input_stream,
            "output_stream": self.output_stream,
            "running": self._running,
            "messages_processed": self._processed,
            "errors": self._errors,
            "last_process_time_ms": (
                round(self._last_process_time * 1000, 2)
                if self._last_process_time
                else None
            ),
        }


# ---------------------------------------------------------------------------
# Pipeline manager
# ---------------------------------------------------------------------------

class Pipeline:
    """
    Manages a set of pipeline stages with lifecycle control.

    Usage:
        pipeline = Pipeline()
        pipeline.add_stage(DetectionStage(...))
        pipeline.add_stage(TrackingStage(...))
        pipeline.start()
        # ... later ...
        pipeline.stop()
    """

    def __init__(self):
        self._stages: List[PipelineStage] = []
        self._running = False

    def add_stage(self, stage: PipelineStage) -> "Pipeline":
        """Add a stage to the pipeline. Returns self for chaining."""
        self._stages.append(stage)
        return self

    def start(self) -> None:
        """Start all stages."""
        if self._running:
            return
        self._running = True
        for stage in self._stages:
            stage.start()
        logger.info("Pipeline started with %d stages", len(self._stages))

    def stop(self) -> None:
        """Stop all stages (in reverse order for clean shutdown)."""
        self._running = False
        for stage in reversed(self._stages):
            stage.stop()
        logger.info("Pipeline stopped")

    def get_stats(self) -> Dict[str, Any]:
        """Return stats for all stages."""
        return {
            "running": self._running,
            "stages": [stage.get_stats() for stage in self._stages],
        }
