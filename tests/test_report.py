from __future__ import annotations

import json
import time

from app import database
from app.report import generate_report, report_to_html


def seed(conn):
    now = int(time.time())
    conn.execute("INSERT INTO videos (bvid, title, up_name, tname, duration) VALUES ('BV1', 'A', 'UP甲', '动画', 300)")
    conn.execute("INSERT INTO history (bvid, view_at, progress) VALUES ('BV1', ?, 50)", (now - 3600,))
    conn.execute("INSERT INTO videos (bvid, title, up_name, tname, duration) VALUES ('BV2', 'B', 'UP乙', '科技', 400)")
    conn.execute("INSERT INTO history (bvid, view_at, progress) VALUES ('BV2', ?, 20)", (now - 7200,))
    conn.commit()


def test_generate_weekly(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    seed(conn)

    result = generate_report(conn, "weekly")
    assert result["type"] == "weekly"
    assert result["stats"]["views"] == 2
    assert result["stats"]["top_ups"][0]["up_name"] == "UP甲"
    assert len(result["stats"]["tnames"]) == 2

    row = conn.execute("SELECT * FROM reports WHERE id=?", (result["id"],)).fetchone()
    assert json.loads(row["content_json"])["views"] == 2
    conn.close()


def test_report_to_html_contains_numbers():
    html = report_to_html({"views": 3, "top_ups": [], "tnames": [], "hours": []}, "2026-01-01~2026-01-07")
    assert "3" in html
    assert "观看报告" in html
