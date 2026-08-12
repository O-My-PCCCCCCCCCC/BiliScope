"""B 站 API 客户端：统一封装请求、Cookie、登录态检测。"""
from __future__ import annotations

import httpx

BASE_URL = "https://api.bilibili.com"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class BiliError(Exception):
    """B 站接口返回非 0 code 或请求异常。"""

    def __init__(self, message: str, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


class BiliClient:
    def __init__(self, cookies: dict | None = None,
                 session: httpx.Client | None = None) -> None:
        self.session = session or httpx.Client(
            base_url=BASE_URL,
            timeout=15.0,
            headers={"User-Agent": UA, "Referer": "https://www.bilibili.com/"},
        )
        if not str(self.session.base_url):
            self.session.base_url = BASE_URL
        if cookies:
            self.session.cookies.update(cookies)

    def get_json(self, path: str, params: dict | None = None) -> dict:
        resp = self.session.get(path, params=params)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") not in (0, None):
            raise BiliError(
                f"{path} 返回错误: code={data.get('code')} {data.get('message', '')}",
                code=data.get("code"),
            )
        return data

    def is_logged_in(self) -> bool:
        data = self.get_json("/x/web-interface/nav")
        return bool(data.get("data", {}).get("isLogin"))

    def get_wbi_json(self, path: str, params: dict | None = None) -> dict:
        from app.bilibili import wbi
        signed = wbi.sign_wbi(self, params or {})
        return self.get_json(path, signed)

    def post_json(self, path: str, data: dict | None = None) -> dict:
        """POST 表单请求，自动附加 bili_jct CSRF。"""
        data = dict(data or {})
        jct = self.session.cookies.get("bili_jct")
        if jct and "csrf" not in data:
            data["csrf"] = jct
        resp = self.session.post(path, data=data)
        resp.raise_for_status()
        body = resp.json()
        if body.get("code") not in (0, None):
            raise BiliError(
                f"{path} 返回错误: code={body.get('code')} {body.get('message', '')}",
                code=body.get("code"),
            )
        return body

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> "BiliClient":
        return self

    def __exit__(self, *args) -> None:
        self.close()
