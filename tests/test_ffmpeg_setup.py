from __future__ import annotations

from app.ffmpeg_setup import ensure_ffmpeg


def test_uses_path_ffmpeg(monkeypatch):
    monkeypatch.setattr("app.ffmpeg_setup.shutil.which", lambda name: "C:/ffmpeg/bin/ffmpeg.exe")
    assert ensure_ffmpeg() == "C:/ffmpeg/bin/ffmpeg.exe"


def test_uses_imageio_when_no_path(monkeypatch):
    monkeypatch.setattr("app.ffmpeg_setup.shutil.which", lambda name: None)
    monkeypatch.setattr("app.ffmpeg_setup.sys", type("S", (), {"frozen": False})())
    import app.ffmpeg_setup as f
    monkeypatch.setattr(f, "imageio_ffmpeg", _fake_imageio())
    assert ensure_ffmpeg() == "C:/site/ffmpeg.exe"


def _fake_imageio():
    return type("I", (), {"get_ffmpeg_exe": staticmethod(lambda: "C:/site/ffmpeg.exe")})()


def test_frozen_missing_path_falls_to_imageio(monkeypatch):
    monkeypatch.setattr("app.ffmpeg_setup.shutil.which", lambda name: None)
    # frozen 但 _MEIPASS/ffmpeg.exe 不存在 → 回落到 imageio
    fake_path = type("P", (), {"exists": lambda self: False, "__truediv__": lambda self, o: self})()
    monkeypatch.setattr("app.ffmpeg_setup.Path", lambda *a, **k: fake_path)
    monkeypatch.setattr("app.ffmpeg_setup.sys", type("S", (), {"frozen": True, "_MEIPASS": "C:/bundle"})())
    import app.ffmpeg_setup as f
    monkeypatch.setattr(f, "imageio_ffmpeg", _fake_imageio())
    assert ensure_ffmpeg() == "C:/site/ffmpeg.exe"


def test_none_when_all_missing(monkeypatch):
    monkeypatch.setattr("app.ffmpeg_setup.shutil.which", lambda name: None)
    monkeypatch.setattr("app.ffmpeg_setup.sys", type("S", (), {"frozen": False})())
    import app.ffmpeg_setup as f
    monkeypatch.setattr(f, "imageio_ffmpeg", None)
    assert ensure_ffmpeg() is None
