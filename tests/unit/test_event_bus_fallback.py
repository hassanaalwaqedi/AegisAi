"""Regression tests for the CPU-safe local event-bus fallback."""

from __future__ import annotations

import threading
import time

from aegis.core.events import EventBus


def _offline_bus(monkeypatch) -> EventBus:
    monkeypatch.setattr(EventBus, "_connect", lambda self: None)
    return EventBus()


def test_empty_fallback_read_blocks_until_a_message_is_published(monkeypatch) -> None:
    bus = _offline_bus(monkeypatch)
    received = []
    ready = threading.Event()

    def reader() -> None:
        ready.set()
        received.extend(bus.read("events", "test-reader", block_ms=500))

    thread = threading.Thread(target=reader)
    thread.start()
    assert ready.wait(timeout=0.1)
    time.sleep(0.03)
    assert thread.is_alive()

    event = {"event_id": "risk-1"}
    bus.publish("events", event)
    thread.join(timeout=0.3)

    assert not thread.is_alive()
    assert received[0][1]["event_id"] == "risk-1"
    assert "_ts" not in event
