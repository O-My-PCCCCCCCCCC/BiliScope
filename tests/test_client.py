from __future__ import annotations

import httpx
import pytest

from app.bilibili.client import BiliClient, BiliError, UA


def make_client(handler) -> BiliClient:
    return BiliClient(session=httpx.Client(transport=httpx.MockTransport(handler)))


def test_get_json_ok():
    def handler(request):
        return httpx.Response(200, json={"code": 0, "data": {"x": 1}})

    client = make_client(handler)
    assert client.get_json("/x/web-interface/nav")["data"] == {"x": 1}


def test_get_json_raises_on_error_code():
    def handler(request):
        return httpx.Response(200, json={"code": -101, "message": "账号未登录"})

    client = make_client(handler)
    with pytest.raises(BiliError, match="账号未登录"):
        client.get_json("/x/v2/history")


def test_is_logged_in_true():
    def handler(request):
        return httpx.Response(200, json={"code": 0, "data": {"isLogin": True}})

    assert make_client(handler).is_logged_in() is True


def test_is_logged_in_false():
    def handler(request):
        return httpx.Response(200, json={"code": 0, "data": {"isLogin": False}})

    assert make_client(handler).is_logged_in() is False


def test_cookies_attached():
    captured = {}

    def handler(request):
        captured["cookie"] = request.headers.get("cookie", "")
        return httpx.Response(200, json={"code": 0, "data": {}})

    make_client({"SESSDATA": "abc123"}).get_json("/x/web-interface/nav")
    assert "SESSDATA=abc123" in captured["cookie"]
    assert "bilibili" in UA
