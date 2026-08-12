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


def generate_weekly_ai(conn: sqlite3.Connection, llm_client, days: int = 7) -> dict:
    """用 LLM 生成本周观看评价（周报）。"""
    start = int(time.time()) - days * 86400
    views = conn.execute(
        "SELECT COUNT(*) FROM history WHERE view_at >= ?", (start,)
    ).fetchone()[0]
    top_ups = [dict(r) for r in conn.execute(
        """SELECT v.up_name, COUNT(*) AS n FROM history h JOIN videos v ON h.bvid = v.bvid
           WHERE h.view_at >= ? AND v.up_name != ''
           GROUP BY v.up_name ORDER BY n DESC LIMIT 5""", (start,),
    ).fetchall()]
    tnames = [dict(r) for r in conn.execute(
        """SELECT v.tname, COUNT(*) AS n FROM history h JOIN videos v ON h.bvid = v.bvid
           WHERE h.view_at >= ? AND v.tname != ''
           GROUP BY v.tname ORDER BY n DESC LIMIT 5""", (start,),
    ).fetchall()]
    peak = conn.execute(
        """SELECT CAST(strftime('%H', view_at, 'unixepoch', 'localtime') AS INTEGER) AS h, COUNT(*) AS n
           FROM history WHERE view_at >= ? GROUP BY h ORDER BY n DESC LIMIT 1""", (start,),
    ).fetchone()
    up_str = "、".join(f"{u['up_name']}({u['n']})" for u in top_ups) or "无"
    tn_str = "、".join(f"{t['tname']}({t['n']})" for t in tnames) or "无"
    summary = (
        f"本周（7天）观看视频 {views} 个。"
        f"常看 UP 主：{up_str}。常看分区：{tn_str}。"
        f"观看高峰在 {peak['h']} 点。"
    )
    prompt = (
        "你是数据洞察助手。以下是一份 B 站用户本周的观看数据摘要：\n"
        f"{summary}\n"
        "请用轻松、友好、有人情味的中文写一份周报评价（120-180字），"
        "点评他的观看习惯和偏好，结尾给一句鼓励或建议。不要用列表，用连贯段落。"
    )
    text = llm_client.chat([{"role": "user", "content": prompt}]).text.strip()
    conn.execute(
        "INSERT INTO reports (period, type, content_json, created_at) VALUES ('本周', 'weekly_ai', ?, ?)",
        (json.dumps({"report": text, "summary": summary}, ensure_ascii=False), int(time.time())),
    )
    conn.commit()
    return {"report": text, "views": views, "summary": summary}


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
