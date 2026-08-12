from __future__ import annotations

from app import database


def test_init_db_creates_tables(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"videos", "history", "fav_folders", "fav_items", "coins",
                "followings", "updates", "invalid_items", "reports", "alerts"} <= tables
    finally:
        conn.close()


def test_insert_and_query_video(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    try:
        conn.execute(
            "INSERT INTO videos (bvid, title, up_mid, up_name) VALUES (?, ?, ?, ?)",
            ("BV1", "测试视频", 1001, "阿测"),
        )
        conn.commit()
        row = conn.execute("SELECT title, up_name FROM videos WHERE bvid='BV1'").fetchone()
        assert dict(row) == {"title": "测试视频", "up_name": "阿测"}
    finally:
        conn.close()


def test_history_unique_constraint(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    try:
        conn.execute("INSERT OR IGNORE INTO history (bvid, view_at, progress) VALUES ('BV1', 100, 50)")
        conn.execute("INSERT OR IGNORE INTO history (bvid, view_at, progress) VALUES ('BV1', 100, 50)")
        conn.commit()
        n = conn.execute("SELECT COUNT(*) FROM history").fetchone()[0]
        assert n == 1
    finally:
        conn.close()
