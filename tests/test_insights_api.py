from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app import database
from app.main import app

client = TestClient(app)


def _seed(conn):
    conn.execute("INSERT INTO videos (bvid, title, tname) VALUES ('BV1', 'A', '科技')")
    conn.execute("INSERT INTO history (bvid, view_at, progress) VALUES ('BV1', ?, 100)", (int(time.time()),))
    conn.execute("INSERT INTO video_analysis (bvid, tags_json, summary, category) VALUES ('BV1', '[\"科技\"]', 's', '学习提升')")


def test_insights_endpoints(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    _seed(conn)
    conn.commit()
    conn.close()

    assert client.get("/api/insights/invest").status_code == 200
    assert client.get("/api/insights/interest").status_code == 200
    body = client.get("/api/insights/cross").json()
    assert "matrix" in body and body["categories"] == ["科技"]
    # 非法 dim 报 400
    assert client.get("/api/insights/cross", params={"dim": "xxx"}).status_code == 400
