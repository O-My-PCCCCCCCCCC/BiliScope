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

    client = BiliClient(
        cookies={"SESSDATA": "abc123"},
        session=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    client.get_json("/x/web-interface/nav")
    assert "SESSDATA=abc123" in captured["cookie"]
    assert "Chrome" in UA


def test_get_json_retries_on_500(monkeypatch):
    calls = {"n": 0}
    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(500, json={"code": -1})
        return httpx.Response(200, json={"code": 0, "data": {"ok": True}})
    monkeypatch.setattr("app.bilibili.client._backoff", lambda attempt: None)
    client = make_client(handler)
    assert client.get_json("/x/web-interface/nav")["data"]["ok"] is True
    assert calls["n"] == 2


def test_get_json_retries_on_risk_control_412(monkeypatch):
    calls = {"n": 0}
    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(200, json={"code": -412, "message": "风控"})
        return httpx.Response(200, json={"code": 0, "data": {"ok": True}})
    monkeypatch.setattr("app.bilibili.client._backoff", lambda attempt: None)
    client = make_client(handler)
    assert client.get_json("/x/web-interface/nav")["data"]["ok"] is True
    assert calls["n"] == 3


def test_get_json_does_not_retry_404(monkeypatch):
    calls = {"n": 0}
    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json={"code": -404, "message": "不存在"})
    monkeypatch.setattr("app.bilibili.client._backoff", lambda attempt: None)
    client = make_client(handler)
    with pytest.raises(BiliError):
        client.get_json("/x/web-interface/view")
    assert calls["n"] == 1  # -404 不重试


def test_get_json_retries_on_non_json_html(monkeypatch):
    calls = {"n": 0}
    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(200, text="<html>反爬页</html>")
        return httpx.Response(200, json={"code": 0, "data": {"ok": True}})
    monkeypatch.setattr("app.bilibili.client._backoff", lambda attempt: None)
    client = make_client(handler)
    assert client.get_json("/x/web-interface/nav")["data"]["ok"] is True
    assert calls["n"] == 2
