from __future__ import annotations

import time

from app import database
from app.insights.watching import night_owl_stats, repeat_watches, streak_stats


def _at(hour: int, day_offset: int = 0) -> int:
    """今天(或偏移 N 天)该时刻的时间戳。"""
    from datetime import datetime, timedelta
    now = datetime.now()
    dt = (now + timedelta(days=day_offset)).replace(hour=hour, minute=0, second=0, microsecond=0)
    return int(dt.timestamp())


def _seed(conn, rows):
    for bvid, hour, offset in rows:
        conn.execute("INSERT OR IGNORE INTO videos (bvid, title, up_name, duration) VALUES (?, 'T', 'UP', 100)", (bvid,))
        conn.execute("INSERT INTO history (bvid, view_at, progress) VALUES (?, ?, 50)", (bvid, _at(hour, offset)))


def test_repeat_watches(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    _seed(conn, [("BV1", 10, 0), ("BV1", 10, -1), ("BV1", 10, -2), ("BV2", 10, 0)])
    conn.commit()
    conn.close()

    result = repeat_watches(database.get_conn(), limit=5)
    assert len(result) == 1
    assert result[0]["bvid"] == "BV1"
    assert result[0]["views"] == 3
    assert result[0]["total_sec"] == 150  # 3 × progress 50
    conn = database.get_conn()
    conn.close()


def test_streak_stats(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    # 连续 3 天（今天、昨天、前天），今天看两次
    _seed(conn, [("BV1", 10, 0), ("BV2", 10, 0), ("BV3", 10, -1), ("BV4", 10, -2)])
    conn.commit()
    conn.close()

    result = streak_stats(database.get_conn(), days=30)
    assert result["active_days"] == 3
    assert result["longest_streak"] == 3
    assert result["calendar"]
    conn = database.get_conn()
    conn.close()


def test_night_owl_stats(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    # 4 条：3 条凌晨(3时) + 1 条白天(15时) → 深夜占比 75%
    _seed(conn, [("BV1", 3, 0), ("BV2", 3, 0), ("BV3", 3, 0), ("BV4", 15, 0)])
    conn.commit()
    conn.close()

    result = night_owl_stats(database.get_conn())
    assert result["night_ratio"] == 75.0
    assert result["night_level"] == "重度夜猫"
    conn = database.get_conn()
    conn.close()
