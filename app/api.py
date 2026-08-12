"""REST API 路由。"""
from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Query

from app.bilibili import login as login_mod
from app.bilibili.client import BiliError
from app.config import get_cookies, load_config
from app.database import get_conn, init_db
from app.sync import run_full_sync

router = APIRouter(prefix="/api")

# 登录会话缓存：qrcode_key -> QRLogin，保证 generate/poll 共用同一 session
_login_clients: dict[str, login_mod.QRLogin] = {}


@router.get("/ping")
def ping() -> dict:
    return {"ok": True}


@router.get("/status")
def status() -> dict:
    cfg = load_config()
    logged_in = bool(cfg.get("cookies"))
    conn = get_conn()
    init_db(conn)
    try:
        counts = {
            "history": conn.execute("SELECT COUNT(*) FROM history").fetchone()[0],
            "favorites": conn.execute("SELECT COUNT(*) FROM fav_items").fetchone()[0],
            "followings": conn.execute("SELECT COUNT(*) FROM followings").fetchone()[0],
            "folders": conn.execute("SELECT COUNT(*) FROM fav_folders").fetchone()[0],
        }
    finally:
        conn.close()
    return {
        "logged_in": logged_in,
        "login_at": cfg.get("login_at"),
        "uid": cfg.get("uid"),
        "counts": counts,
    }


@router.get("/login/qrcode")
def login_qrcode() -> dict:
    ql = login_mod.QRLogin()
    data = ql.generate()
    _login_clients[data["qrcode_key"]] = ql
    return {"url": data["url"], "qrcode_key": data["qrcode_key"]}


@router.get("/login/poll")
def login_poll(qrcode_key: str = Query(...)) -> dict:
    ql = _login_clients.get(qrcode_key) or login_mod.QRLogin()
    result = ql.poll(qrcode_key)
    if result["status"] in ("ok", "expired"):
        _login_clients.pop(qrcode_key, None)
    return result


@router.post("/sync")
def trigger_sync() -> dict:
    if not get_cookies():
        raise HTTPException(status_code=401, detail="未登录，请先扫码登录")
    try:
        return run_full_sync()
    except BiliError as e:
        raise HTTPException(status_code=502, detail=f"同步失败: {e}")


@router.get("/history")
def history(
    search: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    conn = get_conn()
    init_db(conn)
    try:
        where = ""
        params: list = []
        if search:
            where = "WHERE v.title LIKE ? OR v.up_name LIKE ?"
            like = f"%{search}%"
            params = [like, like]
        total = conn.execute(
            f"SELECT COUNT(*) FROM history h JOIN videos v ON h.bvid = v.bvid {where}",
            params,
        ).fetchone()[0]
        rows = conn.execute(
            f"""SELECT h.bvid, h.view_at, h.progress,
                       v.title, v.up_name, v.pic, v.duration, v.tname
                FROM history h JOIN videos v ON h.bvid = v.bvid
                {where}
                ORDER BY h.view_at DESC
                LIMIT ? OFFSET ?""",
            params + [page_size, (page - 1) * page_size],
        ).fetchall()
    finally:
        conn.close()
    return {"total": total, "items": [dict(r) for r in rows]}


@router.get("/favorites")
def favorites() -> list:
    conn = get_conn()
    init_db(conn)
    try:
        rows = conn.execute("SELECT * FROM fav_folders ORDER BY created_at DESC").fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


@router.get("/favorites/{media_id}")
def favorite_items(
    media_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict:
    conn = get_conn()
    init_db(conn)
    try:
        total = conn.execute(
            "SELECT COUNT(*) FROM fav_items WHERE media_id = ?", (media_id,)
        ).fetchone()[0]
        rows = conn.execute(
            """SELECT f.media_id, f.bvid, f.fav_time,
                      v.title, v.up_name, v.pic, v.tname, v.duration
               FROM fav_items f LEFT JOIN videos v ON f.bvid = v.bvid
               WHERE f.media_id = ?
               ORDER BY f.fav_time DESC
               LIMIT ? OFFSET ?""",
            (media_id, page_size, (page - 1) * page_size),
        ).fetchall()
    finally:
        conn.close()
    return {"total": total, "items": [dict(r) for r in rows]}


@router.get("/followings")
def followings() -> list:
    conn = get_conn()
    init_db(conn)
    try:
        rows = conn.execute(
            "SELECT * FROM followings ORDER BY uname LIMIT 5000"
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


@router.get("/stats/overview")
def stats_overview() -> dict:
    conn = get_conn()
    init_db(conn)
    try:
        counts = {
            "history": conn.execute("SELECT COUNT(*) FROM history").fetchone()[0],
            "favorites": conn.execute("SELECT COUNT(*) FROM fav_items").fetchone()[0],
            "followings": conn.execute("SELECT COUNT(*) FROM followings").fetchone()[0],
            "folders": conn.execute("SELECT COUNT(*) FROM fav_folders").fetchone()[0],
        }
        week_ago = int(time.time()) - 30 * 86400
        trend = conn.execute(
            """SELECT date(view_at, 'unixepoch', 'localtime') AS day, COUNT(*) AS n
               FROM history WHERE view_at >= ?
               GROUP BY day ORDER BY day""",
            (week_ago,),
        ).fetchall()
        top_ups = conn.execute(
            """SELECT v.up_name, COUNT(*) AS n
               FROM history h JOIN videos v ON h.bvid = v.bvid
               GROUP BY v.up_mid, v.up_name
               ORDER BY n DESC LIMIT 10"""
        ).fetchall()
        hours = conn.execute(
            """SELECT CAST(strftime('%H', view_at, 'unixepoch', 'localtime') AS INTEGER) AS h,
                      COUNT(*) AS n
               FROM history GROUP BY h"""
        ).fetchall()
        tnames = conn.execute(
            """SELECT v.tname, COUNT(*) AS n
               FROM history h JOIN videos v ON h.bvid = v.bvid
               WHERE v.tname != ''
               GROUP BY v.tname ORDER BY n DESC LIMIT 15"""
        ).fetchall()
    finally:
        conn.close()
    return {
        "counts": counts,
        "trend": [{"day": r["day"], "n": r["n"]} for r in trend],
        "top_ups": [{"up_name": r["up_name"], "n": r["n"]} for r in top_ups],
        "hours": [{"hour": r["h"], "n": r["n"]} for r in hours],
        "tnames": [{"tname": r["tname"], "n": r["n"]} for r in tnames],
    }
