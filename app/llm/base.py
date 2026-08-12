"""LLM 提供层抽象。"""
from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel


class VideoTags(BaseModel):
    tags: list[str]
    summary: str


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict


class ChatResult(BaseModel):
    text: str = ""
    tool_calls: list[ToolCall] = []


class LLMClient(ABC):
    @abstractmethod
    def analyze_video(self, title: str, desc: str) -> VideoTags:
        ...

    @abstractmethod
    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> ChatResult:
        ...


PROMPT = """根据视频的标题和简介，用 3-5 个中文标签概括其内容主题，并写一句话中文总结。
标题：{title}
简介：{desc}
"""
