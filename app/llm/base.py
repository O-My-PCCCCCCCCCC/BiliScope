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
1. 用 3-5 个中文「内容主题类别词」概括其内容主题（如：音乐、科技、游戏、情感、教程、美食、时政、动漫…）。
   注意：标签必须是内容主题类别，绝对不要使用视频标题、歌曲名、作品名或专有名词作为标签。
2. 写一句话中文总结
3. 判断用途类别 category，只能从以下选一个：「学习提升」「娱乐消遣」「资讯」「生活实用」「其他」
   - 学习提升：教程、知识、技能、课程、学习、技术
   - 娱乐消遣：搞笑、游戏、音乐、影视、综艺、动漫、日常放松、娱乐
   - 资讯：新闻、热点、行业动态、时政
   - 生活实用：攻略、工具、购物、健康、美食教程、生活技巧
   - 其他：只有确实难以归入以上四类时才用「其他」，尽量从以上四类中选
标题：{title}
简介：{desc}
"""
