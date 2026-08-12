from __future__ import annotations

import json

from app.llm import get_llm_client
from app.llm.ollama_provider import OllamaClient
from app.llm.openai_provider import OpenAIClient

captured = {}


class FakeMsg:
    content = json.dumps({"tags": ["游戏"], "summary": "评测"}, ensure_ascii=False)


class FakeChoice:
    message = FakeMsg()


class FakeChoices:
    choices = [FakeChoice()]


class FakeOpenAI:
    class chat:
        class completions:
            @staticmethod
            def create(**kw):
                captured["kw"] = kw
                return FakeChoices()


def test_openai_analyze_video():
    captured.clear()
    fake = type("FakeClient", (), {"chat": FakeOpenAI.chat})()
    llm = OpenAIClient(api_key="k", client=fake)
    r = llm.analyze_video("标题", "简介")
    assert r.tags == ["游戏"]
    assert captured["kw"]["response_format"] == {"type": "json_object"}


def test_ollama_analyze_video(monkeypatch):
    sent = {}

    def fake_post(url, json=None, timeout=None):
        sent["url"] = url
        sent["json"] = json
        content = '{"tags": ["音乐"], "summary": "演奏"}'
        class Resp:
            def json(self):
                return {"message": {"content": content}}
        return Resp()

    monkeypatch.setattr("app.llm.ollama_provider.httpx.post", fake_post)
    llm = OllamaClient(model="qwen2.5:7b")
    r = llm.analyze_video("标题", "简介")
    assert r.tags == ["音乐"]
    assert "localhost:11434" in sent["url"]
    assert sent["json"]["format"] == "json"


def test_factory_provider_selection():
    from app.llm.anthropic_provider import AnthropicLLM
    assert isinstance(get_llm_client({"provider": "anthropic", "api_key": "k"}), AnthropicLLM)
    assert isinstance(get_llm_client({"provider": "openai", "api_key": "k"}), OpenAIClient)
    assert isinstance(get_llm_client({"provider": "ollama"}), OllamaClient)
