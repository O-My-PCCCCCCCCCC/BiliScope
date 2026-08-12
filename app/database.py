"""SQLite 数据库层。"""
from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_db_path: Path = ROOT / "data" / "bili.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    bvid TEXT PRIMARY KEY,
    title TEXT,
    up_mid INTEGER,
    up_name TEXT,
    pic TEXT,
    duration INTEGER,
    tname TEXT,
    ctime INTEGER,
    desc TEXT,
    view_count INTEGER,
    danmaku INTEGER,
    updated_at INTEGER
);
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bvid TEXT NOT NULL,
    view_at INTEGER,
    progress INTEGER,
    UNIQUE(bvid, view_at)
);
CREATE TABLE IF NOT EXISTS fav_folders (
    media_id INTEGER PRIMARY KEY,
    name TEXT,
    count INTEGER,
    created_at INTEGER
);
CREATE TABLE IF NOT EXISTS fav_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    media_id INTEGER NOT NULL,
    bvid TEXT NOT NULL,
    fav_time INTEGER,
    UNIQUE(media_id, bvid)
);
CREATE TABLE IF NOT EXISTS coins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bvid TEXT,
    coin_time INTEGER
);
CREATE TABLE IF NOT EXISTS followings (
    mid INTEGER PRIMARY KEY,
    uname TEXT,
    face TEXT
);
CREATE TABLE IF NOT EXISTS updates (
    mid INTEGER PRIMARY KEY,
    last_bvid TEXT,
    last_pubdate INTEGER,
    checked_at INTEGER
);
CREATE TABLE IF NOT EXISTS invalid_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bvid TEXT,
    source TEXT,
    checked_at INTEGER
);
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT,
    type TEXT,
    content_json TEXT,
    created_at INTEGER
);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT,
    title TEXT,
    content TEXT,
    created_at INTEGER,
    read INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS video_analysis (
    bvid TEXT PRIMARY KEY,
    tags_json TEXT,
    summary TEXT,
    analyzed_at INTEGER,
    model TEXT
);
CREATE TABLE IF NOT EXISTS account_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    coins REAL,
    level INTEGER,
    following INTEGER,
    follower INTEGER,
    bangumi INTEGER,
    drama INTEGER,
    uname TEXT,
    updated_at INTEGER
);
CREATE TABLE IF NOT EXISTS coin_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    time TEXT,
    delta REAL,
    reason TEXT,
    UNIQUE(time, delta, reason)
);
CREATE TABLE IF NOT EXISTS collections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_id INTEGER,
    title TEXT,
    cover TEXT,
    total INTEGER,
    category TEXT,
    updated_at INTEGER,
    UNIQUE(collection_id, category)
);
CREATE TABLE IF NOT EXISTS collected_folders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    media_id INTEGER,
    title TEXT,
    media_count INTEGER,
    up_name TEXT,
    updated_at INTEGER,
    UNIQUE(media_id)
);
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT,
    content TEXT,
    tool_calls_json TEXT,
    tool_call_id TEXT,
    created_at INTEGER
);
CREATE TABLE IF NOT EXISTS dynamics (
    id TEXT PRIMARY KEY,
    type TEXT,
    content TEXT,
    like_count INTEGER,
    comment_count INTEGER,
    repost_count INTEGER,
    ctime INTEGER,
    updated_at INTEGER
);
"""


def set_db_path(path: Path) -> None:
    global _db_path
    _db_path = Path(path)


def get_conn(db_path: Path | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else _db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection | None = None) -> None:
    conn = conn or get_conn()
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.commit()


def _migrate(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(videos)")}
    if "desc" not in cols:
        conn.execute("ALTER TABLE videos ADD COLUMN desc TEXT")
    if "view_count" not in cols:
        conn.execute("ALTER TABLE videos ADD COLUMN view_count INTEGER")
        conn.execute("ALTER TABLE videos ADD COLUMN danmaku INTEGER")
    acols = {r[1] for r in conn.execute("PRAGMA table_info(account_stats)")}
    if acols and "bangumi" not in acols:
        conn.execute("ALTER TABLE account_stats ADD COLUMN bangumi INTEGER")
        conn.execute("ALTER TABLE account_stats ADD COLUMN drama INTEGER")
