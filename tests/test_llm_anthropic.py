from __future__ import annotations

from app.llm.anthropic_provider import AnthropicLLM
from app.llm.base import VideoTags

captured = {}


class FakeMessage:
    parsed_output = VideoTags(tags=["科技", "AI"], summary="讲人工智能")


class FakeMessages:
    def parse(self, **kw):
        captured["kw"] = kw
        return FakeMessage()


def test_anthropic_analyze_video():
    captured.clear()
    fake = type("FakeClient", (), {"messages": FakeMessages()})()
    llm = AnthropicLLM(api_key="k", model="claude-haiku-4-5", client=fake)
    result = llm.analyze_video("标题", "简介")
    assert result.tags == ["科技", "AI"]
    assert captured["kw"]["model"] == "claude-haiku-4-5"
    assert "标题" in captured["kw"]["messages"][0]["content"]
    assert captured["kw"]["output_format"] is VideoTags


def test_anthropic_default_model():
    llm = AnthropicLLM(api_key="k")
    assert llm.model == "claude-haiku-4-5"
