from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app import config, database
from app.insights.persona import generate_persona
from app.main import app

client = TestClient(app)


class FakeLLM:
    def chat(self, messages, tools=None):
        class R:
            text = "你是个深夜深度学习者，喜欢在安静时刷长视频。"
        return R()


def test_generate_persona(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    now = int(time.time())
    conn.execute("INSERT INTO videos (bvid, title, up_name, tname, duration, view_count) "
                 "VALUES ('BV1', 'A', 'UP甲', '科技', 3000, 50000)")
    conn.execute("INSERT INTO history (bvid, view_at, progress) VALUES ('BV1', ?, 3000)", (now,))
    conn.commit()
    conn.close()

    result = generate_persona(database.get_conn(), FakeLLM())
    assert result["persona"] == "你是个深夜深度学习者，喜欢在安静时刷长视频。"
    assert "总观看" in result["summary"]
    assert "UP甲" in result["summary"]


def test_generate_persona_empty_db(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    result = generate_persona(database.get_conn(), FakeLLM())
    assert result["persona"]
    assert result["summary"]


def test_persona_requires_llm(tmp_path):
    config.set_config_path(tmp_path / "config.json")
    config.save_config({**config.load_config(),
                        "llm": {"provider": "", "api_key": "", "base_url": "", "model": ""}})
    assert client.post("/api/insights/persona").status_code == 400


def test_persona_generates(monkeypatch, tmp_path):
    config.set_config_path(tmp_path / "config.json")
    config.save_config({**config.load_config(),
                        "llm": {"provider": "openai", "api_key": "k", "base_url": "", "model": ""}})
    import app.api as api_mod
    monkeypatch.setattr(api_mod, "generate_persona",
                        lambda conn, llm_client: {"persona": "画像", "summary": "s"})
    r = client.post("/api/insights/persona")
    assert r.status_code == 200
    assert r.json() == {"persona": "画像", "summary": "s"}
