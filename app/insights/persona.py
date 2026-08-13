"""AI 观看人格画像：聚合观看数据交给 LLM 生成人格描绘。"""
from __future__ import annotations

import sqlite3

from app.analyze import (category_distribution, fav_tnames, popularity,
                         time_buckets, up_depth, watch_completion, watch_profile)
from app.llm.base import LLMClient


def _summary(conn: sqlite3.Connection) -> str:
    p = watch_profile(conn)
    ups = [f"{u['up_name']}({u['views']})" for u in up_depth(conn, 5)] or ["无"]
    tns = [f"{t['tname']}({t['n']})" for t in fav_tnames(conn, 5)] or ["无"]
    cat = category_distribution(conn)["distribution"]
    cat_str = "、".join(f"{c['category']}({c['n']})" for c in cat[:5]) or "无"
    tb = time_buckets(conn)
    peak_bucket = max(tb, key=lambda x: x["n"])["bucket"] if tb else "未知"
    comp = watch_completion(conn)
    comp_str = "、".join(f"{c['bucket']}({c['n']})" for c in comp[:4]) or "无"
    pop = popularity(conn)
    pop_str = "、".join(f"{x['bucket']}({x['n']})" for x in pop[:4]) or "无"
    return (
        f"总观看 {p['total_views']} 个，累计时长 {p['total_duration_h']} 小时，"
        f"活跃 {p['active_days']} 天，日均 {p['avg_daily']} 个，"
        f"黄金时段在{p['peak_hour']}，最活跃{p['peak_weekday']}。"
        f"常看UP主：{'、'.join(ups)}。常看分区：{'、'.join(tns)}。"
        f"用途分布：{cat_str}。观看时段主力：{peak_bucket}。"
        f"完整度：{comp_str}。热门分布：{pop_str}。"
    )


def generate_persona(conn: sqlite3.Connection, llm_client: LLMClient) -> dict:
    summary = _summary(conn)
    prompt = (
        "你是数据洞察助手。以下是某位 B 站用户的观看数据摘要：\n"
        f"{summary}\n"
        "请描绘他的「B站观看人格画像」（130-180字），要求：\n"
        "1. 不要罗列具体数字，从整体抽象概括他的观看风格与节奏（如深夜党/碎片党/深度沉浸/广泛涉猎等）\n"
        "2. 点出他关注内容的偏向（学习成长型/娱乐放松型/资讯型）和观看习惯特征\n"
        "3. 用有画面感但不夸张的语言，像在和朋友聊天\n"
        "4. 结尾给一句简短的鼓励或建议\n"
        "用连贯段落，不要列表、不要重复数据。"
    )
    text = llm_client.chat([{"role": "user", "content": prompt}]).text.strip()
    return {"persona": text, "summary": summary}
