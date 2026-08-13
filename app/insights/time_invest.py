"""时间投资榜：按用途/主题/UP主 累计实际观看时长。"""
from __future__ import annotations

import json
import sqlite3


def time_invest(conn: sqlite3.Connection, top_n: int = 15) -> dict:
    rows = conn.execute(
        """SELECT h.bvid, h.progress, v.duration, v.up_name, va.tags_json, va.category
           FROM history h
           JOIN videos v ON h.bvid = v.bvid
           LEFT JOIN video_analysis va ON h.bvid = va.bvid"""
    ).fetchall()
    by_category: dict[str, int] = {}
    by_up: dict[str, int] = {}
    by_tag: dict[str, int] = {}
    for r in rows:
        secs = r["progress"] or r["duration"] or 0
        if secs <= 0:
            continue
        # 没做过 LLM 分析的一律标「未分类」，避免和「其他」（LLM 确实归不出类）混淆
        cat = r["category"] or "未分类"
        by_category[cat] = by_category.get(cat, 0) + secs
        up = r["up_name"] or "未知UP"
        by_up[up] = by_up.get(up, 0) + secs
        try:
            tags = json.loads(r["tags_json"] or "[]")
        except (json.JSONDecodeError, TypeError):
            tags = []
        if not isinstance(tags, list):
            tags = []
        for t in tags:
            by_tag[t] = by_tag.get(t, 0) + secs

    def top(d: dict[str, int]) -> list[dict]:
        return [{"name": k, "seconds": v} for k, v in
                sorted(d.items(), key=lambda x: -x[1])[:top_n]]

    return {"by_category": top(by_category), "by_tag": top(by_tag), "by_up": top(by_up)}
