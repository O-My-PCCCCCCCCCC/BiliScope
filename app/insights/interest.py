"""兴趣漂移分析：LLM 主题标签 × 观看月份，看兴趣随时间迁移。"""
from __future__ import annotations

import json
import sqlite3
import time
from collections import Counter
from datetime import datetime


def _month_series(months: int) -> list[str]:
    """从 months 个月前到本月的月份列表，如 ['2026-06', '2026-07', '2026-08']。"""
    today = datetime.now()
    y, m = today.year, today.month - (months - 1)
    while m <= 0:
        y -= 1
        m += 12
    out = []
    for _ in range(months):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def interest_drift(conn: sqlite3.Connection, months: int = 12,
                   top_n: int = 10) -> dict:
    """近 N 个月每个主题标签的观看数。series 为 TOP 标签 + 一个「其他」。"""
    months_list = _month_series(months)
    start = int(datetime(int(months_list[0][:4]), int(months_list[0][5:7]), 1).timestamp())
    rows = conn.execute(
        """SELECT va.bvid, va.tags_json, MIN(h.view_at) AS t
           FROM video_analysis va JOIN history h ON va.bvid = h.bvid
           WHERE h.view_at >= ?
           GROUP BY va.bvid""",
        (start,),
    ).fetchall()
    monthly: dict[str, Counter] = {m: Counter() for m in months_list}
    all_tags: Counter = Counter()
    for r in rows:
        try:
            tags = json.loads(r["tags_json"] or "[]")
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(tags, list):
            continue
        mo = time.strftime("%Y-%m", time.localtime(r["t"]))
        if mo not in monthly:
            continue
        for t in tags:
            monthly[mo][t] += 1
            all_tags[t] += 1
    if not all_tags:
        return {"months": months_list, "series": []}
    top = [t for t, _ in all_tags.most_common(top_n)]
    series: dict[str, list[int]] = {t: [0] * len(months_list) for t in top}
    series["其他"] = [0] * len(months_list)
    for i, mo in enumerate(months_list):
        for t, n in monthly[mo].items():
            if t in series:
                series[t][i] += n
            else:
                series["其他"][i] += n
    return {
        "months": months_list,
        "series": [{"tag": k, "data": v} for k, v in series.items()],
    }
