from __future__ import annotations

import time

from app import database
from app.insights.ai_report import generate_ai_report


class FakeLLM:
    text = ('{"narrative": "你是个深夜音乐重度用户，喜欢在安静时反复刷喜欢的作品。", '
            '"findings": [{"title": "吃灰率高", "detail": "76.7% 收藏从没看过，建议清理"}]}')

    def chat(self, messages, tools=None):
        class R:
            text = FakeLLM.text
        return R()


def _seed(conn):
    conn.execute("INSERT INTO videos (bvid, title, up_name, duration) VALUES ('BV1', 'A', 'UP甲', 100)")
    conn.execute("INSERT INTO history (bvid, view_at, progress) VALUES ('BV1', ?, 50)", (int(time.time()),))
    conn.execute("INSERT INTO video_analysis (bvid, tags_json, summary, category) VALUES ('BV1', '[\"音乐\"]', 's', '娱乐消遣')")


def test_generate_ai_report(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    _seed(conn)
    conn.commit()
    conn.close()

    result = generate_ai_report(database.get_conn(), FakeLLM())
    assert "深夜音乐重度用户" in result["narrative"]
    assert result["findings"][0]["title"] == "吃灰率高"


def test_generate_ai_report_empty_db(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    result = generate_ai_report(database.get_conn(), FakeLLM())
    assert result["narrative"]


def test_generate_ai_report_non_json_fallback(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()

    class PlainLLM:
        def chat(self, messages, tools=None):
            class R:
                text = "一段没有 JSON 的普通文字回复。"
            return R()

    result = generate_ai_report(database.get_conn(), PlainLLM())
    assert result["narrative"] == "一段没有 JSON 的普通文字回复。"
    assert result["findings"] == []
