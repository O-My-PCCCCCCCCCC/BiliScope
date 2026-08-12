"""数据同步编排：拉取 B 站数据并写入 SQLite。"""
from __future__ import annotations

import sqlite3
import time

from app.bilibili import favorite as favorite_mod
from app.bilibili import history as history_mod
from app.bilibili import relation as relation_mod
from app.bilibili.client import BiliClient, BiliError
from app.config import get_cookies, load_config, save_config


def upsert_video(conn: sqlite3.Connection, v: dict) -> None:
    conn.execute(
        """INSERT INTO videos (bvid, title, up_mid, up_name, pic, duration, tname, ctime, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(bvid) DO UPDATE SET
             title=excluded.title, up_mid=excluded.up_mid, up_name=excluded.up_name,
             pic=excluded.pic, duration=excluded.duration, tname=excluded.tname,
             ctime=excluded.ctime, updated_at=excluded.updated_at""",
        (v["bvid"], v["title"], v.get("up_mid", 0), v.get("up_name", ""),
         v.get("pic", ""), v.get("duration", 0), v.get("tname", ""),
         v.get("ctime", 0), int(time.time())),
    )


def sync_history(conn: sqlite3.Connection, client: BiliClient) -> int:
    rows = history_mod.fetch_history(client)
    n = 0
    for v in rows:
        upsert_video(conn, v)
        cur = conn.execute(
            "INSERT OR IGNORE INTO history (bvid, view_at, progress) VALUES (?, ?, ?)",
            (v["bvid"], v["view_at"], v.get("progress", 0)),
        )
        n += cur.rowcount
    return n


def sync_favorites(conn: sqlite3.Connection, client: BiliClient, uid: int) -> int:
    folders = favorite_mod.fetch_folders(client, uid)
    conn.executemany(
        "INSERT OR REPLACE INTO fav_folders (media_id, name, count, created_at) VALUES (?, ?, ?, ?)",
        [(f["media_id"], f["name"], f["count"], f["created_at"]) for f in folders],
    )
    n = 0
    for f in folders:
        for it in favorite_mod.fetch_folder_items(client, f["media_id"]):
            upsert_video(conn, it)
            cur = conn.execute(
                "INSERT OR IGNORE INTO fav_items (media_id, bvid, fav_time) VALUES (?, ?, ?)",
                (it["media_id"], it["bvid"], it.get("fav_time", 0)),
            )
            n += cur.rowcount
    return n


def sync_followings(conn: sqlite3.Connection, client: BiliClient, uid: int) -> int:
    rows = relation_mod.fetch_followings(client, uid)
    conn.executemany(
        "INSERT OR REPLACE INTO followings (mid, uname, face) VALUES (?, ?, ?)",
        [(r["mid"], r["uname"], r["face"]) for r in rows],
    )
    return len(rows)


def sync_descriptions(conn: sqlite3.Connection, client: BiliClient,
                      limit: int = 100, delay: float = 0.3) -> int:
    """补拉视频简介（videos.desc）。返回更新的条数。"""
    rows = conn.execute(
        "SELECT bvid FROM videos WHERE desc IS NULL OR desc = '' LIMIT ?",
        (limit,),
    ).fetchall()
    n = 0
    for row in rows:
        try:
            data = client.get_json("/x/web-interface/view", {"bvid": row["bvid"]})
            desc = data.get("data", {}).get("desc", "")
            if desc:
                conn.execute("UPDATE videos SET desc = ? WHERE bvid = ?", (desc, row["bvid"]))
                n += 1
        except BiliError:
            continue
        time.sleep(delay)
    conn.commit()
    return n


def run_full_sync(client: BiliClient | None = None) -> dict:
    """执行完整同步，返回各数据源的新增条数。未登录抛 BiliError。"""
    from app.database import get_conn, init_db

    cookies = get_cookies()
    if not cookies:
        raise BiliError("未登录，请先扫码登录")

    own = client is None
    client = client or BiliClient(cookies=cookies)
    conn = get_conn()
    init_db(conn)
    try:
        nav = client.get_json("/x/web-interface/nav")
        uid = nav.get("data", {}).get("mid", 0)
        n_hist = sync_history(conn, client)
        n_fav = sync_favorites(conn, client, uid) if uid else 0
        n_fol = sync_followings(conn, client, uid) if uid else 0
        if uid:
            cfg = load_config()
            cfg["uid"] = uid
            save_config(cfg)
        conn.commit()
        return {"history": n_hist, "favorites": n_fav, "followings": n_fol}
    finally:
        conn.close()
        if own and client is not None:
            client.close()
