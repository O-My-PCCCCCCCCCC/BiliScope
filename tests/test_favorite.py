from __future__ import annotations

import httpx

from app.bilibili.client import BiliClient
from app.bilibili import favorite as f


def make_client(handler) -> BiliClient:
    return BiliClient(session=httpx.Client(transport=httpx.MockTransport(handler)))


def test_fetch_folders():
    def handler(request):
        return httpx.Response(200, json={
            "code": 0,
            "data": {"list": [
                {"id": 101, "title": "动画", "media_count": 12, "ctime": 1700000000},
                {"id": 102, "title": "科技", "media_count": 5, "ctime": 1700000100},
            ]},
        })

    folders = f.fetch_folders(make_client(handler))
    assert folders == [
        {"media_id": 101, "name": "动画", "count": 12, "created_at": 1700000000},
        {"media_id": 102, "name": "科技", "count": 5, "created_at": 1700000100},
    ]


def test_fetch_folder_items_single_page():
    def handler(request):
        return httpx.Response(200, json={
            "code": 0,
            "data": {"medias": [
                {"bvid": "BV1", "title": "视频一", "fav_time": 1600000000,
                 "upper": {"mid": 1, "name": "UP甲"}, "duration": 300,
                 "cover": "http://x/a.jpg", "tname": "动画"},
                {"bvid": "BV2", "title": "视频二", "fav_time": 1600000001,
                 "upper": {"mid": 2, "name": "UP乙"}, "duration": 400,
                 "cover": "http://x/b.jpg", "tname": "科技"},
            ]},
        })

    items = f.fetch_folder_items(make_client(handler), 101)
    assert len(items) == 2
    assert items[0]["bvid"] == "BV1"
    assert items[0]["media_id"] == 101
    assert items[0]["up_name"] == "UP甲"


def test_fetch_folder_items_paginates_until_short_page():
    pages = iter([
        {"code": 0, "data": {"medias": [{"bvid": f"BV{i}", "upper": {}, "fav_time": 1} for i in range(20)]}},
        {"code": 0, "data": {"medias": []}},
    ])

    def handler(request):
        return httpx.Response(200, json=next(pages))

    items = f.fetch_folder_items(make_client(handler), 101, max_pages=100)
    assert len(items) == 20
