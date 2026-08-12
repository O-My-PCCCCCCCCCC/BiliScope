"""收藏夹管理工具（供 AI 助手调用）。"""
from __future__ import annotations

import json

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
