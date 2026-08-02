"""
AegisAI - Structured Logging Configuration

Provides JSON-structured logging with correlation IDs for production
observability. Replaces scattered logging.basicConfig() calls.

Usage:
    from aegis.core.logging import setup_logging, get_logger

    setup_logging(debug=True)  # Call once at startup
    logger = get_logger(__name__)
    logger.info("camera.connected", camera_id="cam-1", status="online")
"""

from __future__ import annotations

import logging
import os
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

# Correlation ID for request tracing
_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")


def new_correlation_id() -> str:
    """Generate a new correlation ID."""
    return uuid.uuid4().hex[:12]


def get_correlation_id() -> str:
    """Get the current correlation ID."""
    return _correlation_id.get()


def set_correlation_id(cid: str) -> None:
    """Set the correlation ID for the current context."""
    _correlation_id.set(cid)


class JSONFormatter(logging.Formatter):
    """
    JSON log formatter for structured logging.

    Output format:
        {"ts": "...", "level": "INFO", "logger": "aegis.api", "msg": "...",
         "correlation_id": "...", "extra": {...}}
    """

    def format(self, record: logging.LogRecord) -> str:
        import json

        log_entry: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        # Add correlation ID if set
        cid = get_correlation_id()
        if cid:
            log_entry["correlation_id"] = cid

        # Add extra fields (passed via logger.info("msg", extra={...}))
        standard_attrs = {
            "name", "msg", "args", "created", "relativeCreated", "exc_info",
            "exc_text", "stack_info", "lineno", "funcName", "pathname",
            "filename", "module", "levelno", "levelname", "msecs",
            "thread", "threadName", "process", "processName", "taskName",
            "message",
        }
        extras = {
            k: v for k, v in record.__dict__.items()
            if k not in standard_attrs and not k.startswith("_")
        }
        if extras:
            log_entry["extra"] = extras

        # Add exception info
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str, ensure_ascii=False)


class HumanFormatter(logging.Formatter):
    """
    Human-readable log formatter for development.

    Output format:
        2024-01-15 10:30:00 | INFO     | aegis.api | Message here
    """

    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )


def setup_logging(
    debug: bool = False,
    json_output: bool | None = None,
    level: str | None = None,
) -> None:
    """
    Configure logging for the entire application.

    Call this ONCE at application startup, before any other imports that log.

    Args:
        debug: Enable debug-level logging.
        json_output: Force JSON output. If None, auto-detect (JSON in
                     production, human-readable in debug/tty).
        level: Override log level (DEBUG, INFO, WARNING, ERROR).
    """
    # Determine log level
    if level:
        log_level = getattr(logging, level.upper(), logging.INFO)
    elif debug:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO

    # Determine output format
    if json_output is None:
        # Use JSON in production (non-TTY), human-readable in development
        use_json = not (sys.stderr.isatty() or debug)
    else:
        use_json = json_output

    # Create formatter
    formatter = JSONFormatter() if use_json else HumanFormatter()

    # Configure root logger
    root = logging.getLogger()
    root.setLevel(log_level)

    # Remove existing handlers to avoid duplicates
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    # Add stream handler
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)
    root.addHandler(handler)

    # These transports can emit one log record for every camera frame or
    # WebSocket payload. Keep warnings and errors, but never let diagnostic
    # mode turn active video streams into disk I/O that delays the API or the
    # Gemini Live gateway.
    for noisy in (
        "urllib3",
        "httpx",
        "httpcore",
        "ultralytics",
        "sqlalchemy.engine",
        "uvicorn",
        "uvicorn.access",
        "uvicorn.error",
        "websockets",
        "websockets.client",
        "websockets.server",
    ):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance.

    Prefer this over logging.getLogger() for consistency.

    Args:
        name: Logger name (typically __name__).

    Returns:
        Configured logger.
    """
    return logging.getLogger(name)
