"""观看数据报告生成（周报/月报）。"""
from __future__ import annotations

import json
import sqlite3
import time


def _range(type_: str) -> tuple[int, str]:
    now = int(time.time())
    if type_ == "weekly":
        start = now - 7 * 86400
    else:
        start = now - 30 * 86400
    period = f"{time.strftime('%Y-%m-%d', time.localtime(start))} ~ {time.strftime('%Y-%m-%d', time.localtime(now))}"
    return start, period


def generate_report(conn: sqlite3.Connection, type_: str = "weekly") -> dict:
    """聚合最近 7/30 天观看数据并写入 reports 表。"""
    start, period = _range(type_)
    views = conn.execute(
        "SELECT COUNT(*) FROM history WHERE view_at >= ?", (start,)
    ).fetchone()[0]
    top_ups = [dict(r) for r in conn.execute(
        """SELECT v.up_name, COUNT(*) AS n FROM history h
           JOIN videos v ON h.bvid = v.bvid
           WHERE h.view_at >= ? AND v.up_name != ''
           GROUP BY v.up_name ORDER BY n DESC LIMIT 5""",
        (start,),
    ).fetchall()]
    tnames = [dict(r) for r in conn.execute(
        """SELECT v.tname, COUNT(*) AS n FROM history h
           JOIN videos v ON h.bvid = v.bvid
           WHERE h.view_at >= ? AND v.tname != ''
           GROUP BY v.tname ORDER BY n DESC LIMIT 8""",
        (start,),
    ).fetchall()]
    hours = [dict(r) for r in conn.execute(
        """SELECT CAST(strftime('%H', view_at, 'unixepoch', 'localtime') AS INTEGER) AS h, COUNT(*) AS n
           FROM history WHERE view_at >= ? GROUP BY h""",
        (start,),
    ).fetchall()]
    stats = {"views": views, "top_ups": top_ups, "tnames": tnames, "hours": hours}
    cur = conn.execute(
        "INSERT INTO reports (period, type, content_json, created_at) VALUES (?, ?, ?, ?)",
        (period, type_, json.dumps(stats, ensure_ascii=False), int(time.time())),
    )
    conn.commit()
    return {"id": cur.lastrowid, "period": period, "type": type_, "stats": stats}


def report_to_html(stats: dict, period: str) -> str:
    """生成报告 HTML 摘要。"""
    top = "、".join(f"{u['up_name']}({u['n']})" for u in stats.get("top_ups", [])) or "无"
    tnames = "、".join(f"{t['tname']}({t['n']})" for t in stats.get("tnames", [])) or "无"
    return f"""
    <h3>观看报告（{period}）</h3>
    <p>观看视频数：<b>{stats.get('views', 0)}</b></p>
    <p>常看 UP 主 TOP：{top}</p>
    <p>内容分区：{tnames}</p>
    """
