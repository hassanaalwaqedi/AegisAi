from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from aegis.camera.manager import MultiCameraPipelineManager
from aegis.camera.types import CameraSourceType


def test_browser_frame_acknowledges_before_background_inference(monkeypatch):
    """A slow model must not make the browser camera queue stale frames."""

    started = threading.Event()
    release = threading.Event()

    class Ingestion:
        def process_frame(self, *_args):
            started.set()
            assert release.wait(timeout=1)
            return {}

    manager = object.__new__(MultiCameraPipelineManager)
    manager._lock = threading.RLock()
    manager._processing = {}
    manager._last_submit = {}
    manager._executor = ThreadPoolExecutor(max_workers=1)
    manager.ingestion = Ingestion()

    class Source:
        config = SimpleNamespace(
            source_type=CameraSourceType.BROWSER_WEBCAM,
            metadata={},
            name=None,
        )
        is_running = True

        def __init__(self):
            self.frames_received = 0
            self.notify_pipeline = None

        def ingest_frame(self, frame, notify_pipeline=True):
            self.frames_received += 1
            self.notify_pipeline = notify_pipeline
            if notify_pipeline:
                manager._handle_frame("browser-cam", frame)

        def get_status(self):
            return SimpleNamespace(frames_received=self.frames_received)

    source = Source()
    manager._sources = {"browser-cam": source}
    monkeypatch.setattr("aegis.camera.manager.decode_base64_frame", lambda _: object())

    try:
        started_at = time.monotonic()
        response = manager.ingest_browser_frame("browser-cam", "frame")

        assert time.monotonic() - started_at < 0.1
        assert response["processing"] is True
        assert response["detections"] == []
        assert source.notify_pipeline is True
        assert started.wait(timeout=0.5)
    finally:
        release.set()
        manager._executor.shutdown(wait=True)
