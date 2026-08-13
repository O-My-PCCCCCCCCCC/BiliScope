"""本地 Ollama provider。"""
from __future__ import annotations

import json

import httpx

from app.llm.base import ChatResult, LLMClient, PROMPT, ToolCall, VideoTags


class OllamaClient(LLMClient):
    def __init__(self, model: str = "qwen2.5:7b",
                 base_url: str = "http://localhost:11434",
                 client: httpx.Client | None = None) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.client = client

    def analyze_video(self, title: str, desc: str) -> VideoTags:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content":
                          PROMPT.format(title=title, desc=desc) +
                          '\n只输出 JSON：{"tags": [...], "summary": "..."}'}],
            "format": "json",
            "stream": False,
        }
        if self.client:
            resp = self.client.post(f"{self.base_url}/api/chat", json=payload, timeout=120)
        else:
            resp = httpx.post(f"{self.base_url}/api/chat", json=payload, timeout=120)
        content = resp.json()["message"]["content"]
        data = json.loads(content)
        return VideoTags(tags=data["tags"], summary=data["summary"], category=data.get("category", "其他"))

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> ChatResult:
        """走 Ollama 的 OpenAI 兼容端点 /v1/chat/completions。"""
        payload: dict = {"model": self.model, "messages": messages, "stream": False}
        if tools:
            payload["tools"] = tools
        url = f"{self.base_url}/v1/chat/completions"
        if self.client:
            resp = self.client.post(url, json=payload, timeout=180)
        else:
            resp = httpx.post(url, json=payload, timeout=180)
        data = resp.json()
        msg = data["choices"][0]["message"]
        tool_calls = []
        for tc in msg.get("tool_calls") or []:
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
            except Exception:
                args = {}
            tool_calls.append(ToolCall(id=tc["id"], name=tc["function"]["name"], arguments=args))
        return ChatResult(text=msg.get("content") or "", tool_calls=tool_calls)
