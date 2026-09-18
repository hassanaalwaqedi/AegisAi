"""
AegisAI - Camera Utilities

Shared helpers for URL masking, ID sanitization, frame decoding.
"""

from __future__ import annotations

import base64
import re
from typing import Optional
from urllib.parse import parse_qs, quote, urlparse, urlunparse

import cv2
import numpy as np


def mask_url(raw_url: Optional[str]) -> Optional[str]:
    """Return a display-safe URL without credentials or query-string secrets."""
    if not raw_url:
        return raw_url

    parsed = urlparse(raw_url)
    host = parsed.hostname or ""
    try:
        port = parsed.port
    except ValueError:
        port = None
    if port:
        host = f"{host}:{port}"

    # A username is also a credential and signed query strings frequently
    # contain access tokens.  Neither belongs in operational UI/log output.
    netloc = f"****@{host}" if (parsed.username or parsed.password) else host

    return urlunparse(
        (
            parsed.scheme,
            netloc,
            parsed.path,
            parsed.params,
            "redacted" if parsed.query else "",
            "",
        )
    )


def redact_url_for_persistence(raw_url: Optional[str]) -> Optional[str]:
    """Keep only the non-secret endpoint portion in the camera registry."""
    if not raw_url:
        return raw_url
    parsed = urlparse(raw_url)
    host = parsed.hostname or ""
    try:
        port = parsed.port
    except ValueError:
        port = None
    if port:
        host = f"{host}:{port}"
    return urlunparse((parsed.scheme, host, parsed.path, parsed.params, "", ""))


def normalise_stream_identity(raw_url: Optional[str]) -> Optional[str]:
    """Return a credential-free endpoint identity for duplicate detection."""
    if not raw_url:
        return None
    parsed = urlparse(raw_url)
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower().rstrip(".")
    if not scheme or not host:
        return None
    default_port = 554 if scheme in {"rtsp", "rtsps"} else 443 if scheme == "https" else 80
    try:
        port = parsed.port or default_port
    except ValueError:
        return None
    path = "/" + parsed.path.lstrip("/") if parsed.path else "/"

    # A YouTube watch page is a catalogue endpoint, not the media endpoint.
    # Its ``v`` parameter identifies the actual video and must remain part of
    # duplicate detection; otherwise every YouTube video is treated as one
    # camera.  The same canonical identity covers watch, short, live, and
    # embedded links for a single video.
    youtube_host = host in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"} or host.endswith(".youtube.com")
    if youtube_host:
        path_parts = [part for part in path.split("/") if part]
        video_id: Optional[str] = None
        if host == "youtu.be" and path_parts:
            video_id = path_parts[0]
        elif path.rstrip("/") == "/watch":
            video_id = (parse_qs(parsed.query).get("v") or [None])[0]
        elif len(path_parts) >= 2 and path_parts[0] in {"shorts", "live", "embed"}:
            video_id = path_parts[1]
        if isinstance(video_id, str) and video_id.strip():
            return f"youtube-video:{video_id.strip()}"

    # Query strings are intentionally excluded: they are often credentials
    # and must not make the same physical stream appear unique. YouTube video
    # identities are the exception above because their query names the media.
    return f"{host}:{port}{path.rstrip('/') or '/'}"


def build_rtsp_url(
    *,
    protocol: str,
    host: str,
    port: int = 554,
    stream_path: str = "",
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> str:
    """Build a correctly escaped RTSP URL from guided registration fields."""
    normalized_protocol = protocol.lower().strip()
    if normalized_protocol not in {"rtsp", "rtsps"}:
        raise ValueError("RTSP protocol must be rtsp or rtsps")
    normalized_host = host.strip()
    if not normalized_host:
        raise ValueError("RTSP host is required")
    if not 1 <= int(port) <= 65535:
        raise ValueError("RTSP port must be between 1 and 65535")

    # URL parsing expects literal IPv6 hosts to be bracketed in netloc.
    rendered_host = (
        f"[{normalized_host}]"
        if ":" in normalized_host and not normalized_host.startswith("[")
        else normalized_host
    )
    credentials = ""
    if username or password:
        encoded_username = quote(username or "", safe="")
        encoded_password = quote(password or "", safe="")
        credentials = f"{encoded_username}:{encoded_password}@"
    path = "/" + stream_path.strip().lstrip("/") if stream_path.strip() else "/"
    return urlunparse((normalized_protocol, f"{credentials}{rendered_host}:{int(port)}", path, "", "", ""))


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
