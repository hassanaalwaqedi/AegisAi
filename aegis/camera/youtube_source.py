"""
AegisAI - YouTube Video Camera Source

Decodes YouTube videos into frames for the Aegis detection pipeline.

OpenCV cannot open YouTube CDN URLs directly because they require
session tokens and specific HTTP headers. This source uses yt-dlp
to download to a local temp file, then processes frames from that
file through the standard OpenCV capture loop.

For connection testing, only a short probe is downloaded to verify
end-to-end frame decoding before committing.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import threading
import time
from typing import Any, Dict, Optional, Tuple

import cv2
import numpy as np

from aegis.camera.base import BaseCameraSource, OpenCVLoopCameraSource
from aegis.camera.connection_tests import (
    CameraConnectionTestResult,
    frame_snapshot_data_url,
)
from aegis.camera.types import CameraConfig, CameraConnectionStatus
from aegis.camera.utils import mask_url
from aegis.video.youtube_resolver import is_youtube_url, resolve_youtube_stream

logger = logging.getLogger(__name__)

# Target resolution cap — 720p balances quality and CPU cost.
_TARGET_HEIGHT = 720
# A connection test needs enough data to decode several frames, not an entire
# potentially multi-hour YouTube video.
_CONNECTION_TEST_CLIP_SECONDS = 5


def _find_ffmpeg() -> Optional[str]:
    """Locate an ffmpeg binary: system PATH first, then imageio-ffmpeg."""
    path = shutil.which("ffmpeg")
    if path:
        return path
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _find_node_exe() -> Optional[str]:
    """Locate Node.js executable — needed by new yt-dlp as JS runtime for YouTube."""
    return shutil.which("node")


def _find_ytdlp_exe() -> Optional[str]:
    """Locate the yt-dlp executable."""
    path = shutil.which("yt-dlp")
    if path:
        return path
    # Fallback: look in Python user scripts (pip install --user)
    try:
        import site
        user_base = site.getusersitepackages()
        if user_base:
            scripts_dir = os.path.join(os.path.dirname(user_base), "Scripts")
            candidate = os.path.join(scripts_dir, "yt-dlp.exe" if os.name == "nt" else "yt-dlp")
            if os.path.isfile(candidate):
                return candidate
    except Exception:
        pass
    return None


def _download_youtube(
    ytdlp_path: str,
    ffmpeg_path: Optional[str],
    url: str,
    output_path: str,
    *,
    max_duration_seconds: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Download a YouTube video to a local file using yt-dlp.

    Returns dict with metadata (title, height, fps, format_id).
    """
    cmd = [
        ytdlp_path,
        "--no-playlist",
        "--quiet", "--no-warnings",
        # Format selector: prefer h.264 dash (https protocol, video-only) ≤720p,
        # fallback to any video-containing format yt-dlp can find.
        "-f", (
            "bestvideo[height<=720][vcodec^=avc1][protocol=https]"
            "/bestvideo[height<=720][protocol=https][vcodec!=none]"
            "/bestvideo[height<=720][vcodec!=none]"
            "/best[vcodec!=none]"
        ),
        "--no-mtime",
        "-o", output_path,
        "--print-json",
    ]

    # Inject Node.js as JS runtime — required by yt-dlp >= 2026.09 for YouTube
    node_exe = _find_node_exe()
    if node_exe:
        cmd = [ytdlp_path, f"--js-runtimes=node:{node_exe}"] + cmd[1:]

    # --ffmpeg-location must receive the executable itself.  The bundled
    # imageio-ffmpeg binary has a versioned filename, so passing only its
    # directory makes yt-dlp search unsuccessfully for ffmpeg.exe.
    ffmpeg_dir = os.path.dirname(ffmpeg_path) if ffmpeg_path else None
    if ffmpeg_path:
        # Insert after the executable name so it is processed first
        cmd = [ytdlp_path] + cmd[1:2] + ["--ffmpeg-location", ffmpeg_path] + cmd[2:]

    if max_duration_seconds:
        cmd += ["--download-sections", f"*0:00-0:{int(max_duration_seconds)}"]
    cmd.append(url)

    logger.info("Downloading YouTube video url=%s output=%s", mask_url(url), output_path)

    # Ensure ffmpeg is findable by PATH in the child process
    env = os.environ.copy()
    if ffmpeg_dir and ffmpeg_dir not in env.get("PATH", ""):
        env["PATH"] = ffmpeg_dir + os.pathsep + env.get("PATH", "")

    result = subprocess.run(
        cmd,
        capture_output=True,
        timeout=120 if not max_duration_seconds else 60,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        env=env,
    )

    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace")[:500]
        raise RuntimeError(f"yt-dlp download failed (exit {result.returncode}): {stderr}")

    # Parse JSON metadata from stdout
    import json
    metadata = {}
    stdout_text = result.stdout.decode(errors="replace").strip()
    if stdout_text:
        try:
            # yt-dlp --print-json outputs one JSON object
            for line in stdout_text.splitlines():
                line = line.strip()
                if line.startswith("{"):
                    info = json.loads(line)
                    metadata = {
                        "title": info.get("title"),
                        "height": info.get("height"),
                        "fps": info.get("fps"),
                        "format_id": str(info.get("format_id", "")),
                        "duration": info.get("duration"),
                        "ext": info.get("ext"),
                        "vcodec": info.get("vcodec"),
                    }
                    break
        except (json.JSONDecodeError, KeyError):
            pass

    if not os.path.isfile(output_path):
        raise RuntimeError("yt-dlp completed but output file was not created")

    file_size = os.path.getsize(output_path)
    if file_size < 1000:
        raise RuntimeError(f"Downloaded file is too small ({file_size} bytes)")

    logger.info(
        "YouTube download complete title=%s height=%s fps=%s size=%s",
        metadata.get("title", "unknown"),
        metadata.get("height"),
        metadata.get("fps"),
        file_size,
    )
    return metadata


