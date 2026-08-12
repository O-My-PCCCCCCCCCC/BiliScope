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
    monkeypatch.setattr(api_mod, "analyze_unanalyzed", lambda conn, llm_client, limit=50: 3)

    r = client.post("/api/analysis/run", params={"limit": 10})
    assert r.status_code == 200
    assert r.json() == {"analyzed": 3}


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
