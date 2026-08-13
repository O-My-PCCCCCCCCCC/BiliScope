from __future__ import annotations

from app import database
from app.analyze import aggregate_themes, analysis_stats, analyze_unanalyzed
from app.llm.base import VideoTags


class FakeLLM:
    def analyze_video(self, title, desc):
        return VideoTags(tags=["科技"], summary=f"关于{title}")


def test_sync_descriptions(tmp_path):
    from app.sync import sync_descriptions

    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    conn.execute("INSERT INTO videos (bvid, title) VALUES ('BV1', 'A')")
    conn.commit()

    class FakeClient:
        def get_json(self, path, params=None):
            return {"code": 0, "data": {"desc": "这是简介"}}

    n = sync_descriptions(conn, FakeClient(), limit=10)
    assert n == 1
    assert conn.execute("SELECT desc FROM videos WHERE bvid='BV1'").fetchone()[0] == "这是简介"
    conn.close()


def test_analyze_unanalyzed(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    conn.execute("INSERT INTO videos (bvid, title, desc) VALUES ('BV1', 'A', '简介1')")
    conn.execute("INSERT INTO videos (bvid, title, desc) VALUES ('BV2', 'B', '简介2')")
    conn.commit()

    n = analyze_unanalyzed(conn, FakeLLM(), limit=10)
    assert n == 2
    assert conn.execute("SELECT COUNT(*) FROM video_analysis").fetchone()[0] == 2

    n2 = analyze_unanalyzed(conn, FakeLLM(), limit=10)
    assert n2 == 0

    stats = analysis_stats(conn)
    assert stats["analyzed"] == 2 and stats["total"] == 2
    conn.close()


def test_aggregate_themes(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    conn.execute("INSERT INTO video_analysis (bvid, tags_json, summary) VALUES ('BV1', '[\"科技\",\"AI\"]', 'a')")
    conn.execute("INSERT INTO video_analysis (bvid, tags_json, summary) VALUES ('BV2', '[\"科技\",\"游戏\"]', 'b')")
    conn.commit()

    themes = aggregate_themes(conn)
    by_tag = {t["tag"]: t["n"] for t in themes}
    assert by_tag["科技"] == 2
    assert by_tag["AI"] == 1
    conn.close()


def test_graveyard_stats(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    # 3 个收藏：BV1 看过、BV2 没看过、BV3 没看过 → 吃灰 2/3 = 66.7%
    for bvid in ("BV1", "BV2", "BV3"):
        conn.execute("INSERT INTO fav_items (media_id, bvid) VALUES (101, ?)", (bvid,))
    conn.execute("INSERT INTO history (bvid, view_at) VALUES ('BV1', 1)")
    conn.commit()

    stats = __import__("app.analyze", fromlist=["graveyard_stats"]).graveyard_stats(conn)
    assert stats["total"] == 3
    assert stats["graveyard"] == 2
    assert stats["pct"] == 66.7
    conn.close()


def test_graveyard_stats_empty(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    stats = __import__("app.analyze", fromlist=["graveyard_stats"]).graveyard_stats(conn)
    assert stats == {"graveyard": 0, "total": 0, "pct": 0}
    conn.close()


def test_analyze_unanalyzed_reports_progress(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    conn.execute("INSERT INTO videos (bvid, title, desc) VALUES ('BV1', 'A', '简介1')")
    conn.execute("INSERT INTO videos (bvid, title, desc) VALUES ('BV2', 'B', '简介2')")
    conn.commit()

    progress = {}
    n = analyze_unanalyzed(conn, FakeLLM(), limit=10, progress=progress)
    assert n == 2
    assert progress["total"] == 2
    assert progress["progress"] >= 0
    assert "分析" in progress["message"]
    conn.close()


def test_start_analysis_background_flow(monkeypatch):
    import time

    import app.analyze as analyze_mod
    import app.config as cfg
    import app.database as db
    import app.llm as llm

    monkeypatch.setattr(analyze_mod, "analyze_unanalyzed",
                        lambda conn, llm_client, limit=50, force=False, progress=None: 3)

    class FakeConn:
        def close(self):
            pass

    monkeypatch.setattr(db, "get_conn", lambda: FakeConn())
    monkeypatch.setattr(db, "init_db", lambda conn: None)
    monkeypatch.setattr(llm, "get_llm_client", lambda c: object())
    monkeypatch.setattr(cfg, "load_config", lambda: {"llm": {"provider": "x"}})

    assert analyze_mod.start_analysis() == {"ok": True}
    st = {}
    for _ in range(100):
        st = analyze_mod.analysis_status()
        if st["state"] in ("done", "error"):
            break
        time.sleep(0.05)
    assert st["state"] == "done"
    assert st["result"] == {"analyzed": 3}
