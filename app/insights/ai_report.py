"""AI 综合分析报告：聚合全部指标 → LLM 生成画像叙事 + 关键发现。"""
from __future__ import annotations

import json
import sqlite3

from app.analyze import (aggregate_themes, category_distribution, graveyard_stats,
                         up_depth, watch_profile)
from app.insights.watching import night_owl_stats, repeat_watches, streak_stats
from app.llm.base import LLMClient


def _summary(conn: sqlite3.Connection) -> str:
    p = watch_profile(conn)
    gy = graveyard_stats(conn)
    night = night_owl_stats(conn)
    streak = streak_stats(conn)
    cats = category_distribution(conn)["distribution"]
    ups = up_depth(conn, 3)
    rep = repeat_watches(conn, 3)
    themes = aggregate_themes(conn, 5)

    cat_str = "、".join(f"{c['category']}({c['n']})" for c in cats) or "无"
    up_str = "、".join(f"{u['up_name']}({u['views']})" for u in ups) or "无"
    theme_str = "、".join(f"{t['tag']}({t['n']})" for t in themes) or "无"
    rep_str = "、".join(f"{r['title'][:15]}({r['views']}遍)" for r in rep) or "无"

    lines = [
        f"总观看 {p['total_views']}，累计 {p['total_duration_h']} 小时，"
        f"活跃 {p['active_days']} 天，日均 {p['avg_daily']}，"
        f"黄金时段{p['peak_hour']}，最活跃{p['peak_weekday']}",
        f"用途分布：{cat_str}",
        f"常看UP主：{up_str}",
        f"主题标签：{theme_str}",
        f"收藏吃灰率 {gy['pct']}%（{gy['graveyard']}/{gy['total']}）",
        f"深夜占比 {night['night_ratio']}%（{night['night_level']}），工作日占比 {night['weekday_ratio']}%",
        f"最长连续观看 {streak['longest_streak']} 天，近期活跃 {streak['active_days']} 天",
        f"重复观看最多：{rep_str}",
    ]
    return "\n".join(lines)


def generate_ai_report(conn: sqlite3.Connection, llm_client: LLMClient) -> dict:
    """生成 AI 综合分析报告，返回 {narrative, findings:[{title, detail}]}。"""
    summary = _summary(conn)
    prompt = (
        "你是数据洞察分析师。以下是某位 B 站用户近期的观看数据摘要：\n"
        f"{summary}\n"
        "请写一份「B站观看分析报告」，必须严格按以下 JSON 格式返回，不要输出多余内容：\n"
        '{"narrative": "一段200-300字的画像叙事，概括他的观看风格/时间去向/兴趣倾向/作息习惯，'
        '像朋友聊天、有画面感，不要罗列数字", '
        '"findings": [{"title": "发现标题(10字内)", "detail": "发现+数据+含义，60字内"}]}\n'
        "findings 给 3-5 条最有价值的关键发现，每条结合具体数据点出含义"
        "（如吃灰率高=收藏了没看、深夜占比高=作息、某UP主沉迷=深度粉等）。"
    )
    text = llm_client.chat([{"role": "user", "content": prompt}]).text.strip()
    try:
        start = text.find("{")
        end = text.rfind("}")
        data = json.loads(text[start:end + 1])
        return {"narrative": data.get("narrative") or text,
                "findings": data.get("findings") or []}
    except Exception:
        return {"narrative": text, "findings": []}
