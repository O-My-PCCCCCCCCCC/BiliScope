from __future__ import annotations

import httpx

from app import database, dynamics
from app.bilibili.client import BiliClient


def make_client(handler) -> BiliClient:
    return BiliClient(session=httpx.Client(transport=httpx.MockTransport(handler)))


def item(id_str, ctime, like=3, comment=1, repost=0, text="内容"):
    return {
        "id_str": id_str, "type": "DYNAMIC_TYPE_AV",
        "modules": {
            "module_stat": {
                "like": {"count": like}, "comment": {"count": comment},
                "forward": {"count": repost},
            },
            "module_dynamic": {"desc": {"text": text}},
            "module_author": {"pub_ts": ctime},
        },
    }


def test_normalize():
    n = dynamics.normalize(item("123", 1700000000))
    assert n["id"] == "123"
    assert n["type"] == "AV"
    assert n["like_count"] == 3
    assert n["comment_count"] == 1
    assert n["repost_count"] == 0
    assert n["ctime"] == 1700000000


def test_fetch_paginates():
    pages = iter([
        {"code": 0, "data": {"items": [item("1", 100)], "offset": "abc", "has_more": True}},
        {"code": 0, "data": {"items": [item("2", 99)], "offset": "", "has_more": False}},
    ])
    offsets = []

    def handler(request):
        offsets.append(request.url.params.get("offset"))
        return httpx.Response(200, json=next(pages))

    rows = dynamics.fetch_dynamics(make_client(handler), 123, max_pages=3)
    assert len(rows) == 2
    assert offsets == [None, "abc"]


def test_sync_dynamics(tmp_path):
    from app.sync import sync_dynamics

    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()

    class FakeClient:
        def get_json(self, path, params=None):
            return {"code": 0, "data": {"items": [item("1", 100)], "offset": ""}}

    n = sync_dynamics(conn, FakeClient(), 123)  # type: ignore
    assert n == 1
    n = sync_dynamics(conn, FakeClient(), 123)  # type: ignore
    assert n == 0  # 去重
    assert conn.execute("SELECT COUNT(*) FROM dynamics").fetchone()[0] == 1
    conn.close()
