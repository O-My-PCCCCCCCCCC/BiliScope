from __future__ import annotations

import pathlib
import tempfile

from fastapi.testclient import TestClient

from app import config, database
from app.main import app
from app.notify import add_alert


def test_add_alert(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    add_alert(conn, "invalid", "视频失效", "BV1 检测为失效")
    conn.commit()
    row = conn.execute("SELECT * FROM alerts").fetchone()
    assert row["type"] == "invalid"
    assert row["title"] == "视频失效"
    assert row["read"] == 0
    conn.close()


def test_list_alerts_and_unread_count():
    tmp = pathlib.Path(tempfile.mkdtemp())
    config.set_config_path(tmp / "config.json")
    database.set_db_path(tmp / "t.db")
    database.init_db()

    conn = database.get_conn()
    add_alert(conn, "invalid", "A", "x")
    add_alert(conn, "update", "B", "y")
    conn.commit()
    conn.execute("UPDATE alerts SET read=1 WHERE title='A'")
    conn.commit()
    conn.close()

    client = TestClient(app)
    body = client.get("/api/alerts").json()
    assert body["unread"] == 1
    assert len(body["items"]) == 2

    r = client.post(f"/api/alerts/{body['items'][0]['id']}/read")
    assert r.json() == {"ok": True}
    assert client.get("/api/alerts").json()["unread"] == 1  # 只剩 B 未读

    body = client.get("/api/status").json()
    assert body["alerts_unread"] == 1
