"""监测：视频失效检测、UP 主更新检测。"""
from __future__ import annotations

import sqlite3
import time

from app.bilibili.client import BiliClient, BiliError
from app.notify import add_alert


def check_invalid(conn: sqlite3.Connection, client: BiliClient,
                  limit: int = 100, delay: float = 0.3) -> int:
    """检查历史+收藏中的视频是否失效，返回新失效数。"""
    rows = conn.execute(
        "SELECT DISTINCT bvid FROM history "
        "UNION SELECT DISTINCT bvid FROM fav_items "
        "LIMIT ?",
        (limit,),
    ).fetchall()
    new_invalid = 0
    now = int(time.time())
    for row in rows:
        bvid = row["bvid"]
        if conn.execute(
            "SELECT 1 FROM invalid_items WHERE bvid = ?", (bvid,)
        ).fetchone():
            continue
        try:
            client.get_json("/x/web-interface/view", {"bvid": bvid})
        except BiliError as e:
            if e.code != -404:
                continue
            conn.execute(
                "INSERT INTO invalid_items (bvid, source, checked_at) VALUES (?, 'check', ?)",
                (bvid, now),
            )
            add_alert(conn, "invalid", "视频已失效", f"{bvid} 检测为失效，来源：历史/收藏")
            new_invalid += 1
        time.sleep(delay)
    conn.commit()
    return new_invalid


def check_updates(conn: sqlite3.Connection, client: BiliClient,
                  limit: int = 20, delay: float = 0.5) -> int:
    """检查关注列表 UP 主最新投稿，有更新则写提醒。返回新提醒数。"""
    rows = conn.execute(
        "SELECT mid, uname FROM followings LIMIT ?", (limit,)
    ).fetchall()
    new_updates = 0
    now = int(time.time())
    for row in rows:
        mid = row["mid"]
        try:
            data = client.get_wbi_json(
                "/x/space/wbi/arc/search",
                {"mid": mid, "pn": 1, "ps": 1, "order": "pubdate"},
            )
            vlist = (data.get("data", {}).get("list") or {}).get("vlist") or []
            if not vlist:
                continue
            v = vlist[0]
            bvid = v["bvid"]
            cur = conn.execute(
                "SELECT last_bvid FROM updates WHERE mid = ?", (mid,)
            ).fetchone()
            if cur is None:
                conn.execute(
                    "INSERT INTO updates (mid, last_bvid, last_pubdate, checked_at) VALUES (?, ?, ?, ?)",
                    (mid, bvid, v.get("created", 0), now),
                )
            elif cur["last_bvid"] != bvid:
                conn.execute(
                    "UPDATE updates SET last_bvid = ?, last_pubdate = ?, checked_at = ? WHERE mid = ?",
                    (bvid, v.get("created", 0), now, mid),
                )
                add_alert(conn, "update", f"{row['uname']} 发布了新视频",
                          f"{v.get('title', '')} ({bvid})")
                new_updates += 1
            else:
                conn.execute("UPDATE updates SET checked_at = ? WHERE mid = ?", (now, mid))
        except Exception:
            continue
        time.sleep(delay)
    conn.commit()
    return new_updates
