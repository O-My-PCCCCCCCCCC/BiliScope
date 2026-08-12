"""Anthropic Claude provider。"""
from __future__ import annotations

import anthropic

from app.llm.base import LLMClient, PROMPT, VideoTags


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
