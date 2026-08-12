"""内容分析编排：把视频标题+简介交给 LLM 生成标签并入库。"""
from __future__ import annotations

import json
import sqlite3
import time

from app.llm.base import LLMClient


def analyze_unanalyzed(conn: sqlite3.Connection, llm_client: LLMClient,
                       limit: int = 50) -> int:
    rows = conn.execute(
        """SELECT bvid, title, desc FROM videos
           WHERE desc IS NOT NULL AND desc != ''
             AND bvid NOT IN (SELECT bvid FROM video_analysis)
           LIMIT ?""",
        (limit,),
    ).fetchall()
    n = 0
    model = getattr(llm_client, "model", "")
    for row in rows:
        try:
            result = llm_client.analyze_video(row["title"], row["desc"])
            conn.execute(
                "INSERT OR REPLACE INTO video_analysis (bvid, tags_json, summary, analyzed_at, model) VALUES (?, ?, ?, ?, ?)",
                (row["bvid"], json.dumps(result.tags, ensure_ascii=False), result.summary,
                 int(time.time()), model),
            )
            n += 1
        except Exception:
            continue
    conn.commit()
    return n


def analysis_stats(conn: sqlite3.Connection) -> dict:
    analyzed = conn.execute("SELECT COUNT(*) FROM video_analysis").fetchone()[0]
    total = conn.execute(
        "SELECT COUNT(*) FROM videos WHERE desc IS NOT NULL AND desc != ''"
    ).fetchone()[0]
    return {"analyzed": analyzed, "total": total}


def aggregate_themes(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    rows = conn.execute("SELECT tags_json FROM video_analysis").fetchall()
    counter: dict[str, int] = {}
    for row in rows:
        try:
            tags = json.loads(row["tags_json"] or "[]")
        except json.JSONDecodeError:
            continue
        for t in tags:
            counter[t] = counter.get(t, 0) + 1
    return sorted(
        ({"tag": k, "n": v} for k, v in counter.items()),
        key=lambda x: x["n"], reverse=True,
    )[:limit]
