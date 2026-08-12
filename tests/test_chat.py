from __future__ import annotations

from app import chat, favtools
from app.llm.anthropic_provider import AnthropicLLM
from app.llm.base import ChatResult, ToolCall


class FakeLLM:
    def __init__(self, script):
        self.script = list(script)
        self.messages_seen = []

    def chat(self, messages, tools=None):
        self.messages_seen.append(messages)
        return self.script.pop(0)

    def analyze_video(self, title, desc):
        raise NotImplementedError


def test_run_chat_executes_tools(monkeypatch):
    chat.reset_session()
    calls = []
    monkeypatch.setattr(chat, "execute_tool",
                        lambda name, args: (calls.append((name, args)), '{"ok":true}')[1])
    llm = FakeLLM([
        ChatResult(text="", tool_calls=[ToolCall(id="1", name="list_folders", arguments={})]),
        ChatResult(text="完成", tool_calls=[]),
    ])
    result = chat.run_chat(llm, [], "整理我的收藏夹")
    assert result["reply"] == "完成"
    assert calls == [("list_folders", {})]
    assert result["tool_uses"][0]["tool"] == "list_folders"


def test_run_chat_preserves_tool_roundtrip():
    # 验证 assistant.tool_calls 与 tool 消息按 OpenAI 风格回填
    llm = FakeLLM([
        ChatResult(text="", tool_calls=[ToolCall(id="x1", name="create_folder", arguments={"title": "测试"})]),
        ChatResult(text="已创建", tool_calls=[]),
    ])
    result = chat.run_chat(llm, [], "新建一个叫测试的收藏夹")
    assistant = [m for m in result["messages"] if m["role"] == "assistant"][0]
    assert assistant["tool_calls"][0]["function"]["name"] == "create_folder"
    tool_msg = [m for m in result["messages"] if m["role"] == "tool"]
    assert tool_msg and tool_msg[0]["tool_call_id"] == "x1"


def test_execute_tool_unknown():
    out = chat.execute_tool("no_such", {})
    assert "error" in out


def test_favtools_move_params(monkeypatch):
    captured = {}

    class Fake:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post_json(self, path, data=None):
            captured["path"] = path
            captured["data"] = data
            return {"code": 0}

    monkeypatch.setattr(favtools, "_client", lambda: Fake())
    favtools.move_fav_items(101, 202, ["BV1", "BV2"])
    assert captured["path"] == "/x/v3/fav/resource/move"
    assert captured["data"]["src_media_id"] == 101
    assert captured["data"]["tar_media_id"] == 202
    assert '"id": "BV1"' in captured["data"]["resources"]
    assert '"type": 2' in captured["data"]["resources"]


def test_anthropic_message_conversion():
    llm = AnthropicLLM(api_key="k")
    msgs = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "",
         "tool_calls": [{"id": "t1", "function": {"name": "f", "arguments": '{"a":1}'}}]},
        {"role": "tool", "tool_call_id": "t1", "content": "ok"},
        {"role": "user", "content": "继续"},
    ]
    out = llm._to_anthropic_messages(msgs)
    assert out[0] == {"role": "user", "content": "hi"}
    asst = out[1]
    assert asst["role"] == "assistant"
    assert asst["content"][0]["type"] == "tool_use"
    assert asst["content"][0]["input"] == {"a": 1}
    # tool_result 被并进后续 user 消息
    tool_user = out[2]
    assert tool_user["role"] == "user"
    assert tool_user["content"][0]["type"] == "tool_result"
    assert tool_user["content"][0]["tool_use_id"] == "t1"
