from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import config, database
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean(tmp_path):
    config.set_config_path(tmp_path / "config.json")
    database.set_db_path(tmp_path / "t.db")
    database.init_db()


def test_run_requires_login():
    assert client.post("/api/analysis/run").status_code == 401


def test_run_and_themes(monkeypatch):
    import app.api as api_mod
    config.save_cookies({"SESSDATA": "abc"})
    config.save_config({**config.load_config(),
                        "llm": {"provider": "ollama", "api_key": "", "base_url": "", "model": "qwen2.5:7b"}})
    monkeypatch.setattr(api_mod, "start_analysis", lambda limit=50, force=False: {"ok": True})
    monkeypatch.setattr(api_mod, "analysis_status_fn",
                        lambda: {"state": "done", "result": {"analyzed": 3},
                                 "progress": 100, "message": "分析完成：3 条", "total": 0, "current": ""})

    r = client.post("/api/analysis/run", params={"limit": 10})
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert client.get("/api/analysis/run-status").json()["state"] == "done"


def test_analysis_status_and_themes():
    conn = database.get_conn()
    conn.execute("INSERT INTO video_analysis (bvid, tags_json, summary) VALUES ('BV1', '[\"科技\"]', 'a')")
    conn.commit()
    conn.close()

    assert client.get("/api/analysis/status").json()["analyzed"] == 1
    themes = client.get("/api/analysis/themes").json()
    assert themes[0]["tag"] == "科技"


def test_hardware_endpoint():
    body = client.get("/api/hardware").json()
    assert "recommended_model" in body
    assert "ram_gb" in body


def test_graveyard_stats_endpoint():
    conn = database.get_conn()
    conn.execute("INSERT INTO fav_items (media_id, bvid) VALUES (101, 'BV1')")
    conn.execute("INSERT INTO fav_items (media_id, bvid) VALUES (101, 'BV2')")
    conn.commit()
    conn.close()

    body = client.get("/api/analysis/graveyard-stats").json()
    assert body == {"graveyard": 2, "total": 2, "pct": 100.0}
