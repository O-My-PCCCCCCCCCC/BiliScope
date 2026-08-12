"""动态采集：拉取自己的动态（点赞/评论/转发数）。"""
from __future__ import annotations

from app.bilibili.client import BiliClient


def normalize(item: dict) -> dict:
    mods = item.get("modules") or {}
    stat = mods.get("module_stat") or {}

    def cnt(x) -> int:
        return (x or {}).get("count", 0) or 0

    desc = (mods.get("module_dynamic") or {}).get("desc") or {}
    author = mods.get("module_author") or {}
    return {
        "id": item.get("id_str", ""),
        "type": (item.get("type") or "").replace("DYNAMIC_TYPE_", ""),
        "content": (desc.get("text") or "")[:200],
        "like_count": cnt(stat.get("like")),
        "comment_count": cnt(stat.get("comment")),
        "repost_count": cnt(stat.get("forward")),
        "ctime": author.get("pub_ts", 0),
    }


def fetch_dynamics(client: BiliClient, uid: int, max_pages: int = 5) -> list[dict]:
    result: list[dict] = []
    offset = None
    for _ in range(max_pages):
        params = {"host_mid": uid, "timezone_offset": -480, "features": "itemOpusStyle"}
        if offset:
            params["offset"] = offset
        data = client.get_json("/x/polymer/web-dynamic/v1/feed/space", params)
        items = (data.get("data") or {}).get("items") or []
        if not items:
            break
        result.extend(normalize(i) for i in items)
        offset = (data.get("data") or {}).get("offset")
        if not offset:
            break
    return result
