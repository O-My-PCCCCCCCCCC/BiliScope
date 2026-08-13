"""观看行为深度聚合：重复观看 / 连续活跃 / 深夜作息。"""
from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timedelta


def repeat_watches(conn: sqlite3.Connection, limit: int = 10) -> list[dict]:
    """重复观看 / 沉迷视频 TOP：同一视频看几遍 + 累计观看时长。"""
    rows = conn.execute(
        """SELECT v.bvid, v.title, v.up_name,
                  COUNT(*) AS views,
                  SUM(COALESCE(NULLIF(h.progress, 0), v.duration)) AS total_sec
           FROM history h JOIN videos v ON h.bvid = v.bvid
           WHERE v.title IS NOT NULL AND v.title != ''
           GROUP BY v.bvid
           HAVING COUNT(*) > 1
           ORDER BY views DESC, total_sec DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def streak_stats(conn: sqlite3.Connection, days: int = 90) -> dict:
    """最长连续观看天数 + 活跃天数 + 周活跃趋势 + 日历。"""
    start = int(time.time()) - days * 86400
    days_set = sorted(
        r["day"] for r in conn.execute(
            """SELECT DISTINCT date(view_at, 'unixepoch', 'localtime') AS day
               FROM history WHERE view_at >= ?""", (start,)).fetchall()
    )
    longest = cur = 0
    prev = None
    for d in days_set:
        dt = datetime.strptime(d, "%Y-%m-%d")
        cur = cur + 1 if prev is not None and (dt - prev).days == 1 else 1
        longest = max(longest, cur)
        prev = dt
    weekly = [dict(r) for r in conn.execute(
        """SELECT strftime('%Y-%m-%d', date(view_at, 'unixepoch', 'localtime'),
                 'start of week', '+7 days') AS w,
                 COUNT(DISTINCT date(view_at, 'unixepoch', 'localtime')) AS n
           FROM history WHERE view_at >= ?
           GROUP BY w ORDER BY w""", (start,)).fetchall()]
    calendar = [dict(r) for r in conn.execute(
        """SELECT date(view_at, 'unixepoch', 'localtime') AS day, COUNT(*) AS n
           FROM history WHERE view_at >= ? GROUP BY day""", (start,)).fetchall()]
    return {"longest_streak": longest, "active_days": len(days_set),
            "weekly": weekly, "calendar": calendar}


def night_owl_stats(conn: sqlite3.Connection) -> dict:
    """深夜(0-6)观看占比 + 工作日/周末节奏 + 作息标签。"""
    total = conn.execute("SELECT COUNT(*) FROM history").fetchone()[0]
    night = conn.execute(
        """SELECT COUNT(*) FROM history
           WHERE CAST(strftime('%H', view_at, 'unixepoch', 'localtime') AS INTEGER) < 6"""
    ).fetchone()[0]
    night_ratio = round(night / total * 100, 1) if total else 0
    weekend = conn.execute(
        """SELECT COUNT(*) FROM history
           WHERE CAST(strftime('%w', view_at, 'unixepoch', 'localtime') AS INTEGER) IN (0, 6)"""
    ).fetchone()[0]
    weekday_ratio = round((total - weekend) / total * 100, 1) if total else 0
    if night_ratio >= 25:
        level = "重度夜猫"
    elif night_ratio >= 10:
        level = "常熬夜"
    else:
        level = "作息规律"
    return {"night_ratio": night_ratio, "weekday_ratio": weekday_ratio, "night_level": level}
