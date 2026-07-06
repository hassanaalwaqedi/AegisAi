from aegis.video import camera_sources
from aegis.video.camera_sources import CameraConfig, CameraSourceType, HTTPCameraSource
from aegis.video.youtube_resolver import ResolvedYouTubeStream, is_youtube_url


class _FakeCapture:
    def set(self, *_args):
        return True


def test_youtube_url_detection_accepts_watch_and_share_links():
    assert is_youtube_url("https://www.youtube.com/watch?v=BAw342Xqxhs&t=1326s")
    assert is_youtube_url("https://youtu.be/BAw342Xqxhs")
    assert not is_youtube_url("https://example.com/video.mjpg")


def test_http_camera_source_resolves_youtube_before_opening_opencv(monkeypatch):
    opened_sources = []
    resolved_urls = []

    def fake_resolve(raw_url):
        resolved_urls.append(raw_url)
        return ResolvedYouTubeStream(
            source_url=raw_url,
            stream_url="https://rr.example.com/direct-video.mp4",
            title="Street camera sample",
            format_id="18",
            height=360,
            fps=30,
        )

    def fake_video_capture(source, *_args):
        opened_sources.append(source)
        return _FakeCapture()

    monkeypatch.setattr(camera_sources, "resolve_youtube_stream", fake_resolve)
    monkeypatch.setattr(camera_sources.cv2, "VideoCapture", fake_video_capture)

    config = CameraConfig(
        camera_id="youtube-stream",
        source_type=CameraSourceType.HTTP_STREAM,
        url="https://www.youtube.com/watch?v=BAw342Xqxhs&t=1326s",
    )
    source = HTTPCameraSource(config)

    source._open_capture()

    assert resolved_urls == ["https://www.youtube.com/watch?v=BAw342Xqxhs&t=1326s"]
    assert opened_sources == ["https://rr.example.com/direct-video.mp4"]
    assert source.config.metadata["source_resolver"] == "yt-dlp"
    assert source.config.metadata["source_page_url"] == config.url
    assert source.config.metadata["resolved_format_id"] == "18"
