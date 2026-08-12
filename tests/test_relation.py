from __future__ import annotations

import httpx

from app.bilibili.client import BiliClient
from app.bilibili import relation as r


def make_client(handler) -> BiliClient:
    return BiliClient(session=httpx.Client(transport=httpx.MockTransport(handler)))


def test_fetch_followings_single_page():
    def handler(request):
        return httpx.Response(200, json={
            "code": 0,
            "data": {"list": [
                {"mid": 1, "uname": "UP甲", "face": "http://x/1.jpg"},
                {"mid": 2, "uname": "UP乙", "face": "http://x/2.jpg"},
            ]},
        })

    rows = r.fetch_followings(make_client(handler), 123)
    assert len(rows) == 2
    assert rows[0] == {"mid": 1, "uname": "UP甲", "face": "http://x/1.jpg"}


def test_fetch_followings_paginates_until_short_page():
    pages = iter([
        {"code": 0, "data": {"list": [{"mid": i, "uname": f"U{i}", "face": ""} for i in range(50)]}},
        {"code": 0, "data": {"list": [{"mid": 100, "uname": "U100", "face": ""}]}},
        {"code": 0, "data": {"list": []}},
    ])
    pns = []

    def handler(request):
        pns.append(request.url.params.get("pn"))
        return httpx.Response(200, json=next(pages))

    rows = r.fetch_followings(make_client(handler), 123)
    assert len(rows) == 51
    assert pns == ["1", "2"]
