"""SQLite 数据库层。"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_db_path: Path = ROOT / "data" / "bili.db"


def set_db_path(path: Path) -> None:
    global _db_path
    _db_path = Path(path)


def init_db() -> None:
    raise NotImplementedError("Task 2 实现")


def get_conn():
    raise NotImplementedError("Task 2 实现")
