"""LLM 提供层抽象。"""
from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel


class VideoTags(BaseModel):
    tags: list[str]
    summary: str
    category: str = "其他"


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


PROMPT = """根据视频的标题和简介：
1. 用 3-5 个中文标签概括其内容主题
2. 写一句话中文总结
3. 判断用途类别 category，只能从以下选一个：「学习提升」「娱乐消遣」「资讯」「生活实用」「其他」
   - 学习提升：教程、知识、技能、课程
   - 娱乐消遣：搞笑、游戏、音乐、影视、日常放松
   - 资讯：新闻、热点、行业动态
   - 生活实用：攻略、工具、购物、健康
   - 其他：难以归类的
标题：{title}
简介：{desc}
"""
