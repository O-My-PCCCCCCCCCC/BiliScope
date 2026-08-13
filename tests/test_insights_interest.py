from __future__ import annotations

import time

from app import database
from app.insights.interest import interest_drift


def _seed(conn):
    conn.execute("INSERT INTO videos (bvid, title) VALUES ('BV1', 'A')")
    conn.execute("INSERT INTO videos (bvid, title) VALUES ('BV2', 'B')")


def test_interest_drift_basic(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    now = int(time.time())
    _seed(conn)
    conn.execute("INSERT INTO history (bvid, view_at, progress) VALUES ('BV1', ?, 100)", (now,))
    conn.execute("INSERT INTO history (bvid, view_at, progress) VALUES ('BV2', ?, 100)", (now - 40 * 86400,))
    conn.execute("INSERT INTO video_analysis (bvid, tags_json, summary) VALUES ('BV1', '[\"科技\",\"AI\"]', 's')")
    conn.execute("INSERT INTO video_analysis (bvid, tags_json, summary) VALUES ('BV2', '[\"游戏\"]', 's')")
    conn.commit()
    conn.close()

    result = interest_drift(database.get_conn(), months=3)
    this_m = time.strftime("%Y-%m", time.localtime(now))
    last_m = time.strftime("%Y-%m", time.localtime(now - 40 * 86400))
    by_tag = {s["tag"]: dict(zip(result["months"], s["data"])) for s in result["series"]}
    assert by_tag["科技"][this_m] == 1
    assert by_tag["AI"][this_m] == 1
    assert by_tag["游戏"][last_m] == 1


def test_interest_drift_topn_and_other(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    now = int(time.time())
    _seed(conn)
    conn.execute("INSERT INTO history (bvid, view_at, progress) VALUES ('BV1', ?, 100)", (now,))
    conn.execute("INSERT INTO video_analysis (bvid, tags_json, summary) VALUES ('BV1', '[\"A\",\"B\",\"C\"]', 's')")
    conn.commit()
    conn.close()

    result = interest_drift(database.get_conn(), months=3, top_n=2)
    tags = [s["tag"] for s in result["series"]]
    assert "其他" in tags
    assert len(tags) == 3  # TOP2 + 其他
    this_m = time.strftime("%Y-%m", time.localtime(now))
    by_tag = {s["tag"]: dict(zip(result["months"], s["data"])) for s in result["series"]}
    assert by_tag["其他"][this_m] == 1


def test_interest_drift_empty(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    result = interest_drift(database.get_conn(), months=3)
    assert result["series"] == []
    assert len(result["months"]) == 3


def test_interest_drift_ignores_non_list_tags(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    now = int(time.time())
    conn.execute("INSERT INTO videos (bvid, title) VALUES ('BV1', 'A')")
    conn.execute("INSERT INTO history (bvid, view_at, progress) VALUES ('BV1', ?, 100)", (now,))
    conn.execute("INSERT INTO video_analysis (bvid, tags_json, summary) VALUES ('BV1', '{\"a\": 1}', 's')")  # 合法 JSON 但非数组
    conn.commit()
    conn.close()
    result = interest_drift(database.get_conn(), months=3)
    assert result["series"] == []  # 脏行被跳过，不崩溃
