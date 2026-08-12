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
