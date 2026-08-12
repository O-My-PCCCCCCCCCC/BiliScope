"""AI 聊天编排与工具调用循环（会话持久化到 SQLite）。"""
from __future__ import annotations

import json
import re
import time

import app.favtools as favtools
from app.database import get_conn, init_db
from app.downloader import start_download
from app.llm.base import LLMClient

SYSTEM_PROMPT = (
    "你是 BiliScope 的 AI 助手，帮助用户管理 B 站收藏夹、分析视频。"
    "你可以查看收藏夹和其中视频、新建/删除收藏夹、移动视频、分析视频链接。"
    "用户让你整理收藏夹时，先看内容再操作，不要编造数据；回答简洁清楚，避免冗长点评。"
)

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
    {"type": "function", "function": {"name": "analyze_video",
        "description": "分析一个 B 站视频链接，返回标题、UP主、简介、分区、播放量等",
        "parameters": {"type": "object", "properties": {
            "link": {"type": "string", "description": "B 站视频链接或 BV 号"}},
            "required": ["link"]}}},
    {"type": "function", "function": {"name": "download_videos",
        "description": "批量下载视频为 MP4（后台执行），传入 B 站链接列表",
        "parameters": {"type": "object", "properties": {
            "urls": {"type": "array", "items": {"type": "string"}, "description": "B 站视频链接列表"}},
            "required": ["urls"]}}},
    {"type": "function", "function": {"name": "download_audio",
        "description": "批量提取视频音频为 MP3（后台执行），传入 B 站链接列表",
        "parameters": {"type": "object", "properties": {
            "urls": {"type": "array", "items": {"type": "string"}, "description": "B 站视频链接列表"}},
            "required": ["urls"]}}},
]

TOOL_FUNCS = {
    "list_folders": lambda a: favtools.list_folders(),
    "list_fav_items": lambda a: favtools.list_fav_items(int(a.get("media_id", 0)), int(a.get("limit", 20))),
    "create_folder": lambda a: favtools.create_folder(a.get("title", "")),
    "delete_folder": lambda a: favtools.delete_folder(a.get("media_ids", "")),
    "move_fav_items": lambda a: favtools.move_fav_items(
        int(a.get("src_media_id", 0)), int(a.get("tar_media_id", 0)), a.get("bvids", [])),
    "analyze_video": lambda a: favtools.analyze_video(a.get("link", "")),
    "download_videos": lambda a: start_download(a.get("urls", []), "mp4"),
    "download_audio": lambda a: start_download(a.get("urls", []), "audio"),
}


def _persist(role: str, content: str = "", tool_calls: list | None = None,
             tool_call_id: str | None = None) -> None:
    conn = get_conn()
    init_db(conn)
    conn.execute(
        "INSERT INTO chat_messages (role, content, tool_calls_json, tool_call_id, created_at) VALUES (?, ?, ?, ?, ?)",
        (role, content,
         json.dumps(tool_calls, ensure_ascii=False) if tool_calls else None,
         tool_call_id, int(time.time())),
    )
    conn.commit()
    conn.close()


def get_history() -> list[dict]:
    conn = get_conn()
    init_db(conn)
    rows = conn.execute("SELECT * FROM chat_messages ORDER BY id").fetchall()
    conn.close()
    msgs = []
    for r in rows:
        m: dict = {"role": r["role"], "content": r["content"] or ""}
        if r["role"] == "assistant" and r["tool_calls_json"]:
            m["tool_calls"] = json.loads(r["tool_calls_json"])
        if r["role"] == "tool" and r["tool_call_id"]:
            m["tool_call_id"] = r["tool_call_id"]
        msgs.append(m)
    return msgs


def reset_session() -> None:
    conn = get_conn()
    init_db(conn)
    conn.execute("DELETE FROM chat_messages")
    conn.commit()
    conn.close()


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
    _persist("user", user_message)
    messages = list(history) + [{"role": "user", "content": user_message}]
    if not any(m.get("role") == "system" for m in messages):
        messages.insert(0, {"role": "system", "content": SYSTEM_PROMPT})
    tool_uses = []
    for _ in range(max_rounds):
        result = llm_client.chat(messages, TOOLS)
        if not result.tool_calls:
            messages.append({"role": "assistant", "content": result.text})
            _persist("assistant", result.text)
            return {"reply": result.text, "tool_uses": tool_uses}
        tc_list = [
            {"id": tc.id, "type": "function",
             "function": {"name": tc.name, "arguments": json.dumps(tc.arguments, ensure_ascii=False)}}
            for tc in result.tool_calls
        ]
        messages.append({"role": "assistant", "content": result.text, "tool_calls": tc_list})
        _persist("assistant", result.text, tool_calls=tc_list)
        for tc in result.tool_calls:
            output = execute_tool(tc.name, tc.arguments)
            tool_uses.append({"tool": tc.name, "args": tc.arguments, "output": output})
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": output})
            _persist("tool", output, tool_call_id=tc.id)
    return {"reply": "步骤较多，已暂停（你可以让我继续）", "tool_uses": tool_uses}
