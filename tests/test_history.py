from __future__ import annotations

import httpx

from app.bilibili.client import BiliClient
from app.bilibili import history as h


def make_client(handler) -> BiliClient:
    return BiliClient(session=httpx.Client(transport=httpx.MockTransport(handler)))


def item(bvid, view_at, **kw):
    base = {
        "bvid": bvid, "title": "标题", "author_mid": 1001, "author_name": "阿测",
        "view_at": view_at, "progress": 30, "duration": 600,
        "pic": "http://x/pic.jpg", "tname": "生活", "ctime": 1700000000,
    }
    base.update(kw)
    return base


def test_normalize_history_item():
    it = item("BV1", 1234567890)
    n = h.normalize_history_item(it)
    assert n["bvid"] == "BV1"
    assert n["up_name"] == "阿测"
    assert n["tname"] == "生活"


def test_fetch_history_single_page():
    pages = iter([{
        "code": 0,
        "data": {"list": [item("BV1", 100), item("BV2", 99)], "max_id": None},
    }])

    def handler(request):
        return httpx.Response(200, json=next(pages))

    rows = h.fetch_history(make_client(handler))
    assert len(rows) == 2
    assert rows[0]["bvid"] == "BV1"


def test_fetch_history_paginates_until_empty():
    responses = [
        {"code": 0, "data": {"list": [item("BV1", 100)], "max_id": 50}},
        {"code": 0, "data": {"list": [item("BV2", 99)], "max_id": 25}},
        {"code": 0, "data": {"list": [], "max_id": None}},
    ]
    requested_max_ids = []

    def handler(request):
        requested_max_ids.append(request.url.params.get("max_id"))
        return httpx.Response(200, json=responses.pop(0))

    rows = h.fetch_history(make_client(handler))
    assert len(rows) == 2
    assert requested_max_ids == [None, "50", "25"]
