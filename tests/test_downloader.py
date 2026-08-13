from __future__ import annotations

from app import config, database
from app.downloader import _run, download_status, out_dir


def test_out_dir_default(tmp_path):
    config.set_config_path(tmp_path / "config.json")
    assert out_dir().name == "downloads"


def test_out_dir_custom(tmp_path):
    config.set_config_path(tmp_path / "config.json")
    config.save_config({**config.load_config(), "download_dir": str(tmp_path / "my_dl")})
    assert str(out_dir()) == str(tmp_path / "my_dl")
    assert out_dir().exists()


def test_status_includes_out_dir(tmp_path):
    config.set_config_path(tmp_path / "config.json")
    assert "out_dir" in download_status()


def test_run_sets_ffmpeg_location(monkeypatch, tmp_path):
    config.set_config_path(tmp_path / "config.json")
    captured = {}

    class FakeYD:
        def __init__(self, opts):
            captured["opts"] = opts
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def download(self, urls):
            captured["downloaded"] = urls

    monkeypatch.setattr("app.downloader.yt_dlp", type("Y", (), {"YoutubeDL": FakeYD})())
    monkeypatch.setattr("app.downloader.ensure_ffmpeg", lambda: "C:/ffmpeg.exe")
    monkeypatch.setattr("app.downloader._write_cookies", lambda: "c.txt")
    monkeypatch.setattr("app.downloader._download_status", {})

    _run(["https://www.bilibili.com/video/BV1xx"], "mp4")
    assert captured["opts"]["ffmpeg_location"] == "C:/ffmpeg.exe"
    assert captured["opts"]["format"] == "bv*+ba/b"
    assert "FFmpegExtractAudio" not in str(captured["opts"])


def test_run_audio_uses_mp3_with_ffmpeg(monkeypatch, tmp_path):
    config.set_config_path(tmp_path / "config.json")
    captured = {}

    class FakeYD:
        def __init__(self, opts):
            captured["opts"] = opts
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def download(self, urls):
            pass

    monkeypatch.setattr("app.downloader.yt_dlp", type("Y", (), {"YoutubeDL": FakeYD})())
    monkeypatch.setattr("app.downloader.ensure_ffmpeg", lambda: "C:/ffmpeg.exe")
    monkeypatch.setattr("app.downloader._write_cookies", lambda: "c.txt")
    monkeypatch.setattr("app.downloader._download_status", {})

    _run(["https://www.bilibili.com/video/BV1xx"], "audio")
    assert captured["opts"]["ffmpeg_location"] == "C:/ffmpeg.exe"
    assert captured["opts"]["postprocessors"] == [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}]


def test_run_audio_no_ffmpeg_downloads_m4a(monkeypatch, tmp_path):
    config.set_config_path(tmp_path / "config.json")
    captured = {}

    class FakeYD:
        def __init__(self, opts):
            captured["opts"] = opts
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def download(self, urls):
            pass

    monkeypatch.setattr("app.downloader.yt_dlp", type("Y", (), {"YoutubeDL": FakeYD})())
    monkeypatch.setattr("app.downloader.ensure_ffmpeg", lambda: None)
    monkeypatch.setattr("app.downloader._write_cookies", lambda: "c.txt")
    monkeypatch.setattr("app.downloader._download_status", {})

    _run(["https://www.bilibili.com/video/BV1xx"], "audio")
    assert "ffmpeg_location" not in captured["opts"]
    assert captured["opts"]["postprocessors"] == []


def test_normalize_urls():
    from app.downloader import normalize_urls
    assert normalize_urls(["BV1ZagB6cEM6"]) == ["https://www.bilibili.com/video/BV1ZagB6cEM6"]
    assert normalize_urls(["https://www.bilibili.com/video/BV1xx"]) == ["https://www.bilibili.com/video/BV1xx"]
    assert normalize_urls(["", "  "]) == []
