from __future__ import annotations

import time

from app import database
from app.insights.time_invest import time_invest


def test_time_invest(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    now = int(time.time())
    conn.execute("INSERT INTO videos (bvid, title, up_name, tname, duration) VALUES ('BV1','A','UP甲','科技',3000)")
    conn.execute("INSERT INTO videos (bvid, title, up_name, tname, duration) VALUES ('BV2','B','UP甲','科技',1000)")
    conn.execute("INSERT INTO videos (bvid, title, up_name, tname, duration) VALUES ('BV3','C','UP乙','游戏',500)")
    conn.execute("INSERT INTO history (bvid, view_at, progress) VALUES ('BV1', ?, 3000)", (now,))
    conn.execute("INSERT INTO history (bvid, view_at, progress) VALUES ('BV2', ?, 0)", (now,))  # progress 0 → duration 兜底
    conn.execute("INSERT INTO history (bvid, view_at, progress) VALUES ('BV3', ?, 200)", (now,))
    conn.execute("INSERT INTO video_analysis (bvid, tags_json, summary, category) VALUES ('BV1','[\"AI\"]','s','学习提升')")
    conn.commit()
    conn.close()

    result = time_invest(database.get_conn())
    by_up = {r["name"]: r["seconds"] for r in result["by_up"]}
    assert by_up["UP甲"] == 4000      # BV1 progress 3000 + BV2 duration 兜底 1000
    assert by_up["UP乙"] == 200
    by_cat = {r["name"]: r["seconds"] for r in result["by_category"]}
    assert by_cat["学习提升"] == 3000
    assert by_cat["其他"] == 1200     # BV2(1000) + BV3(200) 无 category
    by_tag = {r["name"]: r["seconds"] for r in result["by_tag"]}
    assert by_tag["AI"] == 3000


def test_time_invest_ignores_non_list_tags(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    now = int(time.time())
    conn.execute("INSERT INTO videos (bvid, title, up_name, duration) VALUES ('BV1','A','UP甲',100)")
    conn.execute("INSERT INTO history (bvid, view_at, progress) VALUES ('BV1', ?, 100)", (now,))
    conn.execute("INSERT INTO video_analysis (bvid, tags_json, summary, category) VALUES ('BV1', '123', 's', '学习提升')")  # JSON 数字
    conn.commit()
    conn.close()
    result = time_invest(database.get_conn())
    assert {r["name"] for r in result["by_category"]} == {"学习提升"}
    assert result["by_tag"] == []  # 非数组 tags 不产生标签，不崩溃
