"""
Resolve YouTube watch/share URLs into direct media stream URLs.

OpenCV cannot read a YouTube HTML watch page. This helper uses yt-dlp,
when installed, to extract a temporary direct media URL that OpenCV/FFmpeg
can open like any other HTTP video stream.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import urlparse


YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
}


@dataclass(frozen=True)
class ResolvedYouTubeStream:
    source_url: str
    stream_url: str
    title: Optional[str] = None
    format_id: Optional[str] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    headers: Dict[str, str] | None = None


def is_youtube_url(raw_url: Optional[str]) -> bool:
    if not raw_url:
        return False
    parsed = urlparse(raw_url)
    hostname = (parsed.hostname or "").lower()
    return hostname in YOUTUBE_HOSTS or hostname.endswith(".youtube.com")


def resolve_youtube_stream(raw_url: str) -> ResolvedYouTubeStream:
    try:
        from yt_dlp import YoutubeDL
    except ImportError as exc:
        raise RuntimeError(
            "YouTube HTTP streams require yt-dlp. Install dependencies with: pip install -r requirements.txt"
        ) from exc

    options: Dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "format": (
            "bestvideo[height<=720][vcodec^=avc1][protocol^=http]/"
            "bestvideo[height<=720][ext=mp4][protocol^=http]/"
            "best[height<=720][protocol^=http][vcodec!=none]/"
            "best[protocol^=http][vcodec!=none]/best"
        ),
    }

    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(raw_url, download=False)

    if not isinstance(info, dict):
        raise RuntimeError("yt-dlp did not return video metadata")

    stream_url = info.get("url")
    if not stream_url:
        raise RuntimeError("yt-dlp could not resolve a direct media stream URL")

    return ResolvedYouTubeStream(
        source_url=raw_url,
        stream_url=stream_url,
        title=info.get("title"),
        format_id=str(info.get("format_id")) if info.get("format_id") is not None else None,
        height=info.get("height"),
        fps=info.get("fps"),
        headers=info.get("http_headers") if isinstance(info.get("http_headers"), dict) else None,
    )
