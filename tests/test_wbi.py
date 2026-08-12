from __future__ import annotations

import httpx

from app.bilibili import wbi
from app.bilibili.client import BiliClient


def make_client(handler) -> BiliClient:
    return BiliClient(session=httpx.Client(transport=httpx.MockTransport(handler)))


def test_mixin_key():
    img_key = "7cd084941338484aae1ad9425b84077c"
    sub_key = "4932caff0ff746eab6f01bf08b70ac45"
    mixin = wbi.get_mixin_key(img_key, sub_key)
    assert len(mixin) == 32
    assert mixin == "ea1db124af3c7062474693fa704f4ff8"


def test_sign_wbi_adds_wts_and_w_rid(monkeypatch):
    import time as _time
    monkeypatch.setattr(_time, "time", lambda: 1700000000)

    def handler(request):
        return httpx.Response(200, json={"code": 0, "data": {
            "wbi_img": {
                "img_url": "https://i0.hdslb.com/bfs/wbi/7cd084941338484aae1ad9425b84077c.png",
                "sub_url": "https://i0.hdslb.com/bfs/wbi/4932caff0ff746eab6f01bf08b70ac45.png",
            },
        }})

    client = make_client(handler)
    signed = wbi.sign_wbi(client, {"mid": 123})
    assert signed["mid"] == 123
    assert signed["wts"] == 1700000000
    assert "w_rid" in signed
    assert len(signed["w_rid"]) == 32


def test_get_wbi_json_signs_request():
    captured = {}

    def handler(request):
        if "/x/space/wbi/arc/search" in request.url.path:
            captured["query"] = str(request.url.query)
            return httpx.Response(200, json={"code": 0, "data": {"list": {"vlist": []}}})
        return httpx.Response(200, json={"code": 0, "data": {
            "wbi_img": {
                "img_url": "https://i0.hdslb.com/bfs/wbi/7cd084941338484aae1ad9425b84077c.png",
                "sub_url": "https://i0.hdslb.com/bfs/wbi/4932caff0ff746eab6f01bf08b70ac45.png",
            },
        }})

    client = make_client(handler)
    client.get_wbi_json("/x/space/wbi/arc/search", {"mid": 1})
    assert "w_rid=" in captured["query"]
    assert "wts=" in captured["query"]
