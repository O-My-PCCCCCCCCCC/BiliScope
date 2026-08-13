"""REST API 路由。"""
from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel

from app.analyze import (aggregate_themes, analysis_stats, analyze_unanalyzed,
                         category_distribution, collect_up_followers, daily_calendar, fav_growth,
                         fav_tnames, graveyard_by_tname, graveyard_list, monthly_compare,
                         monthly_trend, popularity, time_buckets, up_depth, up_follower_trend,
                         watch_completion, watch_profile, weekday_weekend)
from app.bilibili import login as login_mod
from app.bilibili.client import BiliError, UA
from app.config import get_cookies, load_config, save_config
from app.database import get_conn, init_db
from app.hardware import detect_hardware, recommend_models, recommend_ollama_model
from app.llm import get_llm_client
from app.insights.cross_time import time_content_cross
from app.insights.interest import interest_drift
from app.insights.time_invest import time_invest
from app.monitor import check_invalid, check_updates
from app.report import generate_report
from app.sync import run_full_sync

MASKED = "******"


class SmtpPayload(BaseModel):
    host: str | None = None
    port: int | None = None
    user: str | None = None
    password: str | None = None
    to: str | None = None


class LlmPayload(BaseModel):
    provider: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None


class ConfigPayload(BaseModel):
    smtp: SmtpPayload | None = None
    llm: LlmPayload | None = None


class ChatPayload(BaseModel):
    message: str

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
        alerts_unread = conn.execute(
            "SELECT COUNT(*) FROM alerts WHERE read = 0"
        ).fetchone()[0]
    finally:
        conn.close()
    return {
        "logged_in": logged_in,
        "login_at": cfg.get("login_at"),
        "uid": cfg.get("uid"),
        "counts": counts,
        "alerts_unread": alerts_unread,
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


@router.get("/alerts")
def alerts(unread_only: bool = False) -> dict:
    conn = get_conn()
    init_db(conn)
    try:
        where = "WHERE read = 0" if unread_only else ""
        unread = conn.execute("SELECT COUNT(*) FROM alerts WHERE read = 0").fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM alerts {where} ORDER BY created_at DESC LIMIT 100"
        ).fetchall()
    finally:
        conn.close()
    return {"unread": unread, "items": [dict(r) for r in rows]}


@router.post("/alerts/{alert_id}/read")
def alert_read(alert_id: int) -> dict:
    conn = get_conn()
    init_db(conn)
    try:
        conn.execute("UPDATE alerts SET read = 1 WHERE id = ?", (alert_id,))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


@router.post("/monitor/run")
def monitor_run(scope: str = "all") -> dict:
    if not get_cookies():
        raise HTTPException(status_code=401, detail="未登录，请先扫码登录")
    conn = get_conn()
    init_db(conn)
    try:
        from app.bilibili.client import BiliClient
        with BiliClient(cookies=get_cookies()) as client:
            history_only = scope == "history"
            media_id = int(scope) if scope.isdigit() else None
            n_invalid = check_invalid(conn, client, limit=100,
                                      media_id=media_id, history_only=history_only)
            n_updates = check_updates(conn, client, limit=20)
    finally:
        conn.close()
    return {"invalid": n_invalid, "updates": n_updates}


