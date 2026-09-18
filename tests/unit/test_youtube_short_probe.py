import numpy as np
from pathlib import Path
from types import SimpleNamespace

from aegis.camera import youtube_source
from aegis.camera.types import CameraConfig, CameraSourceType


class _FakeCapture:
    def __init__(self, *_args):
        self._frames_read = 0

    def isOpened(self):
        return True

    def read(self):
        self._frames_read += 1
        return True, np.zeros((8, 12, 3), dtype=np.uint8)

    def release(self):
        pass


def test_youtube_connection_test_downloads_only_a_short_probe(monkeypatch):
    source = youtube_source.YouTubeCameraSource(
        CameraConfig(
            camera_id="youtube-short-probe",
            source_type=CameraSourceType.HTTP_STREAM,
            url="https://www.youtube.com/watch?v=example",
        )
    )
    source._ytdlp_path = "yt-dlp"
    observed = {}

    def download_probe(*_args, **kwargs):
        observed["duration"] = kwargs.get("max_duration_seconds")
        return {"title": "Test video", "height": 720, "fps": 30}

    monkeypatch.setattr(youtube_source, "_download_youtube", download_probe)
    monkeypatch.setattr(youtube_source.cv2, "VideoCapture", _FakeCapture)

    result = source.test_connection_details()

    assert result.ok is True
    assert observed["duration"] == 5


def test_youtube_short_probe_passes_the_bundled_ffmpeg_binary_to_ytdlp(monkeypatch, tmp_path):
    output_path = tmp_path / "test_clip.mp4"
    ffmpeg_path = "C:/tools/ffmpeg-win-x86_64-v7.1.exe"
    observed = {}

    def fake_run(command, **_kwargs):
        observed["command"] = command
        output_path.write_bytes(b"x" * 1001)
        return SimpleNamespace(returncode=0, stdout=b"{}", stderr=b"")

    monkeypatch.setattr(youtube_source.subprocess, "run", fake_run)
    monkeypatch.setattr(youtube_source, "_find_node_exe", lambda: None)

    youtube_source._download_youtube(
        "yt-dlp",
        ffmpeg_path,
        "https://www.youtube.com/watch?v=example",
        str(output_path),
        max_duration_seconds=5,
    )

    command = observed["command"]
    assert command[command.index("--ffmpeg-location") + 1] == ffmpeg_path
