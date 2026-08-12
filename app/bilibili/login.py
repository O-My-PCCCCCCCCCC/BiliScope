"""扫码登录：生成二维码、轮询扫码结果、保存 Cookie。"""
from __future__ import annotations

import httpx

from app.bilibili.client import UA
from app.config import save_cookies

QR_GENERATE_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
QR_POLL_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"


class QRLogin:
    def __init__(self, session: httpx.Client | None = None) -> None:
        self.session = session or httpx.Client(
            timeout=15.0,
            headers={"User-Agent": UA, "Referer": "https://www.bilibili.com/"},
        )

    def generate(self) -> dict:
        resp = self.session.get(QR_GENERATE_URL)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"生成二维码失败: {data.get('message', data)}")
        return data["data"]

    def poll(self, qrcode_key: str) -> dict:
        resp = self.session.get(QR_POLL_URL, params={"qrcode_key": qrcode_key})
        resp.raise_for_status()
        data = resp.json()
        code = data.get("code")
        if code == 0:
            cookies = {k: v for k, v in self.session.cookies.items()}
            save_cookies(cookies)
            return {"status": "ok", "message": "登录成功"}
        if code == 86038:
            return {"status": "expired", "message": "二维码已失效，请刷新"}
        if code == 86090:
            return {"status": "scanned", "message": "已扫码，请在手机确认"}
        if code == 86101:
            return {"status": "pending", "message": "等待扫码"}
        return {"status": "pending", "message": f"未知状态 code={code}"}