class YouTubeCameraSource(OpenCVLoopCameraSource):
    """
    Camera source that processes YouTube videos through the Aegis pipeline.

    Pipeline: yt-dlp downloads video to temp file → OpenCV reads frames
            → Aegis detection/tracking pipeline
    """

    def __init__(self, config: CameraConfig, **kwargs):
        # Initialize with a placeholder capture source; will be set after download
        super().__init__(config, capture_source="__youtube_pending__", finite=True, **kwargs)
        self._youtube_url = config.url
        self._temp_dir: Optional[str] = None
        self._temp_video_path: Optional[str] = None
        self._download_thread: Optional[threading.Thread] = None
        self._ffmpeg_path = _find_ffmpeg()
        self._ytdlp_path = _find_ytdlp_exe()
        self._yt_metadata: Dict[str, Any] = {}

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._set_status(CameraConnectionStatus.CONNECTING)
        # Download in a thread, then start the capture loop
        self._download_thread = threading.Thread(
            target=self._download_and_play, daemon=True,
            name=f"yt-download-{self.camera_id}",
        )
        self._download_thread.start()

    def stop(self) -> None:
        self._running = False
        self._release_capture()
        self._set_status(CameraConnectionStatus.STOPPED, "Stopped")
        if self._download_thread and self._download_thread.is_alive():
            self._download_thread.join(timeout=5.0)
        # Keep temp files until next start or deletion
        self._cleanup_temp()

    def _download_and_play(self) -> None:
        """Download YouTube video, then start OpenCV capture loop."""
        try:
            if not self._ytdlp_path:
                raise RuntimeError("yt-dlp not found")

            # Create temp directory for this camera
            self._temp_dir = tempfile.mkdtemp(prefix=f"aegis_yt_{self.camera_id}_")
            self._temp_video_path = os.path.join(self._temp_dir, "video.mp4")

            metadata = _download_youtube(
                self._ytdlp_path,
                self._ffmpeg_path,
                self._youtube_url,
                self._temp_video_path,
            )
            self._yt_metadata = metadata

            if not self._running:
                return

            # Update config metadata
            self.config.metadata = {
                **self.config.metadata,
                "source_resolver": "yt-dlp",
                "decoder": "opencv-file",
                "resolved_title": metadata.get("title"),
                "resolved_height": metadata.get("height"),
                "resolved_fps": metadata.get("fps"),
                "resolved_format_id": metadata.get("format_id"),
            }

            # Now set the capture source to the downloaded file and run the loop
            self._capture_source = self._temp_video_path
            self._capture_loop()

        except Exception as exc:
            if self._running:
                logger.error(
                    "YouTube download/playback failed camera_id=%s error=%s",
                    self.camera_id, exc,
                )
                self._set_status(
                    CameraConnectionStatus.ERROR,
                    f"YouTube video processing failed: {exc}",
                )
                self._running = False

    def _get_frame_interval(self, capture: Optional[cv2.VideoCapture]) -> Optional[float]:
        """Pace playback at original FPS."""
        fps = self._yt_metadata.get("fps")
        if fps:
            return self._fps_interval(float(fps))
        return self._capture_fps_interval(capture) or self._fps_interval(30.0)

    def test_connection(self) -> Tuple[bool, Optional[str]]:
        result = self.test_connection_details()
        return result.ok, result.error_message

    def test_connection_details(self) -> CameraConnectionTestResult:
        """
        Genuine connection test: resolve video, download a short clip, decode frames.
        Only succeeds if actual video frames are decoded end-to-end.
        """
        started_at = time.monotonic()

        # Check dependencies
        if not self._ytdlp_path:
            return CameraConnectionTestResult(
                ok=False, status="failed",
                error_category="missing_dependency",
                error_message="yt-dlp executable not found. Install: pip install yt-dlp",
                dns_resolved=True, host_reachable=True,
                masked_url=mask_url(self._youtube_url),
            )

        # Step 1: Download a short clip for testing
        temp_dir = None
        try:
            temp_dir = tempfile.mkdtemp(prefix="aegis_yt_test_")
            temp_path = os.path.join(temp_dir, "test_clip.mp4")

            metadata = _download_youtube(
                self._ytdlp_path,
                self._ffmpeg_path,
                self._youtube_url,
                temp_path,
                max_duration_seconds=_CONNECTION_TEST_CLIP_SECONDS,
            )
        except Exception as exc:
            if temp_dir and os.path.isdir(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
            error_msg = str(exc)
            # Only classify as private/unavailable if yt-dlp explicitly says so
            if any(kw in error_msg.lower() for kw in ["private", "unavailable", "members only", "sign in", "age-restricted"]):
                category = "youtube_private_or_unavailable"
                message = "This video is private, unavailable, or access-restricted."
            elif "importerror" in type(exc).__name__.lower() or "modulenotfounderror" in type(exc).__name__.lower():
                category = "missing_dependency"
                message = "yt-dlp is not installed. Run: pip install yt-dlp"
            else:
                category = "youtube_resolution_failed"
                message = f"Could not download YouTube video: {error_msg[:300]}"
            logger.warning("YouTube connection test download failed camera_id=%s error=%s", self.camera_id, error_msg[:200])
            return CameraConnectionTestResult(
                ok=False, status="failed",
                error_category=category,
                error_message=message,
                dns_resolved=True, host_reachable=True,
                masked_url=mask_url(self._youtube_url),
            )

        # Step 2: Open with OpenCV and read frames
        try:
            cap = cv2.VideoCapture(temp_path)
            if not cap.isOpened():
                return CameraConnectionTestResult(
                    ok=False, status="failed",
                    error_category="youtube_decode_failed",
                    error_message="Downloaded video could not be opened by the frame decoder.",
                    dns_resolved=True, host_reachable=True,
                    masked_url=mask_url(self._youtube_url),
                )

            frames_decoded = 0
            first_frame = None
            for _ in range(5):
                ok, frame = cap.read()
                if not ok or frame is None:
                    break
                frames_decoded += 1
                if first_frame is None:
                    first_frame = frame.copy()

            cap.release()

            if frames_decoded < 3:
                return CameraConnectionTestResult(
                    ok=False, status="failed",
                    error_category="youtube_decode_failed",
                    error_message=f"Video downloaded but only {frames_decoded} frames decoded.",
                    dns_resolved=True, host_reachable=True,
                    masked_url=mask_url(self._youtube_url),
                )

            height_val = first_frame.shape[0] if first_frame is not None else metadata.get("height")
            width_val = first_frame.shape[1] if first_frame is not None else None
            elapsed_ms = round((time.monotonic() - started_at) * 1000)

            # Store resolved metadata
            self._yt_metadata = metadata
            self.config.metadata = {
                **self.config.metadata,
                "source_resolver": "yt-dlp",
                "decoder": "opencv-file",
                "resolved_title": metadata.get("title"),
                "resolved_height": metadata.get("height"),
                "resolved_fps": metadata.get("fps"),
                "resolved_format_id": metadata.get("format_id"),
            }

            return CameraConnectionTestResult(
                ok=True, status="online",
                dns_resolved=True, host_reachable=True,
                time_to_first_frame_ms=elapsed_ms,
                width=width_val,
                height=height_val,
                masked_url=mask_url(self._youtube_url),
                snapshot_data_url=frame_snapshot_data_url(first_frame) if first_frame is not None else None,
            )
        finally:
            if temp_dir and os.path.isdir(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)

    def _cleanup_temp(self) -> None:
        """Remove temporary video files."""
        if self._temp_dir and os.path.isdir(self._temp_dir):
            try:
                shutil.rmtree(self._temp_dir, ignore_errors=True)
            except Exception:
                pass
            self._temp_dir = None
            self._temp_video_path = None
