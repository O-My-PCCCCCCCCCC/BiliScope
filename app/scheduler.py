"""APScheduler 定时任务。"""
from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler

_scheduler: BackgroundScheduler | None = None


def start_scheduler() -> BackgroundScheduler:
    """幂等启动后台调度器，注册同步/失效检测/UP 主更新任务。"""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        return _scheduler

    from app.bilibili.client import BiliClient
    from app.config import get_cookies
    from app.database import get_conn, init_db
    from app.emailer import send_report_email
    from app.monitor import check_invalid, check_updates
    from app.report import generate_report
    from app.sync import run_full_sync


    def job_sync() -> None:
        if not get_cookies():
            return
        try:
            run_full_sync()
        except Exception:
            pass


    def job_invalid() -> None:
        if not get_cookies():
            return
        try:
            conn = get_conn()
            init_db(conn)
            with BiliClient(cookies=get_cookies()) as client:
                check_invalid(conn, client, limit=200)
            conn.close()
        except Exception:
            pass


    def job_updates() -> None:
        if not get_cookies():
            return
        try:
            conn = get_conn()
            init_db(conn)
            with BiliClient(cookies=get_cookies()) as client:
                check_updates(conn, client, limit=30)
            conn.close()
        except Exception:
            pass

    def job_report(kind: str) -> None:
        try:
            conn = get_conn()
            init_db(conn)
            report = generate_report(conn, kind)
            conn.close()
            send_report_email(report)
        except Exception:
            pass

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(job_sync, "cron", hour=3, minute=0, id="sync")
    _scheduler.add_job(job_invalid, "cron", hour=4, minute=0, id="invalid")
    _scheduler.add_job(job_updates, "interval", hours=6, id="updates")
    _scheduler.add_job(lambda: job_report("weekly"), "cron", day_of_week="sun", hour=5, minute=0, id="report_weekly")
    _scheduler.add_job(lambda: job_report("monthly"), "cron", day=1, hour=5, minute=0, id="report_monthly")
    _scheduler.start()
    return _scheduler
