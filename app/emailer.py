"""邮件通知（SMTP）。"""
from __future__ import annotations

import smtplib
from email.header import Header
from email.mime.text import MIMEText

from app.config import load_config


def send_email(cfg: dict, subject: str, html: str) -> None:
    host = cfg["host"]
    port = int(cfg.get("port", 465))
    user = cfg["user"]
    password = cfg["password"]
    to = cfg["to"]
    msg = MIMEText(html, "html", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = user
    msg["To"] = to
    with smtplib.SMTP_SSL(host, port, timeout=15) as s:
        s.login(user, password)
        s.sendmail(user, [to], msg.as_string())


def _smtp_ready() -> dict | None:
    cfg = load_config().get("smtp") or {}
    if cfg.get("host") and cfg.get("user") and cfg.get("password") and cfg.get("to"):
        return cfg
    return None


def send_report_email(report: dict) -> bool:
    """把报告发到邮箱；未配置 SMTP 则跳过。"""
    cfg = _smtp_ready()
    if not cfg:
        return False
    from app.report import report_to_html
    html = report_to_html(report["stats"], report["period"])
    send_email(cfg, f"BiliScope {report['type']} 观看报告", html)
    return True


def send_alerts_email(alerts: list[dict]) -> bool:
    """把未读提醒发到邮箱；未配置 SMTP 则跳过。"""
    cfg = _smtp_ready()
    if not cfg or not alerts:
        return False
    lines = "".join(
        f"<li><b>{a['title']}</b>：{a.get('content', '')}</li>" for a in alerts
    )
    send_email(cfg, f"BiliScope 提醒（{len(alerts)} 条）", f"<ul>{lines}</ul>")
    return True
