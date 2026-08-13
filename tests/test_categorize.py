from __future__ import annotations

from app import database
from app.categorize import categorize_by_tname, reclassify_others


def test_categorize_by_tname():
    assert categorize_by_tname("音乐") == "娱乐消遣"
    assert categorize_by_tname("游戏") == "娱乐消遣"
    assert categorize_by_tname("日常") == "娱乐消遣"
    assert categorize_by_tname("知识") == "学习提升"
    assert categorize_by_tname("科技") == "学习提升"
    assert categorize_by_tname("资讯") == "资讯"
    assert categorize_by_tname("美食") == "生活实用"
    assert categorize_by_tname("旅行") == "生活实用"
    assert categorize_by_tname("随便啥") == "其他"
    assert categorize_by_tname("") == "其他"


def test_reclassify_others(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    conn.execute("INSERT INTO videos (bvid, title, tname) VALUES ('BV1', 'A', '音乐')")
    conn.execute("INSERT INTO videos (bvid, title, tname) VALUES ('BV2', 'B', '未知分区')")
    conn.execute("INSERT INTO video_analysis (bvid, tags_json, summary, category) VALUES ('BV1', '[]', 's', '其他')")
    conn.execute("INSERT INTO video_analysis (bvid, tags_json, summary, category) VALUES ('BV2', '[]', 's', '其他')")
    conn.commit()

    n = reclassify_others(conn)
    assert n == 1  # BV1 音乐 → 娱乐消遣；BV2 未知分区 保持其他
    cat1 = conn.execute("SELECT category FROM video_analysis WHERE bvid='BV1'").fetchone()[0]
    cat2 = conn.execute("SELECT category FROM video_analysis WHERE bvid='BV2'").fetchone()[0]
    assert cat1 == "娱乐消遣"
    assert cat2 == "其他"
    # 幂等：再次运行不重复更新
    assert reclassify_others(conn) == 0
    conn.close()
