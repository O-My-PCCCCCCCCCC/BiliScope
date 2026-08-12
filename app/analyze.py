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


def monthly_trend(conn: sqlite3.Connection, months: int = 12) -> list[dict]:
    """近 N 个月观看趋势。"""
    now = int(time.time())
    start = now - months * 30 * 86400
    return [dict(r) for r in conn.execute(
        """SELECT strftime('%Y-%m', view_at, 'unixepoch', 'localtime') AS ym, COUNT(*) AS n
           FROM history WHERE view_at >= ?
           GROUP BY ym ORDER BY ym""",
        (start,),
    ).fetchall()]


def watch_profile(conn: sqlite3.Connection) -> dict:
    """观看画像：总量、时长、活跃天数、黄金时段等。"""
    total_views = conn.execute("SELECT COUNT(*) FROM history").fetchone()[0]
    total_dur = conn.execute(
        "SELECT COALESCE(SUM(duration), 0) FROM history h JOIN videos v ON h.bvid = v.bvid WHERE v.duration > 0"
    ).fetchone()[0]
    active_days = conn.execute(
        "SELECT COUNT(DISTINCT date(view_at, 'unixepoch', 'localtime')) FROM history"
    ).fetchone()[0]
    avg_daily = round(total_views / active_days, 1) if active_days else 0
    peak_hour = conn.execute(
        """SELECT CAST(strftime('%H', view_at, 'unixepoch', 'localtime') AS INTEGER) AS h, COUNT(*) AS n
           FROM history GROUP BY h ORDER BY n DESC LIMIT 1"""
    ).fetchone()
    weekdays = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"]
    peak_w = conn.execute(
        """SELECT CAST(strftime('%w', view_at, 'unixepoch', 'localtime') AS INTEGER) AS w, COUNT(*) AS n
           FROM history GROUP BY w ORDER BY n DESC LIMIT 1"""
    ).fetchone()
    return {
        "total_views": total_views,
        "total_duration_h": round(total_dur / 3600, 1),
        "active_days": active_days,
        "avg_daily": avg_daily,
        "peak_hour": f"{peak_hour['h']}时" if peak_hour else "-",
        "peak_weekday": weekdays[peak_w["w"]] if peak_w else "-",
    }


def fav_tnames(conn: sqlite3.Connection, limit: int = 12) -> list[dict]:
    """收藏内容分区分布。"""
    return [dict(r) for r in conn.execute(
        """SELECT v.tname, COUNT(*) AS n FROM fav_items f
           JOIN videos v ON f.bvid = v.bvid
           WHERE v.tname != ''
           GROUP BY v.tname ORDER BY n DESC LIMIT ?""",
        (limit,),
    ).fetchall()]


def graveyard_list(conn: sqlite3.Connection, limit: int = 100) -> list[dict]:
    """吃灰收藏明细：收藏了但从没看过。"""
    return [dict(r) for r in conn.execute(
        """SELECT f.bvid, v.title, v.up_name, v.tname, f.fav_time
           FROM fav_items f LEFT JOIN videos v ON f.bvid = v.bvid
           WHERE f.bvid NOT IN (SELECT bvid FROM history)
           ORDER BY f.fav_time DESC LIMIT ?""",
        (limit,),
    ).fetchall()]


def watch_completion(conn: sqlite3.Connection) -> list[dict]:
    """观看完整度分布（进度/时长）。"""
    return [dict(r) for r in conn.execute(
        """SELECT CASE
                  WHEN h.progress * 1.0 / v.duration >= 0.9 THEN '看完(90%+)'
                  WHEN h.progress * 1.0 / v.duration >= 0.5 THEN '看大半(50-90%)'
                  WHEN h.progress * 1.0 / v.duration >= 0.3 THEN '看一半(30-50%)'
                  ELSE '只看开头(<30%)' END AS bucket, COUNT(*) AS n
           FROM history h JOIN videos v ON h.bvid = v.bvid
           WHERE v.duration > 0
           GROUP BY bucket"""
    ).fetchall()]


def time_buckets(conn: sqlite3.Connection) -> list[dict]:
    """时段细分：凌晨/上午/下午/晚上。"""
    return [dict(r) for r in conn.execute(
        """SELECT CASE
                  WHEN hour >= 0 AND hour < 6 THEN '凌晨(0-6)'
                  WHEN hour >= 6 AND hour < 12 THEN '上午(6-12)'
                  WHEN hour >= 12 AND hour < 18 THEN '下午(12-18)'
                  ELSE '晚上(18-24)' END AS bucket, COUNT(*) AS n
           FROM (SELECT CAST(strftime('%H', view_at, 'unixepoch', 'localtime') AS INTEGER) AS hour
                 FROM history) GROUP BY bucket"""
    ).fetchall()]


def up_depth(conn: sqlite3.Connection, limit: int = 15) -> list[dict]:
    """UP主深度榜：次数、总时长、最近观看。"""
    return [dict(r) for r in conn.execute(
        """SELECT v.up_name, COUNT(*) AS views, SUM(v.duration) AS total_sec,
                  MAX(h.view_at) AS last_view
           FROM history h JOIN videos v ON h.bvid = v.bvid
           WHERE v.up_name != '' AND v.duration > 0
           GROUP BY v.up_name ORDER BY total_sec DESC LIMIT ?""",
        (limit,),
    ).fetchall()]


def popularity(conn: sqlite3.Connection) -> list[dict]:
    """热门 vs 小众：你观看的视频播放量分布。"""
    return [dict(r) for r in conn.execute(
        """SELECT CASE
                  WHEN v.view_count < 10000 THEN '<1万(小众)'
                  WHEN v.view_count < 100000 THEN '1-10万'
                  WHEN v.view_count < 1000000 THEN '10-100万'
                  ELSE '>100万(爆款)' END AS bucket, COUNT(*) AS n
           FROM history h JOIN videos v ON h.bvid = v.bvid
           WHERE v.view_count > 0 GROUP BY bucket"""
    ).fetchall()]


def weekday_weekend(conn: sqlite3.Connection) -> list[dict]:
    """工作日 vs 周末观看。"""
    return [dict(r) for r in conn.execute(
        """SELECT CASE
                  WHEN CAST(strftime('%w', view_at, 'unixepoch', 'localtime') AS INTEGER) IN (0, 6)
                  THEN '周末' ELSE '工作日' END AS kind, COUNT(*) AS n
           FROM history GROUP BY kind"""
    ).fetchall()]


def graveyard_by_tname(conn: sqlite3.Connection) -> list[dict]:
    """各分区吃灰率（收藏了没看）。"""
    return [dict(r) for r in conn.execute(
        """SELECT v.tname,
                  SUM(CASE WHEN f.bvid NOT IN (SELECT bvid FROM history) THEN 1 ELSE 0 END) AS graveyard,
                  COUNT(*) AS total
           FROM fav_items f JOIN videos v ON f.bvid = v.bvid
           WHERE v.tname != ''
           GROUP BY v.tname HAVING total > 0
           ORDER BY graveyard DESC LIMIT 10"""
    ).fetchall()]


def daily_calendar(conn: sqlite3.Connection, days: int = 90) -> list[dict]:
    """最近 N 天每日观看量（热力图数据）。"""
    start = int(time.time()) - days * 86400
    return [dict(r) for r in conn.execute(
        """SELECT date(view_at, 'unixepoch', 'localtime') AS day, COUNT(*) AS n
           FROM history WHERE view_at >= ? GROUP BY day""",
        (start,),
    ).fetchall()]


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
