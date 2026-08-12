"""观看历史采集。"""
from __future__ import annotations

from app.bilibili.client import BiliClient


def normalize_history_item(item: dict) -> dict:
    return {
        "bvid": item["bvid"],
        "title": item.get("title", ""),
        "up_mid": item.get("author_mid", 0),
        "up_name": item.get("author_name", ""),
        "view_at": item.get("view_at", 0),
        "progress": item.get("progress", 0),
        "duration": item.get("duration", 0),
        "pic": item.get("pic", ""),
        "tname": item.get("tname", ""),
        "ctime": item.get("ctime", 0),
    }


def fetch_history(client: BiliClient, max_pages: int = 20) -> list[dict]:
    """分页拉取观看历史，返回规范化记录（按时间倒序）。"""
    result: list[dict] = []
    cursor = None
    for _ in range(max_pages):
        params: dict = {"pn": 1, "ps": 100}
        if cursor:
            params["max_id"] = cursor
        data = client.get_json("/x/v2/history", params)
        items = data.get("data", {}).get("list") or []
        if not items:
            break
        result.extend(normalize_history_item(i) for i in items)
        cursor = data.get("data", {}).get("max_id")
        if not cursor:
            break
    return result
