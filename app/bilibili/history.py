"""观看历史采集。"""
from __future__ import annotations

from app.bilibili.client import BiliClient


def normalize_history_item(item: dict) -> dict:
    owner = item.get("owner") or {}
    stat = item.get("stat") or {}
    return {
        "bvid": item["bvid"],
        "title": item.get("title", ""),
        "up_mid": owner.get("mid", 0),
        "up_name": owner.get("name", ""),
        "view_at": item.get("view_at", 0),
        "progress": item.get("progress", 0),
        "duration": item.get("duration", 0),
        "pic": item.get("pic", ""),
        "tname": item.get("tname", ""),
        "ctime": item.get("ctime", 0),
        "view_count": stat.get("view", 0),
        "danmaku": stat.get("danmaku", 0),
    }


def fetch_history(client: BiliClient, max_pages: int = 20) -> list[dict]:
    """分页拉取观看历史（新版接口 data 直接为列表，按 pn 分页）。"""
    result: list[dict] = []
    for pn in range(1, max_pages + 1):
        data = client.get_json("/x/v2/history", {"pn": pn, "ps": 100})
        items = data.get("data") or []
        if not items:
            break
        result.extend(normalize_history_item(i) for i in items)
        if len(items) < 100:
            break
    return result
