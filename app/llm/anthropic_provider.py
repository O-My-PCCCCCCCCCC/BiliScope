"""Anthropic Claude provider。"""
from __future__ import annotations

import json

import anthropic

from app.llm.base import ChatResult, LLMClient, PROMPT, ToolCall, VideoTags


class AnthropicLLM(LLMClient):
    def __init__(self, api_key: str, model: str = "claude-haiku-4-5",
                 client: anthropic.Anthropic | None = None) -> None:
        self.model = model
        self.client = client or anthropic.Anthropic(api_key=api_key)

    def analyze_video(self, title: str, desc: str) -> VideoTags:
        msg = self.client.messages.parse(
            model=self.model,
            max_tokens=512,
            output_format=VideoTags,
            messages=[{"role": "user", "content": PROMPT.format(title=title, desc=desc)}],
        )
        return msg.parsed_output

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> ChatResult:
        api_tools = None
        if tools:
            api_tools = [
                {"name": t["function"]["name"],
                 "description": t["function"]["description"],
                 "input_schema": t["function"]["parameters"]}
                for t in tools
            ]
        api_messages = self._to_anthropic_messages(messages)
        resp = self.client.messages.create(
            model=self.model, max_tokens=1024,
            messages=api_messages, tools=api_tools,
        )
        text = "".join(b.text for b in resp.content if b.type == "text")
        tool_calls = [
            ToolCall(id=b.id, name=b.name, arguments=b.input or {})
            for b in resp.content if b.type == "tool_use"
        ]
        return ChatResult(text=text, tool_calls=tool_calls)

    def _to_anthropic_messages(self, messages: list[dict]) -> list[dict]:
        """把 OpenAI 风格消息转成 Anthropic 格式。"""
        out: list[dict] = []
        pending: list[dict] = []

        def flush():
            nonlocal pending
            if pending:
                content = [{"type": "tool_result", "tool_use_id": m["tool_call_id"],
                            "content": m["content"]} for m in pending]
                out.append({"role": "user", "content": content})
                pending = []

        for m in messages:
            role = m["role"]
            if role == "user":
                flush()
                out.append({"role": "user", "content": m.get("content", "")})
            elif role == "assistant":
                flush()
                content: list = []
                if m.get("content"):
                    content.append({"type": "text", "text": m["content"]})
                for tc in m.get("tool_calls") or []:
                    try:
                        args = json.loads(tc["function"].get("arguments") or "{}")
                    except Exception:
                        args = {}
                    content.append({"type": "tool_use", "id": tc["id"],
                                    "name": tc["function"]["name"], "input": args})
                out.append({"role": "assistant", "content": content})
            elif role == "tool":
                pending.append(m)
        flush()
        return out
