from __future__ import annotations

import pytest

from app import database
from app.bilibili.client import BiliError
from app import sync
from app import config


def hist_item(bvid, view_at):
    return {"bvid": bvid, "title": f"T-{bvid}", "owner": {"mid": 1, "name": "UP甲"},
            "view_at": view_at, "progress": 10, "duration": 100, "pic": "", "tname": "动画", "ctime": 1}


def test_sync_history_and_dedup(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()

    class FakeClient:
        def get_json(self, path, params=None):
            if path == "/x/v2/history":
                return {"code": 0, "data": [hist_item("BV1", 100), hist_item("BV2", 99)]}
            raise AssertionError(f"unexpected path {path}")

    n = sync.sync_history(conn, FakeClient())  # type: ignore
    assert n == 2
    n = sync.sync_history(conn, FakeClient())  # type: ignore
    assert n == 0  # 幂等：不重复插入
    assert conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM history").fetchone()[0] == 2
    conn.close()


def test_sync_favorites_and_followings(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()

    class FakeClient:
        def get_json(self, path, params=None):
            if path == "/x/v3/fav/folder/created/list-all":
                return {"code": 0, "data": {"list": [{"id": 101, "title": "动画", "media_count": 1, "ctime": 1}]}}
            if path == "/x/v3/fav/resource/list":
                return {"code": 0, "data": {"medias": [{
                    "bvid": "BV9", "title": "F-BV9", "fav_time": 1,
                    "upper": {"mid": 2, "name": "UP乙"}, "duration": 100, "cover": "", "tname": ""}]}}
            if path == "/x/relation/followings":
                return {"code": 0, "data": {"list": [{"mid": 1, "uname": "U1", "face": ""},
                                                     {"mid": 2, "uname": "U2", "face": ""}]}}
            raise AssertionError(f"unexpected path {path}")

    client = FakeClient()  # type: ignore
    n_fav = sync.sync_favorites(conn, client)
    n_fol = sync.sync_followings(conn, client, uid=123)
    assert n_fav == 1
    assert n_fol == 2
    assert conn.execute("SELECT COUNT(*) FROM fav_items").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM followings").fetchone()[0] == 2
    conn.close()


def test_run_full_sync_requires_login(tmp_path, monkeypatch):
    config.set_config_path(tmp_path / "config.json")
    monkeypatch.setattr(config, "get_cookies", lambda: {})
    with pytest.raises(BiliError, match="未登录"):
        sync.run_full_sync()
