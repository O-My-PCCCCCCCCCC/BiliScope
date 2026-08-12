from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolated_config_and_db(tmp_path, monkeypatch):
    """每个测试隔离 config.json 与 SQLite 路径。"""
    from app import config as config_mod
    from app import database as database_mod
    config_mod.set_config_path(tmp_path / "config.json")
    database_mod.set_db_path(tmp_path / "test.db")
    yield
