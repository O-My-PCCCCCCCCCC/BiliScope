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
    assert client.post("/api/monitor/run").status_code == 401


def test_run_starts_background(monkeypatch):
    import app.api as api_mod
    config.save_cookies({"SESSDATA": "abc"})
    monkeypatch.setattr(api_mod, "start_monitor", lambda scope="all": {"ok": True})

    r = client.post("/api/monitor/run")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert "state" in client.get("/api/monitor/status").json()


def test_invalid_and_updates_lists():
    conn = database.get_conn()
    conn.execute("INSERT INTO invalid_items (bvid, source, checked_at) VALUES ('BV1', 'check', 100)")
    conn.execute("INSERT INTO followings (mid, uname) VALUES (1, 'UP甲')")
    conn.execute("INSERT INTO updates (mid, last_bvid, last_pubdate, checked_at) VALUES (1, 'BVX', 50, 60)")
    conn.commit()
    conn.close()

    invalid = client.get("/api/monitor/invalid").json()
    assert len(invalid) == 1 and invalid[0]["bvid"] == "BV1"

    updates = client.get("/api/monitor/updates").json()
    assert len(updates) == 1 and updates[0]["uname"] == "UP甲"


def test_clean_invalid_requires_login():
    assert client.post("/api/monitor/clean-invalid").status_code == 401
