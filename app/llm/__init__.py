"""LLM 提供层：按配置选择 provider。"""
from __future__ import annotations

from app.llm.anthropic_provider import AnthropicLLM
from app.llm.base import LLMClient, VideoTags
from app.llm.ollama_provider import OllamaClient
from app.llm.openai_provider import OpenAIClient


def get_llm_client(cfg: dict) -> LLMClient:
    provider = cfg.get("provider", "ollama")
    api_key = cfg.get("api_key", "")
    base_url = cfg.get("base_url", "")
    model = cfg.get("model", "")
    if provider == "anthropic":
        return AnthropicLLM(api_key=api_key, model=model or "claude-haiku-4-5")
    if provider == "openai":
        return OpenAIClient(api_key=api_key, base_url=base_url or None,
                            model=model or "deepseek-chat")
    return OllamaClient(model=model or "qwen2.5:7b", base_url=base_url or "http://localhost:11434")