@router.get("/monitor/invalid")
def monitor_invalid() -> list:
    conn = get_conn()
    init_db(conn)
    try:
        rows = conn.execute(
            "SELECT * FROM invalid_items ORDER BY checked_at DESC LIMIT 200"
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


@router.get("/monitor/updates")
def monitor_updates() -> list:
    conn = get_conn()
    init_db(conn)
    try:
        rows = conn.execute(
            """SELECT u.*, f.uname FROM updates u
               JOIN followings f ON u.mid = f.mid
               ORDER BY u.checked_at DESC LIMIT 200"""
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


@router.post("/reports/generate")
def report_generate(type: str = Query("weekly")) -> dict:
    conn = get_conn()
    init_db(conn)
    try:
        return generate_report(conn, type)
    finally:
        conn.close()


@router.get("/reports")
def reports_list() -> list:
    conn = get_conn()
    init_db(conn)
    try:
        rows = conn.execute(
            "SELECT id, period, type, created_at FROM reports ORDER BY created_at DESC LIMIT 100"
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


@router.get("/reports/{report_id}")
def report_detail(report_id: int) -> dict:
    import json
    conn = get_conn()
    init_db(conn)
    try:
        row = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    d = dict(row)
    d["stats"] = json.loads(d.pop("content_json"))
    return d


@router.get("/config")
def config_get() -> dict:
    cfg = load_config()
    smtp = dict(cfg.get("smtp") or {})
    smtp["password"] = MASKED if smtp.get("password") else ""
    llm = dict(cfg.get("llm") or {})
    if llm.get("api_key"):
        llm["api_key"] = MASKED
    return {"smtp": smtp, "llm": llm, "task_interval": cfg.get("task_interval")}


@router.post("/config")
def config_save(payload: ConfigPayload) -> dict:
    cfg = load_config()
    smtp = cfg.setdefault("smtp", {})
    if payload.smtp:
        data = payload.smtp.model_dump()
        for k in ("host", "port", "user", "to"):
            if data.get(k) is not None:
                smtp[k] = data[k]
        pw = data.get("password")
        if pw and pw != MASKED:
            smtp["password"] = pw
    llm = cfg.setdefault("llm", {})
    if payload.llm:
        data = payload.llm.model_dump()
        for k in ("provider", "base_url", "model"):
            if data.get(k) is not None:
                llm[k] = data[k]
        key = data.get("api_key")
        if key and key != MASKED:
            llm["api_key"] = key
    save_config(cfg)
    return {"ok": True}


@router.post("/config/test-email")
def config_test_email() -> dict:
    from app.emailer import send_email
    cfg = load_config().get("smtp") or {}
    if not (cfg.get("host") and cfg.get("user") and cfg.get("password") and cfg.get("to")):
        raise HTTPException(status_code=400, detail="SMTP 配置不完整")
    try:
        send_email(cfg, "BiliScope 测试邮件", "<p>邮件配置正常 ✅</p>")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"发送失败: {e}")
    return {"ok": True}


@router.post("/analysis/run")
def analysis_run(limit: int = Query(50, ge=1, le=200)) -> dict:
    if not get_cookies():
        raise HTTPException(status_code=401, detail="未登录，请先扫码登录")
    llm_cfg = load_config().get("llm") or {}
    if not llm_cfg.get("provider"):
        raise HTTPException(status_code=400, detail="未配置 LLM，请先在设置中选择")
    conn = get_conn()
    init_db(conn)
    try:
        n = analyze_unanalyzed(conn, get_llm_client(llm_cfg), limit=limit)
    finally:
        conn.close()
    return {"analyzed": n}


@router.get("/analysis/compare")
def analysis_compare() -> dict:
    conn = get_conn()
    init_db(conn)
    try:
        return {"compare": monthly_compare(conn), "fav_growth": fav_growth(conn)}
    finally:
        conn.close()


@router.post("/analysis/up-followers")
def analysis_up_followers() -> dict:
    if not get_cookies():
        raise HTTPException(status_code=401, detail="未登录")
    conn = get_conn()
    init_db(conn)
    try:
        from app.bilibili.client import BiliClient
        with BiliClient(cookies=get_cookies()) as client:
            n = collect_up_followers(conn, client, limit=20)
        trend = up_follower_trend(conn)
    finally:
        conn.close()
    return {"collected": n, "trend": trend}


@router.get("/analysis/up-followers")
def analysis_up_followers_get() -> list:
    conn = get_conn()
    init_db(conn)
    try:
        return up_follower_trend(conn)
    finally:
        conn.close()


@router.get("/search")
def search(q: str = Query(...)) -> dict:
    like = f"%{q}%"
    conn = get_conn()
    init_db(conn)
    try:
        history = [dict(r) for r in conn.execute(
            """SELECT h.bvid, h.view_at, v.title, v.up_name, v.pic, v.duration
               FROM history h JOIN videos v ON h.bvid = v.bvid
               WHERE v.title LIKE ? OR v.up_name LIKE ?
               ORDER BY h.view_at DESC LIMIT 20""", (like, like)).fetchall()]
        favorites = [dict(r) for r in conn.execute(
            """SELECT f.media_id, f.bvid, v.title, v.up_name, v.pic
               FROM fav_items f LEFT JOIN videos v ON f.bvid = v.bvid
               WHERE v.title LIKE ? OR v.up_name LIKE ? LIMIT 20""", (like, like)).fetchall()]
        followings = [dict(r) for r in conn.execute(
            "SELECT mid, uname FROM followings WHERE uname LIKE ? LIMIT 20", (like,)).fetchall()]
    finally:
        conn.close()
    return {"history": history, "favorites": favorites, "followings": followings}


@router.get("/analysis/detailed")
def analysis_detailed() -> dict:
    conn = get_conn()
    init_db(conn)
    try:
        return {
            "completion": watch_completion(conn),
            "time_buckets": time_buckets(conn),
            "up_depth": up_depth(conn),
            "popularity": popularity(conn),
            "weekday_weekend": weekday_weekend(conn),
            "graveyard_by_tname": graveyard_by_tname(conn),
            "calendar": daily_calendar(conn),
        }
    finally:
        conn.close()


@router.get("/analysis/monthly")
def analysis_monthly() -> list:
    conn = get_conn()
    init_db(conn)
    try:
        return monthly_trend(conn)
    finally:
        conn.close()


@router.get("/analysis/profile")
def analysis_profile() -> dict:
    conn = get_conn()
    init_db(conn)
    try:
        return watch_profile(conn)
    finally:
        conn.close()


@router.get("/analysis/fav-tnames")
def analysis_fav_tnames() -> list:
    conn = get_conn()
    init_db(conn)
    try:
        return fav_tnames(conn)
    finally:
        conn.close()


@router.get("/analysis/graveyard-list")
def analysis_graveyard_list() -> list:
    conn = get_conn()
    init_db(conn)
    try:
        return graveyard_list(conn)
    finally:
        conn.close()


@router.get("/analysis/category")
def analysis_category() -> dict:
    conn = get_conn()
    init_db(conn)
    try:
        return category_distribution(conn)
    finally:
        conn.close()


@router.get("/analysis/themes")
def analysis_themes() -> list:
    conn = get_conn()
    init_db(conn)
    try:
        return aggregate_themes(conn)
    finally:
        conn.close()


@router.get("/analysis/status")
def analysis_status() -> dict:
    conn = get_conn()
    init_db(conn)
    try:
        return analysis_stats(conn)
    finally:
        conn.close()


@router.get("/insights/interest")
def insights_interest(months: int = Query(12, ge=1, le=36)) -> dict:
    conn = get_conn()
    init_db(conn)
    try:
        return interest_drift(conn, months=months)
    finally:
        conn.close()


@router.get("/insights/cross")
def insights_cross(dim: str = Query("tname")) -> dict:
    if dim not in ("tname", "category"):
        raise HTTPException(status_code=400, detail="dim 仅支持 tname / category")
    conn = get_conn()
    init_db(conn)
    try:
        return time_content_cross(conn, dim=dim)
    finally:
        conn.close()


@router.get("/insights/invest")
def insights_invest() -> dict:
    conn = get_conn()
    init_db(conn)
    try:
        return time_invest(conn)
    finally:
        conn.close()


@router.get("/account")
def account_info() -> dict:
    conn = get_conn()
    init_db(conn)
    try:
        row = conn.execute(
            "SELECT * FROM account_stats ORDER BY id DESC LIMIT 1"
        ).fetchone()
        logs = conn.execute(
            "SELECT * FROM coin_log ORDER BY id DESC LIMIT 100"
        ).fetchall()
    finally:
        conn.close()
    stats = dict(row) if row else None
    if stats:
        stats["lv_prediction"] = _lv_prediction(stats)
    return {"stats": stats, "coin_log": [dict(r) for r in logs]}


@router.post("/report/weekly-ai")
def report_weekly_ai() -> dict:
    if not get_cookies():
        raise HTTPException(status_code=401, detail="未登录，请先扫码登录")
    llm_cfg = load_config().get("llm") or {}
    if not llm_cfg.get("provider"):
        raise HTTPException(status_code=400, detail="未配置 LLM，请先在设置中选择")
    conn = get_conn()
    init_db(conn)
    try:
        from app.report import generate_weekly_ai
        result = generate_weekly_ai(conn, get_llm_client(llm_cfg))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI 周报生成失败: {e}")
    finally:
        conn.close()
    return result


def _lv_prediction(stats: dict) -> dict:
    """根据当前经验预测到 LV6 的时间（估算）。"""
    level = stats.get("level") or 0
    cur = stats.get("current_exp") or 0
    if level >= 6:
        return {"level6": True, "text": "已达 LV6"}
    need = 28800 - cur  # LV6 门槛经验
    days = max(1, round(need / 15))  # 按日均 15 exp 估算
    return {"level6": False, "need_exp": need, "days": days,
            "text": f"距 LV6 还需约 {need} exp，按日均 15 exp 估算约 {days} 天（{days / 365:.1f} 年）"}


@router.get("/hardware")
def hardware() -> dict:
    hw = detect_hardware()
    hw["recommended_model"] = recommend_ollama_model(hw)
    return hw


@router.get("/models/recommend")
def models_recommend() -> dict:
    hw = detect_hardware()
    models = recommend_models(hw, max_ram_ratio=0.85, limit=5)
    from app.ollama_manager import ollama_installed
    return {
        "hardware": {"cpu": hw.get("cpu"), "ram_gb": hw.get("ram_gb"), "gpu": hw.get("gpu")},
        "max_ram_ratio": 0.85,
        "ollama_installed": ollama_installed(),
        "models": models,
    }


@router.post("/ollama/install")
def ollama_install() -> dict:
    from app.ollama_manager import start_ollama_install
    return start_ollama_install()


@router.post("/models/install")
def models_install(payload: dict) -> dict:
    model = (payload or {}).get("model", "")
    if not model:
        raise HTTPException(status_code=400, detail="缺少 model 参数")
    from app.ollama_manager import start_model_install
    result = start_model_install(model)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    # 安装完成后设为默认本地模型
    cfg = load_config()
    llm = cfg.setdefault("llm", {})
    llm["provider"] = "ollama"
    llm["model"] = model
    save_config(cfg)
    return {"ok": True}


@router.get("/models/install-status")
def models_install_status() -> dict:
    from app.ollama_manager import install_status
    return install_status()


@router.get("/img")
def img_proxy(url: str = Query(...)) -> Response:
    """图片代理：B 站 CDN 防盗链，带 bilibili Referer 抓取，磁盘缓存加速。"""
    if "hdslb.com" not in url:
        raise HTTPException(status_code=400, detail="非法图片地址")
    import hashlib
    import httpx
    from app.config import DATA_DIR

    cache_dir = DATA_DIR / "data" / "img_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.md5(url.encode()).hexdigest()
    cache_path = cache_dir / f"{key}.img"

    def _sniff_ct(b: bytes) -> str:
        if b[:3] == b"\xff\xd8\xff":
            return "image/jpeg"
        if b[:8] == b"\x89PNG\r\n\x1a\n":
            return "image/png"
        if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
            return "image/webp"
        return "image/jpeg"

    if cache_path.exists():
        content = cache_path.read_bytes()
    else:
        resp = httpx.get(
            url,
            headers={"Referer": "https://www.bilibili.com/", "User-Agent": UA},
            timeout=15,
        )
        content = resp.content
        if resp.status_code == 200 and content:
            cache_path.write_bytes(content)
    return Response(
        content=content,
        media_type=_sniff_ct(content),
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.post("/chat")
def chat_post(payload: ChatPayload) -> dict:
    if not get_cookies():
        raise HTTPException(status_code=401, detail="未登录，请先扫码登录")
    llm_cfg = load_config().get("llm") or {}
    if not llm_cfg.get("provider"):
        raise HTTPException(status_code=400, detail="未配置 LLM，请先在设置中选择")
    from app import chat as chat_mod
    try:
        result = chat_mod.run_chat(get_llm_client(llm_cfg), chat_mod.get_history(), payload.message)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI 调用失败: {e}")
    return {"reply": result["reply"], "tool_uses": result["tool_uses"]}


@router.get("/chat/history")
def chat_history() -> dict:
    from app import chat as chat_mod
    return {"messages": chat_mod.get_history()}


@router.post("/chat/reset")
def chat_reset() -> dict:
    from app import chat as chat_mod
    chat_mod.reset_session()
    return {"ok": True}


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
                       v.title, v.up_name, v.pic, v.duration, v.tname,
                       v.view_count, v.danmaku
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


@router.get("/dynamics")
def dynamics_list() -> list:
    conn = get_conn()
    init_db(conn)
    try:
        rows = conn.execute(
            "SELECT * FROM dynamics ORDER BY ctime DESC LIMIT 200"
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


@router.get("/analysis/deep")
def analysis_deep() -> dict:
    conn = get_conn()
    init_db(conn)
    try:
        duration = [dict(r) for r in conn.execute(
            """SELECT CASE WHEN v.duration < 300 THEN '<5分钟'
                           WHEN v.duration < 900 THEN '5-15分钟'
                           WHEN v.duration < 1800 THEN '15-30分钟'
                           WHEN v.duration < 3600 THEN '30-60分钟'
                           ELSE '>60分钟' END AS bucket, COUNT(*) AS n
               FROM history h JOIN videos v ON h.bvid = v.bvid
               WHERE v.duration > 0
               GROUP BY bucket"""
        ).fetchall()]
        weekdays = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"]
        weekday = [dict(r) for r in conn.execute(
            """SELECT CAST(strftime('%w', view_at, 'unixepoch', 'localtime') AS INTEGER) AS w,
                      COUNT(*) AS n FROM history GROUP BY w"""
        ).fetchall()]
        up_watch = [dict(r) for r in conn.execute(
            """SELECT v.up_name, COUNT(*) AS cnt, SUM(v.duration) AS total_sec
               FROM history h JOIN videos v ON h.bvid = v.bvid
               WHERE v.up_name != '' AND v.duration > 0
               GROUP BY v.up_name ORDER BY total_sec DESC LIMIT 10"""
        ).fetchall()]
        graveyard = conn.execute(
            """SELECT COUNT(*) FROM fav_items f
               WHERE f.bvid NOT IN (SELECT bvid FROM history)"""
        ).fetchone()[0]
        total_fav = conn.execute("SELECT COUNT(*) FROM fav_items").fetchone()[0]
    finally:
        conn.close()
    return {
        "duration": duration,
        "weekday": [{"w": weekdays[r["w"]], "n": r["n"]} for r in weekday],
        "up_watch": up_watch,
        "graveyard": {"count": graveyard, "total": total_fav},
    }


@router.post("/downloads/run")
def downloads_run(payload: dict) -> dict:
    from app.downloader import start_download
    urls = (payload or {}).get("urls", [])
    fmt = (payload or {}).get("fmt", "mp4")
    if not urls:
        raise HTTPException(status_code=400, detail="缺少 urls")
    result = start_download(urls, fmt)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return {"ok": True}


@router.get("/downloads/status")
def downloads_status() -> dict:
    from app.downloader import download_status
    return download_status()


@router.get("/downloads/list")
def downloads_list() -> list:
    from app.downloader import list_downloads
    return list_downloads()


@router.get("/collections")
def collections() -> list:
    conn = get_conn()
    init_db(conn)
    try:
        rows = conn.execute(
            "SELECT * FROM collections ORDER BY category, collection_id"
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


@router.get("/favorites/collected")
def favorites_collected() -> list:
    conn = get_conn()
    init_db(conn)
    try:
        rows = conn.execute(
            "SELECT * FROM collected_folders ORDER BY media_id"
        ).fetchall()
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
                      v.title, v.up_name, v.pic, v.tname, v.duration,
                      v.view_count, v.danmaku
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
