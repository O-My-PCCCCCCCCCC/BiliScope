from __future__ import annotations

from app import config


def test_load_default_config(tmp_path):
    config.set_config_path(tmp_path / "nope.json")
    cfg = config.load_config()
    assert cfg["cookies"] == {}
    assert "smtp" in cfg


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    config.set_config_path(path)
    config.save_config({"cookies": {"SESSDATA": "abc"}})
    cfg = config.load_config()
    assert cfg["cookies"]["SESSDATA"] == "abc"


def test_save_cookies(tmp_path):
    config.set_config_path(tmp_path / "config.json")
    config.save_cookies({"SESSDATA": "xyz"})
    cfg = config.load_config()
    assert cfg["cookies"]["SESSDATA"] == "xyz"
    assert isinstance(cfg["login_at"], int)
