"""AI 聊天编排与工具调用循环。"""
from __future__ import annotations

import json

import app.favtools as favtools
from app.llm.base import LLMClient

TOOLS = [
    {"type": "function", "function": {"name": "list_folders",
        "description": "列出我的全部收藏夹及其 id", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "list_fav_items",
        "description": "列出某个收藏夹里的视频（返回 bvid、标题、UP主、分区）",
        "parameters": {"type": "object", "properties": {
            "media_id": {"type": "integer", "description": "收藏夹 id"},
            "limit": {"type": "integer", "description": "最多返回条数"}},
            "required": ["media_id"]}}},
    {"type": "function", "function": {"name": "create_folder",
        "description": "新建一个收藏夹", "parameters": {"type": "object", "properties": {
            "title": {"type": "string", "description": "收藏夹名称"}}, "required": ["title"]}}},
    {"type": "function", "function": {"name": "move_fav_items",
        "description": "把一批视频从一个收藏夹移动到另一个收藏夹",
        "parameters": {"type": "object", "properties": {
            "src_media_id": {"type": "integer", "description": "来源收藏夹 id"},
            "tar_media_id": {"type": "integer", "description": "目标收藏夹 id"},
            "bvids": {"type": "array", "items": {"type": "string"}, "description": "要移动的视频 bvid 列表"}},
            "required": ["src_media_id", "tar_media_id", "bvids"]}}},
    {"type": "function", "function": {"name": "delete_folder",
        "description": "删除收藏夹", "parameters": {"type": "object", "properties": {
            "media_ids": {"type": "string", "description": "收藏夹 media_id，多个用逗号分隔"}},
            "required": ["media_ids"]}}},
]

TOOL_FUNCS = {
    "list_folders": lambda a: favtools.list_folders(),
    "list_fav_items": lambda a: favtools.list_fav_items(int(a.get("media_id", 0)), int(a.get("limit", 20))),
    "create_folder": lambda a: favtools.create_folder(a.get("title", "")),
    "delete_folder": lambda a: favtools.delete_folder(a.get("media_ids", "")),
    "move_fav_items": lambda a: favtools.move_fav_items(
        int(a.get("src_media_id", 0)), int(a.get("tar_media_id", 0)), a.get("bvids", [])),
}

# 会话（内存，单用户）
_session: list[dict] = []


def get_history() -> list[dict]:
    return list(_session)


def reset_session() -> None:
    _session.clear()


def set_history(messages: list[dict]) -> None:
    _session[:] = messages


def execute_tool(name: str, args: dict) -> str:
    fn = TOOL_FUNCS.get(name)
    if not fn:
        return json.dumps({"error": f"未知工具 {name}"}, ensure_ascii=False)
    try:
        return json.dumps(fn(args), ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def run_chat(llm_client: LLMClient, history: list[dict], user_message: str,
             max_rounds: int = 6) -> dict:
    messages = history + [{"role": "user", "content": user_message}]
    tool_uses = []
    for _ in range(max_rounds):
        result = llm_client.chat(messages, TOOLS)
        if not result.tool_calls:
            messages.append({"role": "assistant", "content": result.text})
            return {"reply": result.text, "messages": messages, "tool_uses": tool_uses}
        messages.append({
            "role": "assistant", "content": result.text,
            "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.name, "arguments": json.dumps(tc.arguments, ensure_ascii=False)}}
                for tc in result.tool_calls
            ],
        })
        for tc in result.tool_calls:
            output = execute_tool(tc.name, tc.arguments)
            tool_uses.append({"tool": tc.name, "args": tc.arguments, "output": output})
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": output})
    return {"reply": "步骤较多，已暂停（你可以让我继续）", "messages": messages, "tool_uses": tool_uses}
