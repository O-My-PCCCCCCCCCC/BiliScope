"""提醒入库。"""
from __future__ import annotations

import sqlite3
import time


def add_alert(conn: sqlite3.Connection, type_: str, title: str, content: str) -> None:
    conn.execute(
        "INSERT INTO alerts (type, title, content, created_at) VALUES (?, ?, ?, ?)",
        (type_, title, content, int(time.time())),
    )
