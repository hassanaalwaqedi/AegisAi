"""
AegisAI - Redis Event Bus

Central pub/sub backbone for the AI pipeline. Uses Redis Streams for
durable, ordered event delivery with consumer groups.

Streams:
    aegis:frames:{camera_id}   — raw frames queued for inference
    aegis:detections            — detection results from workers
    aegis:events                — risk events, alerts, status changes
    aegis:metrics               — pipeline telemetry

Design choices:
    - Redis Streams (not Pub/Sub) for durability and consumer groups
    - MAXLEN trimming to bound memory usage
    - Graceful fallback to in-memory queues when Redis is unavailable
    - All serialization uses msgpack for speed (falls back to JSON)
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Try msgpack for fast serialization, fall back to JSON
try:
    import msgpack

    def _serialize(data: Dict[str, Any]) -> bytes:
        return msgpack.packb(data, use_bin_type=True)

    def _deserialize(raw: bytes) -> Dict[str, Any]:
        return msgpack.unpackb(raw, raw=False)

    _SERIALIZER = "msgpack"
except ImportError:
    def _serialize(data: Dict[str, Any]) -> bytes:
        return json.dumps(data, default=str).encode("utf-8")

    def _deserialize(raw: bytes) -> Dict[str, Any]:
        return json.loads(raw)

    _SERIALIZER = "json"


class EventBus:
    """
    Redis Streams-backed event bus with graceful degradation.

    If Redis is unavailable, falls back to in-memory deques so the
    system keeps working (with reduced durability).
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        stream_prefix: str = "aegis",
        maxlen: int = 10000,
        consumer_group: str = "aegis-pipeline",
        max_connections: int = 20,
    ):
        self._redis_url = redis_url
        self._prefix = stream_prefix
        self._maxlen = maxlen
        self._consumer_group = consumer_group
        self._redis = None
        self._pool = None
        self._connected = False
        self._lock = threading.Lock()
        self._max_connections = max_connections

        # In-memory fallback
        self._fallback_streams: Dict[str, Deque[Dict[str, Any]]] = defaultdict(
            lambda: deque(maxlen=maxlen)
        )
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)

        self._connect()

    def _connect(self) -> None:
        """Attempt Redis connection. Non-fatal if unavailable."""
        try:
            import redis

            self._pool = redis.ConnectionPool.from_url(
                self._redis_url,
                max_connections=self._max_connections,
                decode_responses=False,
            )
            self._redis = redis.Redis(connection_pool=self._pool)
            self._redis.ping()
            self._connected = True
            logger.info(
                "Redis event bus connected url=%s serializer=%s",
                self._redis_url,
                _SERIALIZER,
            )
        except Exception as exc:
            self._connected = False
            self._redis = None
            logger.warning(
                "Redis unavailable, using in-memory fallback: %s", exc
            )

    @property
    def is_connected(self) -> bool:
        """Whether the Redis connection is alive."""
        return self._connected

    def stream_key(self, name: str) -> str:
        """Build a full stream key from a short name."""
        return f"{self._prefix}:{name}"

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    def publish(
        self,
        stream: str,
        data: Dict[str, Any],
        maxlen: Optional[int] = None,
    ) -> Optional[str]:
        """
        Publish a message to a stream.

        Returns the message ID if Redis is connected, None otherwise.
        """
        key = self.stream_key(stream)
        maxlen = maxlen or self._maxlen

        if self._connected and self._redis:
            try:
                # Redis Streams require field-value pairs
                msg_id = self._redis.xadd(
                    key,
                    {"d": _serialize(data)},
                    maxlen=maxlen,
                    approximate=True,
                )
                return msg_id.decode() if isinstance(msg_id, bytes) else str(msg_id)
            except Exception as exc:
                logger.debug("Redis publish failed, falling back: %s", exc)
                self._connected = False

        # Fallback: in-memory + local subscribers
        data["_ts"] = time.time()
        self._fallback_streams[key].append(data)
        self._notify_subscribers(stream, data)
        return None

    def publish_many(
        self, stream: str, items: List[Dict[str, Any]]
    ) -> List[Optional[str]]:
        """Publish multiple messages efficiently (pipelined when Redis is up)."""
        if not items:
            return []

        key = self.stream_key(stream)

        if self._connected and self._redis:
            try:
                pipe = self._redis.pipeline(transaction=False)
                for data in items:
                    pipe.xadd(
                        key,
                        {"d": _serialize(data)},
                        maxlen=self._maxlen,
                        approximate=True,
                    )
                results = pipe.execute()
                return [
                    r.decode() if isinstance(r, bytes) else str(r) for r in results
                ]
            except Exception as exc:
                logger.debug("Redis pipeline publish failed: %s", exc)
                self._connected = False

        return [self.publish(stream, data) for data in items]

    # ------------------------------------------------------------------
    # Consuming (pull-based via consumer groups)
    # ------------------------------------------------------------------

    def ensure_group(self, stream: str, group: Optional[str] = None) -> None:
        """Create a consumer group if it doesn't exist."""
        if not self._connected or not self._redis:
            return

        key = self.stream_key(stream)
        group = group or self._consumer_group

        try:
            self._redis.xgroup_create(key, group, id="0", mkstream=True)
        except Exception:
            # Group already exists — that's fine
            pass

    def read(
        self,
        stream: str,
        consumer_name: str,
        count: int = 10,
        block_ms: int = 1000,
        group: Optional[str] = None,
    ) -> List[Tuple[str, Dict[str, Any]]]:
        """
        Read messages from a consumer group.

        Returns list of (message_id, data) tuples.
        """
        if not self._connected or not self._redis:
            return self._read_fallback(stream, count)

        key = self.stream_key(stream)
        group = group or self._consumer_group

        try:
            results = self._redis.xreadgroup(
                group,
                consumer_name,
                {key: ">"},
                count=count,
                block=block_ms,
            )
            if not results:
                return []

            messages = []
            for _stream_key, entries in results:
                for msg_id, fields in entries:
                    msg_id_str = (
                        msg_id.decode() if isinstance(msg_id, bytes) else str(msg_id)
                    )
                    raw = fields.get(b"d") or fields.get("d")
                    if raw:
                        data = _deserialize(raw)
                        messages.append((msg_id_str, data))
            return messages

        except Exception as exc:
            logger.debug("Redis read failed: %s", exc)
            return self._read_fallback(stream, count)

    def ack(
        self,
        stream: str,
        *message_ids: str,
        group: Optional[str] = None,
    ) -> int:
        """Acknowledge processed messages."""
        if not self._connected or not self._redis:
            return 0

        key = self.stream_key(stream)
        group = group or self._consumer_group

        try:
            return self._redis.xack(key, group, *message_ids)
        except Exception:
            return 0

    # ------------------------------------------------------------------
    # Subscribe (callback-based for in-memory fallback)
    # ------------------------------------------------------------------

    def subscribe(self, stream: str, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Register a callback for in-memory fallback mode."""
        self._subscribers[stream].append(callback)

    def _notify_subscribers(self, stream: str, data: Dict[str, Any]) -> None:
        for callback in self._subscribers.get(stream, []):
            try:
                callback(data)
            except Exception as exc:
                logger.error("Subscriber callback error on %s: %s", stream, exc)

    def _read_fallback(
        self, stream: str, count: int
    ) -> List[Tuple[str, Dict[str, Any]]]:
        key = self.stream_key(stream)
        q = self._fallback_streams.get(key)
        if not q:
            return []

        messages = []
        for _ in range(min(count, len(q))):
            try:
                data = q.popleft()
                messages.append((f"fallback-{time.monotonic_ns()}", data))
            except IndexError:
                break
        return messages

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def stream_length(self, stream: str) -> int:
        """Get the length of a stream."""
        if self._connected and self._redis:
            try:
                return self._redis.xlen(self.stream_key(stream))
            except Exception:
                pass
        return len(self._fallback_streams.get(self.stream_key(stream), []))

    def stream_info(self, stream: str) -> Dict[str, Any]:
        """Get info about a stream (length, groups, consumers)."""
        key = self.stream_key(stream)
        info: Dict[str, Any] = {"stream": key, "connected": self._connected}

        if self._connected and self._redis:
            try:
                info["length"] = self._redis.xlen(key)
                groups = self._redis.xinfo_groups(key)
                info["groups"] = [
                    {
                        "name": g.get(b"name", b"").decode()
                        if isinstance(g.get(b"name"), bytes)
                        else str(g.get("name", "")),
                        "consumers": g.get(b"consumers", g.get("consumers", 0)),
                        "pending": g.get(b"pending", g.get("pending", 0)),
                    }
                    for g in groups
                ]
            except Exception:
                info["length"] = 0
                info["groups"] = []
        else:
            info["length"] = len(self._fallback_streams.get(key, []))
            info["groups"] = []

        return info

    def health_check(self) -> Dict[str, Any]:
        """Check Redis connectivity and return status."""
        result = {
            "connected": False,
            "url": self._redis_url,
            "serializer": _SERIALIZER,
            "mode": "redis" if self._connected else "in-memory",
        }

        if self._redis:
            try:
                self._redis.ping()
                result["connected"] = True
                self._connected = True
            except Exception as exc:
                self._connected = False
                result["error"] = str(exc)

        return result

    def close(self) -> None:
        """Shutdown the event bus."""
        if self._pool:
            try:
                self._pool.disconnect()
            except Exception:
                pass
        self._connected = False
        logger.info("Event bus closed")


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_event_bus: Optional[EventBus] = None
_event_bus_lock = threading.Lock()


def get_event_bus() -> EventBus:
    """Get or create the global EventBus singleton."""
    global _event_bus
    if _event_bus is None:
        with _event_bus_lock:
            if _event_bus is None:
                from aegis.settings import get_settings

                settings = get_settings()
                _event_bus = EventBus(
                    redis_url=settings.redis.url,
                    stream_prefix=settings.redis.stream_prefix,
                    maxlen=settings.redis.stream_maxlen,
                    consumer_group=settings.redis.consumer_group,
                    max_connections=settings.redis.max_connections,
                )
    return _event_bus


def reset_event_bus() -> None:
    """Reset the singleton (for testing)."""
    global _event_bus
    if _event_bus:
        _event_bus.close()
    _event_bus = None
