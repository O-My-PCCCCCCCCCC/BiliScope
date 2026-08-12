"""本地 Ollama provider。"""
from __future__ import annotations

import json

import httpx

from app.llm.base import LLMClient, PROMPT, VideoTags


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
        return VideoTags(tags=data["tags"], summary=data["summary"])
