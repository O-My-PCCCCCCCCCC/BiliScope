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
        """INSERT INTO videos (bvid, title, up_mid, up_name, pic, duration, tname, ctime, view_count, danmaku, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(bvid) DO UPDATE SET
             title=excluded.title, up_mid=excluded.up_mid, up_name=excluded.up_name,
             pic=excluded.pic, duration=excluded.duration, tname=excluded.tname,
             ctime=excluded.ctime, view_count=excluded.view_count,
             danmaku=excluded.danmaku, updated_at=excluded.updated_at""",
        (v["bvid"], v["title"], v.get("up_mid", 0), v.get("up_name", ""),
         v.get("pic", ""), v.get("duration", 0), v.get("tname", ""),
         v.get("ctime", 0), v.get("view_count", 0), v.get("danmaku", 0),
         int(time.time())),
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


def sync_coin_log(conn: sqlite3.Connection, client: BiliClient,
                  max_pages: int = 5) -> int:
    """拉取硬币明细（投币记录）。返回新增条数。"""
    n = 0
    for page in range(1, max_pages + 1):
        data = client.get_json("/x/member/web/coin/log", {"page": page})
        items = (data.get("data") or {}).get("list") or []
        if not items:
            break
        for it in items:
            cur = conn.execute(
                "INSERT OR IGNORE INTO coin_log (time, delta, reason) VALUES (?, ?, ?)",
                (it.get("time"), it.get("delta"), it.get("reason")),
            )
            n += cur.rowcount
        if len(items) < 20:
            break
    return n


def _bangumi_total(client: BiliClient, uid: int, type_: int) -> int:
    try:
        data = client.get_json(
            "/x/space/bangumi/follow/list",
            {"type": type_, "follow_status": 0, "pn": 1, "ps": 1, "vmid": uid},
        )
        return (data.get("data") or {}).get("total", 0)
    except Exception:
        return 0


def sync_account(conn: sqlite3.Connection, client: BiliClient, uid: int) -> dict:
    """采集账号信息：硬币、等级、关注/粉丝、追番/追剧订阅、硬币明细。"""
    nav = client.get_json("/x/web-interface/nav")["data"]
    coins = nav.get("money", 0)
    li = nav.get("level_info") or {}
    level = li.get("current_level", 0)
    uname = nav.get("uname", "")
    face = nav.get("face", "")
    sign = ""
    try:
        info = client.get_wbi_json("/x/space/wbi/acc/info", {"mid": uid})
        sign = (info.get("data") or {}).get("sign", "") or ""
    except Exception:
        pass
    following = conn.execute("SELECT COUNT(*) FROM followings").fetchone()[0]
    follower = 0
    try:
        rel = client.get_json("/x/relation/stat", {"vmid": uid})
        stat = rel.get("data") or {}
        follower = stat.get("follower", 0)
        following = stat.get("following", following)
    except Exception:
        pass
    bangumi = _bangumi_total(client, uid, 1)  # 追番
    drama = _bangumi_total(client, uid, 2)    # 追剧
    conn.execute(
        """INSERT INTO account_stats
           (coins, level, following, follower, bangumi, drama, uname, face, sign, current_exp, current_min, next_exp, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (coins, level, following, follower, bangumi, drama, uname, face, sign,
         li.get("current_exp"), li.get("current_min"), li.get("next_exp"), int(time.time())),
    )
    n_coins = sync_coin_log(conn, client)
    conn.commit()
    return {"coins": coins, "level": level, "following": following,
            "follower": follower, "bangumi": bangumi, "drama": drama,
            "coin_log": n_coins}


def sync_dynamics(conn: sqlite3.Connection, client: BiliClient, uid: int) -> int:
    """采集自己的动态。返回新增条数。"""
    from app import dynamics as dynamics_mod
    rows = dynamics_mod.fetch_dynamics(client, uid)
    n = 0
    now = int(time.time())
    for d in rows:
        cur = conn.execute(
            "INSERT OR IGNORE INTO dynamics (id, type, content, like_count, comment_count, repost_count, ctime, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (d["id"], d["type"], d["content"], d["like_count"],
             d["comment_count"], d["repost_count"], d["ctime"], now),
        )
        n += cur.rowcount
    conn.commit()
    return n


def sync_collections(conn: sqlite3.Connection, client: BiliClient, uid: int) -> int:
    """采集追的合集/系列。返回新增条数。"""
    data = client.get_json(
        "/x/polymer/web-space/seasons_series_list",
        {"mid": uid, "page_num": 1, "page_size": 20},
    )
    items = (data.get("data") or {}).get("items_lists") or {}
    n = 0
    now = int(time.time())
    for category, key in (("season", "seasons_list"), ("series", "series_list")):
        for it in items.get(key) or []:
            meta = it.get("meta") or {}
            cid = meta.get("id") or it.get("id")
            if not cid:
                continue
            cur = conn.execute(
                "INSERT OR IGNORE INTO collections (collection_id, title, cover, total, category, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (cid, meta.get("title", ""), meta.get("cover", ""),
                 meta.get("total", 0), category, now),
            )
            n += cur.rowcount
    conn.commit()
    return n


def sync_collected_folders(conn: sqlite3.Connection, client: BiliClient, uid: int) -> int:
    """采集收藏的收藏夹。返回新增条数。"""
    data = client.get_json(
        "/x/v3/fav/folder/collected/list", {"up_mid": uid, "pn": 1, "ps": 50}
    )
    items = (data.get("data") or {}).get("list") or []
    n = 0
    now = int(time.time())
    for f in items:
        cur = conn.execute(
            "INSERT OR IGNORE INTO collected_folders (media_id, title, media_count, up_name, updated_at) VALUES (?, ?, ?, ?, ?)",
            (f.get("id"), f.get("title", ""), f.get("media_count", 0),
             (f.get("upper") or {}).get("name", ""), now),
        )
        n += cur.rowcount
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
        n_desc = sync_descriptions(conn, client, limit=200)  # 补拉简介（内容分析用）
        n_col = sync_collections(conn, client, uid) if uid else 0
        n_cf = sync_collected_folders(conn, client, uid) if uid else 0
        n_dyn = sync_dynamics(conn, client, uid) if uid else 0
        account = sync_account(conn, client, uid) if uid else {}
        if uid:
            cfg = load_config()
            cfg["uid"] = uid
            save_config(cfg)
        conn.commit()
        return {"history": n_hist, "favorites": n_fav, "followings": n_fol,
                "descriptions": n_desc,
                "collections": n_col, "collected_folders": n_cf,
                "dynamics": n_dyn,
                "coins": account.get("coins", 0), "coin_log": account.get("coin_log", 0)}
    finally:
        conn.close()
        if own and client is not None:
            client.close()
