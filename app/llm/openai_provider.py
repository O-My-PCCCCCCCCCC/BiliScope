"""OpenAI 兼容 provider（DeepSeek / 通义 / Kimi 等）。"""
from __future__ import annotations

import json

from openai import OpenAI

from app.llm.base import LLMClient, PROMPT, VideoTags


class OpenAIClient(LLMClient):
    def __init__(self, api_key: str, base_url: str | None = None,
                 model: str = "deepseek-chat", client: OpenAI | None = None) -> None:
        self.model = model
        self.client = client or (OpenAI(api_key=api_key, base_url=base_url) if base_url
                                 else OpenAI(api_key=api_key))

    def analyze_video(self, title: str, desc: str) -> VideoTags:
        resp = self.client.chat.completions.create(
            model=self.model,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content":
                       PROMPT.format(title=title, desc=desc) +
                       '\n请以 JSON 返回 {"tags": ["标签1","标签2"], "summary": "一句话总结"}。'}],
        )
        text = resp.choices[0].message.content
        data = json.loads(text)
        return VideoTags(tags=data["tags"], summary=data["summary"])
