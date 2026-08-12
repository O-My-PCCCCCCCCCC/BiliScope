from __future__ import annotations

import httpx

from app.bilibili import login
from app.config import load_config


def make_login(handler) -> login.QRLogin:
    return login.QRLogin(session=httpx.Client(transport=httpx.MockTransport(handler)))


def test_generate_returns_url_and_key():
    def handler(request):
        return httpx.Response(200, json={
            "code": 0,
            "data": {"url": "https://passport.bilibili.com/h5/login?key=K", "qrcode_key": "K"},
        })

    result = make_login(handler).generate()
    assert result["qrcode_key"] == "K"
    assert "passport.bilibili.com" in result["url"]


def test_generate_raises_on_error():
    def handler(request):
        return httpx.Response(200, json={"code": -400, "message": "请求太频繁"})

    import pytest
    with pytest.raises(RuntimeError, match="请求太频繁"):
        make_login(handler).generate()


def test_poll_success_saves_cookies(tmp_path):
    from app import config
    config.set_config_path(tmp_path / "config.json")

    def handler(request):
        return httpx.Response(200, json={"code": 0, "data": {"url": "https://www.bilibili.com/"}},
                              headers=[
                                  ("set-cookie", "SESSDATA=abc; Path=/"),
                                  ("set-cookie", "bili_jct=def; Path=/"),
                              ])

    result = make_login(handler).poll("K")
    assert result["status"] == "ok"
    cookies = load_config()["cookies"]
    assert cookies["SESSDATA"] == "abc"
    assert cookies["bili_jct"] == "def"


def test_poll_expired():
    def handler(request):
        return httpx.Response(200, json={"code": 86038, "data": None})

    assert make_login(handler).poll("K")["status"] == "expired"


def test_poll_pending_and_scanned():
    pending = make_login(lambda r: httpx.Response(200, json={"code": 86101, "data": None}))
    assert pending.poll("K")["status"] == "pending"

    scanned = make_login(lambda r: httpx.Response(200, json={"code": 86090, "data": None}))
    assert scanned.poll("K")["status"] == "scanned"
