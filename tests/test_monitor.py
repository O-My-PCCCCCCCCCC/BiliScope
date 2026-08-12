from __future__ import annotations

import httpx

from app import database
from app.bilibili.client import BiliClient
from app.monitor import check_invalid


def make_client(handler) -> BiliClient:
    return BiliClient(session=httpx.Client(transport=httpx.MockTransport(handler)))


def test_checks_invalid_videos(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    conn.execute("INSERT INTO videos (bvid, title) VALUES ('BV1', 'A')")
    conn.execute("INSERT INTO history (bvid, view_at) VALUES ('BV1', 100)")
    conn.execute("INSERT INTO videos (bvid, title) VALUES ('BV2', 'B')")
    conn.execute("INSERT INTO history (bvid, view_at) VALUES ('BV2', 200)")
    conn.commit()

    def handler(request):
        if request.url.params.get("bvid") == "BV1":
            return httpx.Response(200, json={"code": -404, "message": "啥都木有"})
        return httpx.Response(200, json={"code": 0, "data": {}})

    n = check_invalid(conn, make_client(handler), limit=10, delay=0)
    assert n == 1
    assert conn.execute("SELECT COUNT(*) FROM invalid_items").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM alerts WHERE type='invalid'").fetchone()[0] == 1

    # 第二次运行不重复记录
    n2 = check_invalid(conn, make_client(handler), limit=10, delay=0)
    assert n2 == 0
    conn.close()


def test_skips_when_no_videos(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    assert check_invalid(conn, make_client(lambda r: httpx.Response(200, json={"code": 0})), limit=10) == 0
    conn.close()
