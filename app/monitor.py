"""监测：视频失效检测、UP 主更新检测。后台线程 + 进度。"""
from __future__ import annotations

import sqlite3
import threading
import time

from app.bilibili.client import BiliClient, BiliError
from app.config import get_cookies
from app.database import get_conn, init_db
from app.notify import add_alert

_monitor_status: dict = {"state": "idle", "scope": "", "progress": 0,
                         "current": "", "total": 0, "message": "", "result": None}
_monitor_thread: threading.Thread | None = None


def monitor_status() -> dict:
    return dict(_monitor_status)


def start_monitor(scope: str = "all") -> dict:
    """后台启动监测。scope: all(全部收藏) / history / 某个收藏夹 media_id。"""
    global _monitor_thread
    if _monitor_thread and _monitor_thread.is_alive():
        return {"error": "已有监测任务进行中"}
    _monitor_status.update({"state": "running", "scope": scope, "progress": 0,
                            "current": "", "total": 0, "message": "准备开始...", "result": None})
    _monitor_thread = threading.Thread(target=_monitor_run, args=(scope,), daemon=True)
    _monitor_thread.start()
    return {"ok": True}


def _monitor_run(scope: str) -> None:
    conn = get_conn()
    init_db(conn)
    try:
        with BiliClient(cookies=get_cookies()) as client:
            history_only = scope == "history"
            media_id = int(scope) if scope.isdigit() else None
            n_invalid = check_invalid(conn, client, limit=100, delay=0.3,
                                      media_id=media_id, history_only=history_only,
                                      favorites_only=(scope == "all"),
                                      progress=_monitor_status)
            _monitor_status["message"] = "失效检测完成，检查 UP 主更新..."
            n_updates = check_updates(conn, client, limit=20, delay=0.5,
                                      progress=_monitor_status)
        _monitor_status.update({"state": "done", "progress": 100,
                                "message": "监测完成", "result": {"invalid": n_invalid, "updates": n_updates}})
    except Exception as e:
        _monitor_status.update({"state": "error", "message": str(e)})
    finally:
        conn.close()


def check_invalid(conn: sqlite3.Connection, client: BiliClient,
                  limit: int = 100, delay: float = 0.3,
                  media_id: int | None = None, history_only: bool = False,
                  favorites_only: bool = False,
                  progress: dict | None = None) -> int:
    """检查视频是否失效，返回新失效数。favorites_only 只查收藏（默认推荐）。"""
    if history_only:
        rows = conn.execute(
            "SELECT DISTINCT bvid FROM history LIMIT ?", (limit,)
        ).fetchall()
    elif favorites_only or media_id:
        if media_id:
            rows = conn.execute(
                "SELECT DISTINCT bvid FROM fav_items WHERE media_id = ? LIMIT ?",
                (media_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT DISTINCT bvid FROM fav_items LIMIT ?", (limit,)
            ).fetchall()
    else:
        rows = conn.execute(
            "SELECT DISTINCT bvid FROM history "
            "UNION SELECT DISTINCT bvid FROM fav_items "
            "LIMIT ?",
            (limit,),
        ).fetchall()
    total = len(rows)
    if progress:
        progress["total"] = total
    new_invalid = 0
    now = int(time.time())
    for i, row in enumerate(rows):
        bvid = row["bvid"]
        if progress:
            progress["current"] = bvid
            progress["progress"] = min(int(i * 100 / total), 99) if total else 0
            progress["message"] = f"检查 {i + 1}/{total}"
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
            add_alert(conn, "invalid", "视频已失效", f"{bvid} 检测为失效，来源：收藏/历史")
            new_invalid += 1
        time.sleep(delay)
    conn.commit()
    return new_invalid


def check_updates(conn: sqlite3.Connection, client: BiliClient,
                  limit: int = 20, delay: float = 0.5,
                  progress: dict | None = None) -> int:
    """检查关注列表 UP 主最新投稿，有更新则写提醒。返回新提醒数。"""
    rows = conn.execute(
        "SELECT mid, uname FROM followings LIMIT ?", (limit,)
    ).fetchall()
    total = len(rows)
    if progress:
        progress["total"] = total
    new_updates = 0
    now = int(time.time())
    for i, row in enumerate(rows):
        mid = row["mid"]
        if progress:
            progress["current"] = row["uname"]
            progress["progress"] = min(int(i * 100 / total), 99) if total else 0
            progress["message"] = f"UP 主更新 {i + 1}/{total}"
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
