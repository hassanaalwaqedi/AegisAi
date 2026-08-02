"""
AegisAI - Camera Utilities

Shared helpers for URL masking, ID sanitization, frame decoding.
"""

from __future__ import annotations

import base64
import re
from typing import Optional
from urllib.parse import urlparse, urlunparse

import cv2
import numpy as np


def mask_url(raw_url: Optional[str]) -> Optional[str]:
    """Mask credentials in a URL for safe logging/display."""
    if not raw_url:
        return raw_url

    parsed = urlparse(raw_url)
    if not parsed.username and not parsed.password:
        return raw_url

    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"

    if parsed.username:
        netloc = f"{parsed.username}:****@{host}"
    else:
        netloc = host

    return urlunparse(
        (parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment)
    )


def safe_camera_id(value: str) -> str:
    """Sanitize a camera ID to alphanumeric + hyphens/underscores."""
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip())
    normalized = normalized.strip("-_")
    if not normalized:
        raise ValueError("camera_id must contain at least one letter or number")
    return normalized[:80]


def decode_base64_frame(frame: str) -> np.ndarray:
    """Decode a base64-encoded image into an OpenCV BGR ndarray."""
    if "," in frame:
        frame = frame.split(",", 1)[1]
    try:
        frame_bytes = base64.b64decode(frame, validate=True)
    except Exception as exc:
        raise ValueError("Frame is not valid base64 image data") from exc

    image_array = np.frombuffer(frame_bytes, np.uint8)
    decoded = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    if decoded is None:
        raise ValueError("Frame could not be decoded as an image")
    return decoded


def validate_stream_url(
    raw_url: Optional[str], allowed_schemes: set[str], label: str
) -> None:
    """Validate a streaming URL has the correct scheme and host."""
    if not raw_url:
        raise ValueError(f"{label} requires url")
    parsed = urlparse(raw_url)
    if parsed.scheme.lower() not in allowed_schemes:
        allowed = ", ".join(sorted(allowed_schemes))
        raise ValueError(f"{label} URL must use one of: {allowed}")
    if not parsed.hostname:
        raise ValueError(f"{label} URL must include a host")


def frame_to_data_url(jpeg_bytes: bytes) -> str:
    """Convert JPEG bytes to a data URL string."""
    return "data:image/jpeg;base64," + base64.b64encode(jpeg_bytes).decode("ascii")
