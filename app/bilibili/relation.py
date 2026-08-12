"""关注列表采集。"""
from __future__ import annotations

from app.bilibili.client import BiliClient


def fetch_followings(client: BiliClient, vmid: int, max_pages: int = 100) -> list[dict]:
    result: list[dict] = []
    for pn in range(1, max_pages + 1):
        data = client.get_json(
            "/x/relation/followings",
            {"vmid": vmid, "pn": pn, "ps": 50, "order": "desc"},
        )
        items = data.get("data", {}).get("list") or []
        if not items:
            break
        result.extend({
            "mid": it.get("mid", 0),
            "uname": it.get("uname", ""),
            "face": it.get("face", ""),
        } for it in items)
        if len(items) < 50:
            break
    return result
