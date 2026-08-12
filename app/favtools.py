"""收藏夹管理工具（供 AI 助手调用）。"""
from __future__ import annotations

import json
import re

from app.bilibili.client import BiliClient
from app.bilibili.favorite import fetch_folder_items, fetch_folders
from app.config import get_cookies


def _client() -> BiliClient:
    return BiliClient(cookies=get_cookies())


def _uid(client: BiliClient) -> int:
    return client.get_json("/x/web-interface/nav")["data"]["mid"]


def list_folders() -> list[dict]:
    """列出所有收藏夹。"""
    with _client() as c:
        return fetch_folders(c, _uid(c))


def list_fav_items(media_id: int, limit: int = 20) -> list[dict]:
    """列出某收藏夹前 limit 个视频。"""
    with _client() as c:
        return fetch_folder_items(c, media_id)[:limit]


def create_folder(title: str) -> dict:
    """新建收藏夹，返回新夹信息。"""
    with _client() as c:
        return c.post_json("/x/v3/fav/folder/add", {"title": title})


def delete_folder(media_ids: str) -> dict:
    """删除收藏夹，media_ids 为逗号分隔。"""
    with _client() as c:
        return c.post_json("/x/v3/fav/folder/del", {"media_ids": str(media_ids)})


def move_fav_items(src_media_id: int, tar_media_id: int, bvids: list[str]) -> dict:
    """把一批视频从 src_media_id 移动到 tar_media_id。"""
    resources = json.dumps([{"id": b, "type": 2} for b in bvids], ensure_ascii=False)
    with _client() as c:
        return c.post_json("/x/v3/fav/resource/move", {
            "src_media_id": src_media_id,
            "tar_media_id": tar_media_id,
            "resources": resources,
        })


def extract_bvid(link: str) -> str:
    """从 B 站链接或纯 BV 号中提取 bvid。"""
    m = re.search(r"(BV[0-9A-Za-z]{10})", link or "")
    if not m:
        raise ValueError(f"无法从「{link}」中识别视频链接")
    return m.group(1)


def analyze_video(link: str) -> dict:
    """分析一个 B 站视频链接，返回标题/UP主/简介/分区/播放量等。"""
    bvid = extract_bvid(link)
    with _client() as c:
        data = c.get_json("/x/web-interface/view", {"bvid": bvid})
        d = data.get("data") or {}
        owner = d.get("owner") or {}
        stat = d.get("stat") or {}
        return {
            "bvid": bvid,
            "title": d.get("title", ""),
            "up": owner.get("name", ""),
            "tname": d.get("tname", ""),
            "desc": (d.get("desc") or "")[:300],
            "duration": d.get("duration", 0),
            "view_count": stat.get("view", 0),
            "danmaku": stat.get("danmaku", 0),
            "pic": d.get("pic", ""),
        }
