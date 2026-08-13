"""时段 × 内容交叉：什么时间在看什么内容。"""
from __future__ import annotations

import sqlite3

TIME_BUCKETS = ["凌晨(0-6)", "上午(6-12)", "下午(12-18)", "晚上(18-24)"]


def _bucket(hour: int) -> str:
    if 0 <= hour < 6:
        return TIME_BUCKETS[0]
    if 6 <= hour < 12:
        return TIME_BUCKETS[1]
    if 12 <= hour < 18:
        return TIME_BUCKETS[2]
    return TIME_BUCKETS[3]


def time_content_cross(conn: sqlite3.Connection, dim: str = "tname",
                       top_n: int = 10) -> dict:
    """时段 × 分区/用途 观看数矩阵。dim='tname' 或 'category'。"""
    if dim == "category":
        dim_expr = "COALESCE(va.category, '其他')"
        join_clause = "LEFT JOIN video_analysis va ON h.bvid = va.bvid"
    else:
        dim_expr = "COALESCE(NULLIF(v.tname, ''), '其他')"
        join_clause = "JOIN videos v ON h.bvid = v.bvid"
    rows = [dict(r) for r in conn.execute(
        f"""SELECT {dim_expr} AS dim,
                   CAST(strftime('%H', h.view_at, 'unixepoch', 'localtime') AS INTEGER) AS hour,
                   COUNT(*) AS n
            FROM history h {join_clause}
            GROUP BY dim, hour"""
    ).fetchall()]
    totals: dict[str, int] = {}
    for r in rows:
        totals[r["dim"]] = totals.get(r["dim"], 0) + r["n"]
    categories = sorted(totals, key=lambda d: totals[d], reverse=True)[:top_n]
    buckets = list(TIME_BUCKETS)
    matrix = [[0] * len(categories) for _ in buckets]
    for r in rows:
        if r["dim"] not in categories:
            continue
        ci = categories.index(r["dim"])
        bi = buckets.index(_bucket(r["hour"]))
        matrix[bi][ci] += r["n"]
    return {"buckets": buckets, "categories": categories, "matrix": matrix}
