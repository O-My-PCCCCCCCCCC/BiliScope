"""收藏夹采集。"""
from __future__ import annotations

from app.bilibili.client import BiliClient


def fetch_folders(client: BiliClient, up_mid: int) -> list[dict]:
    data = client.get_json(
        "/x/v3/fav/folder/created/list-all", {"up_mid": up_mid}
    )
    folders = data.get("data", {}).get("list") or []
    return [
        {
            "media_id": fl["id"],
            "name": fl.get("title", ""),
            "count": fl.get("media_count", 0),
            "created_at": fl.get("ctime") or 0,
        }
        for fl in folders
    ]


def fetch_folder_items(client: BiliClient, media_id: int, max_pages: int = 100) -> list[dict]:
    result: list[dict] = []
    for pn in range(1, max_pages + 1):
        data = client.get_json(
            "/x/v3/fav/resource/list",
            {"media_id": media_id, "pn": pn, "ps": 20},
        )
        medias = data.get("data", {}).get("medias") or []
        if not medias:
            break
        for m in medias:
            upper = m.get("upper") or {}
            cnt = m.get("cnt_info") or {}
            result.append({
                "media_id": media_id,
                "bvid": m.get("bvid", ""),
                "title": m.get("title", ""),
                "up_mid": upper.get("mid", 0),
                "up_name": upper.get("name", ""),
                "fav_time": m.get("fav_time", 0),
                "duration": m.get("duration", 0),
                "pic": m.get("cover", ""),
                "tname": m.get("tname", ""),
                "view_count": cnt.get("play", 0),
                "danmaku": cnt.get("danmaku", 0),
            })
        if len(medias) < 20:
            break
    return result
