from __future__ import annotations

import pathlib
import smtplib
import tempfile
from unittest import mock

from app import config, emailer


def test_send_email_calls_smtp():
    smtp_cfg = {"host": "smtp.qq.com", "port": 465, "user": "a@qq.com",
                "password": "secret", "to": "b@qq.com"}
    sent = {}

    class FakeSMTP:
        def __init__(self, *a, **kw):
            sent["args"] = a
            sent["kw"] = kw
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def login(self, u, p): sent["login"] = (u, p)
        def sendmail(self, frm, to, msg): sent["sendmail"] = (frm, to, msg)

    with mock.patch.object(smtplib, "SMTP_SSL", FakeSMTP):
        emailer.send_email(smtp_cfg, "测试", "<b>hi</b>")

    from email import policy
    from email.parser import BytesParser

    assert sent["args"][0] == "smtp.qq.com"
    assert sent["login"] == ("a@qq.com", "secret")
    assert sent["sendmail"][1] == ["b@qq.com"]
    # 解析并解码传输编码，校验正文
    msg = BytesParser(policy=policy.default).parsebytes(sent["sendmail"][2].encode())
    assert msg.get_body(preferencelist=("html",)).get_content() == "<b>hi</b>"


def test_send_report_email_skips_without_config():
    config.set_config_path(pathlib.Path(tempfile.mkdtemp()) / "config.json")
    config.save_config({"smtp": {"host": "", "port": 465, "user": "", "password": "", "to": ""}})
    assert emailer.send_report_email({"period": "x", "type": "weekly", "stats": {}}) is False
