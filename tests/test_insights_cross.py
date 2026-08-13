from __future__ import annotations

import datetime

from app import database
from app.insights.cross_time import time_content_cross


def _at(hour: int) -> int:
    """今天该时刻的时间戳（保证跨测试可用任意整点）。"""
    now = datetime.datetime.now()
    return int(now.replace(hour=hour, minute=0, second=0, microsecond=0).timestamp())


def _seed_cross(conn, rows):
    for bvid, tname, hour in rows:
        conn.execute("INSERT INTO videos (bvid, title, tname) VALUES (?, 'T', ?)", (bvid, tname))
        conn.execute("INSERT INTO history (bvid, view_at, progress) VALUES (?, ?, 100)", (bvid, _at(hour)))


def test_cross_by_tname(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    _seed_cross(conn, [
        ("BV1", "科技", 3), ("BV2", "科技", 3), ("BV3", "游戏", 3),  # 凌晨：科技2 游戏1
        ("BV4", "科技", 20),                                          # 晚上：科技1
    ])
    conn.commit()
    conn.close()

    result = time_content_cross(database.get_conn(), dim="tname")
    li, ni = result["buckets"].index("凌晨(0-6)"), result["buckets"].index("晚上(18-24)")
    ci, gi = result["categories"].index("科技"), result["categories"].index("游戏")
    assert result["matrix"][li][ci] == 2
    assert result["matrix"][li][gi] == 1
    assert result["matrix"][ni][ci] == 1
    assert result["matrix"][ni][gi] == 0


def test_cross_by_category(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    _seed_cross(conn, [("BV1", "科技", 3), ("BV2", "游戏", 20)])
    conn.execute("INSERT INTO video_analysis (bvid, tags_json, summary, category) VALUES ('BV1', '[]', 's', '学习提升')")
    conn.execute("INSERT INTO video_analysis (bvid, tags_json, summary, category) VALUES ('BV2', '[]', 's', '娱乐消遣')")
    conn.commit()
    conn.close()

    result = time_content_cross(database.get_conn(), dim="category")
    assert "学习提升" in result["categories"]
    li = result["buckets"].index("凌晨(0-6)")
    assert result["matrix"][li][result["categories"].index("学习提升")] == 1


def test_cross_empty(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    result = time_content_cross(database.get_conn(), dim="tname")
    assert result["categories"] == []
