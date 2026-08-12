"""端到端：mock 的 B 站接口 → 同步 → 查询全链路。"""
from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app import config, database
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated(tmp_path):
    config.set_config_path(tmp_path / "config.json")
    database.set_db_path(tmp_path / "int.db")
    database.init_db()


def make_sync_client():
    """一个完整的 mock B 站客户端，覆盖同步所需全部接口。"""
    responses = {
        "/x/web-interface/nav": {"code": 0, "data": {"isLogin": True, "mid": 123}},
        "/x/v2/history": {"code": 0, "data": [
            {"bvid": "BV1", "title": "历史一", "owner": {"mid": 1, "name": "UP甲"},
             "view_at": 100, "progress": 50, "duration": 300, "pic": "", "tname": "动画", "ctime": 1},
        ]},
        "/x/v3/fav/folder/created/list-all": {"code": 0, "data": {"list": [
            {"id": 101, "title": "动画", "media_count": 1, "ctime": 1},
        ]}},
        "/x/v3/fav/resource/list": {"code": 0, "data": {"medias": [
            {"bvid": "BV2", "title": "收藏一", "fav_time": 2,
             "upper": {"mid": 2, "name": "UP乙"}, "duration": 400, "cover": "", "tname": "科技"},
        ]}},
        "/x/relation/followings": {"code": 0, "data": {"list": [
            {"mid": 1, "uname": "UP甲", "face": ""},
        ]}},
    }

    def handler(request):
        return httpx.Response(200, json=responses.get(request.url.path, {"code": 0, "data": {}}))

    from app.bilibili.client import BiliClient
    return BiliClient(session=httpx.Client(transport=httpx.MockTransport(handler)))


def test_full_flow(tmp_path, monkeypatch):
    import app.api as api_mod
    config.save_cookies({"SESSDATA": "abc"})
    # 接口层持有的 run_full_sync 引用需要直接替换
    monkeypatch.setattr(api_mod, "run_full_sync", lambda client=None: {
        "history": 1, "favorites": 1, "followings": 1,
    })

    # 通过 API 触发同步
    r = client.post("/api/sync")
    assert r.status_code == 200
    assert r.json() == {"history": 1, "favorites": 1, "followings": 1}


def test_database_seeded_from_client():
    from app import sync
    conn = database.get_conn()
    n_h = sync.sync_history(conn, make_sync_client())
    n_f = sync.sync_favorites(conn, make_sync_client(), uid=123)
    assert n_h == 1 and n_f == 1
    conn.commit()
    conn.close()

    body = client.get("/api/status").json()
    assert body["counts"]["history"] == 1
    assert body["counts"]["favorites"] == 1


def test_monitor_chain(tmp_path, monkeypatch):
    import app.api as api_mod
    config.save_cookies({"SESSDATA": "abc"})
    monkeypatch.setattr(api_mod, "check_invalid", lambda conn, client, **kw: 1)
    monkeypatch.setattr(api_mod, "check_updates", lambda conn, client, **kw: 0)

    r = client.post("/api/monitor/run")
    assert r.status_code == 200
    assert r.json() == {"invalid": 1, "updates": 0}

    # 写入一条提醒并确认未读数暴露到 status
    from app.notify import add_alert
    conn = database.get_conn()
    add_alert(conn, "invalid", "失效", "BV1")
    conn.commit()
    conn.close()
    assert client.get("/api/status").json()["alerts_unread"] == 1


def test_report_chain():
    from app.report import generate_report
    conn = database.get_conn()
    result = generate_report(conn, "weekly")
    conn.close()

    items = client.get("/api/reports").json()
    assert len(items) == 1
    detail = client.get(f"/api/reports/{result['id']}").json()
    assert detail["type"] == "weekly"


def test_analysis_chain(monkeypatch):
    import app.api as api_mod
    config.save_cookies({"SESSDATA": "abc"})
    config.save_config({**config.load_config(),
                        "llm": {"provider": "ollama", "api_key": "", "base_url": "", "model": "qwen2.5:7b"}})
    monkeypatch.setattr(api_mod, "analyze_unanalyzed", lambda conn, llm_client, limit=50: 2)

    r = client.post("/api/analysis/run", params={"limit": 10})
    assert r.status_code == 200
    assert r.json() == {"analyzed": 2}

    hw = client.get("/api/hardware").json()
    assert "recommended_model" in hw
