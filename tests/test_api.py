from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app import config, database
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_state(tmp_path):
    config.set_config_path(tmp_path / "config.json")
    database.set_db_path(tmp_path / "api.db")
    database.init_db()


def test_ping():
    assert client.get("/api/ping").json() == {"ok": True}


def test_status_not_logged_in():
    r = client.get("/api/status")
    assert r.status_code == 200
    body = r.json()
    assert body["logged_in"] is False
    assert body["counts"]["history"] == 0


def test_status_logged_in_with_counts():
    conn = database.get_conn()
    conn.execute("INSERT INTO videos (bvid, title) VALUES ('BV1', 'T')")
    conn.execute("INSERT INTO history (bvid, view_at, progress) VALUES ('BV1', 100, 10)")
    conn.execute("INSERT INTO fav_folders (media_id, name) VALUES (101, '动画')")
    conn.execute("INSERT INTO fav_items (media_id, bvid) VALUES (101, 'BV1')")
    conn.execute("INSERT INTO followings (mid, uname) VALUES (1, 'U')")
    conn.commit()
    conn.close()
    config.save_cookies({"SESSDATA": "abc"})

    body = client.get("/api/status").json()
    assert body["logged_in"] is True
    assert body["counts"]["history"] == 1
    assert body["counts"]["favorites"] == 1
    assert body["counts"]["folders"] == 1
    assert body["counts"]["followings"] == 1


def test_history_search():
    conn = database.get_conn()
    conn.execute("INSERT INTO videos (bvid, title, up_name, tname, duration) VALUES ('BV1', 'Python 教程', 'UP甲', '科技', 300)")
    conn.execute("INSERT INTO videos (bvid, title, up_name, tname, duration) VALUES ('BV2', '美食探店', 'UP乙', '美食', 400)")
    conn.execute("INSERT INTO history (bvid, view_at, progress) VALUES ('BV1', 200, 50)")
    conn.execute("INSERT INTO history (bvid, view_at, progress) VALUES ('BV2', 100, 20)")
    conn.commit()
    conn.close()

    r = client.get("/api/history", params={"search": "Python", "page": 1, "page_size": 10})
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Python 教程"


def test_sync_returns_401_when_not_logged_in():
    r = client.post("/api/sync")
    assert r.status_code == 401


def test_overview_stats():
    conn = database.get_conn()
    now = int(time.time())
    conn.execute("INSERT INTO videos (bvid, title, up_name, tname, duration) VALUES ('BV1', 'T', 'UP甲', '动画', 300)")
    conn.execute("INSERT INTO history (bvid, view_at, progress) VALUES ('BV1', ?, 50)", (now - 86400,))
    conn.commit()
    conn.close()

    body = client.get("/api/stats/overview").json()
    assert body["counts"]["history"] == 1
    assert body["top_ups"][0]["up_name"] == "UP甲"
    assert body["tnames"][0]["tname"] == "动画"
    assert len(body["trend"]) == 1
