# BiliScope M1（核心可用）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建成一个可本地运行、能扫码登录 B 站并拉取观看历史/收藏/关注数据、用 Web 仪表盘展示概览统计的 Python 应用。

**Architecture:** FastAPI 承载 REST API + 托管 Vue3 单页前端；数据采集用 httpx 直接调 B 站网页内部接口（扫码登录拿到 Cookie）；SQLite 存储；模块分层：`config`（配置/Cookie）→ `database`（建表）→ `bilibili/`（API 客户端与三个采集器）→ `sync`（同步编排）→ `api`（REST）→ `web/`（前端）。

**Tech Stack:** Python 3.10+，fastapi、uvicorn、httpx、pytest；前端 Vue3 + Element Plus + ECharts + qrcodejs（全部 CDN 引入，无 Node 构建链）。

**M1 里程碑范围**（来自 spec 第 15 节）：项目骨架 + 扫码登录 + 历史/收藏/关注采集 + SQLite + 概览页基本图表。M2（监测/定时）、M3（报告/邮件）、M4（打磨）另行计划。

## Global Constraints

- Python ≥ 3.10；依赖固定：`fastapi==0.115.12`、`uvicorn[standard]==0.34.0`、`httpx==0.28.1`、`pytest==8.3.5`
- 所有请求带浏览器 UA 和 `Referer: https://www.bilibili.com/`
- 敏感数据（Cookie）只存 `config.json`（已被 .gitignore 排除），绝不出现在测试提交内容中
- 测试**不得**真实请求 B 站：一律用 `httpx.MockTransport` mock
- 评论/文档使用中文，标识符与代码注释使用英文
- 每个 Task 结束时必须有可独立验证的交付物，并提交一次 git

---

### Task 1: 项目骨架与配置管理

**Files:**
- Create: `requirements.txt`
- Create: `run.py`
- Create: `app/__init__.py`
- Create: `app/config.py`
- Create: `app/main.py`
- Test: `tests/test_config.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

**Interfaces:**
- Produces:
  - `app/config.load_config() -> dict`：读 config.json，缺失时返回默认配置
  - `app/config.save_config(cfg: dict) -> None`
  - `app/config.get_cookies() -> dict`
  - `app/config.save_cookies(cookies: dict) -> None`（写入 cookies 与 login_at 时间戳）
  - `app/config.set_config_path(path: Path) -> None`（测试用）
  - `app.main:app`（FastAPI 实例，含 `GET /api/ping`）

- [ ] **Step 1: 写失败的测试**

`tests/conftest.py`：
```python
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolated_config_and_db(tmp_path, monkeypatch):
    """每个测试隔离 config.json 与 SQLite 路径。"""
    from app import config as config_mod
    from app import database as database_mod
    config_mod.set_config_path(tmp_path / "config.json")
    database_mod.set_db_path(tmp_path / "test.db")
    yield
```

`tests/test_config.py`：
```python
from __future__ import annotations

from app import config


def test_load_default_config(tmp_path):
    config.set_config_path(tmp_path / "nope.json")
    cfg = config.load_config()
    assert cfg["cookies"] == {}
    assert "smtp" in cfg


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    config.set_config_path(path)
    config.save_config({"cookies": {"SESSDATA": "abc"}})
    cfg = config.load_config()
    assert cfg["cookies"]["SESSDATA"] == "abc"


def test_save_cookies(tmp_path):
    config.set_config_path(tmp_path / "config.json")
    config.save_cookies({"SESSDATA": "xyz"})
    cfg = config.load_config()
    assert cfg["cookies"]["SESSDATA"] == "xyz"
    assert isinstance(cfg["login_at"], int)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd "d:/用户/桌面/b站账号视频分析" && python -m pytest tests/test_config.py -v`
Expected: FAIL（ImportError: 找不到 app.config）

- [ ] **Step 3: 写实现**

`requirements.txt`：
```
fastapi==0.115.12
uvicorn[standard]==0.34.0
httpx==0.28.1
pytest==8.3.5
```

`run.py`：
```python
"""一键启动 BiliScope。"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
```

`app/__init__.py`：空文件。

`app/config.py`：
```python
"""配置管理：读写 config.json，存放 Cookie 等敏感信息。"""
from __future__ import annotations

import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_config_path: Path = ROOT / "config.json"

DEFAULT_CONFIG: dict = {
    "cookies": {},
    "uid": None,
    "login_at": None,
    "smtp": {"host": "", "port": 465, "user": "", "password": "", "to": ""},
    "task_interval": {"history": "03:00", "invalid": "04:00", "updates": 6},
}


def set_config_path(path: Path) -> None:
    """测试用：重定向配置文件路径。"""
    global _config_path
    _config_path = Path(path)


def load_config() -> dict:
    if not _config_path.exists():
        return {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULT_CONFIG.items()}
    data = json.loads(_config_path.read_text(encoding="utf-8"))
    merged = {**DEFAULT_CONFIG, **data}
    merged["cookies"] = {**DEFAULT_CONFIG["cookies"], **data.get("cookies", {})}
    return merged


def save_config(cfg: dict) -> None:
    _config_path.parent.mkdir(parents=True, exist_ok=True)
    _config_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def get_cookies() -> dict:
    return load_config().get("cookies", {})


def save_cookies(cookies: dict) -> None:
    cfg = load_config()
    cfg["cookies"] = cookies
    cfg["login_at"] = int(time.time())
    save_config(cfg)
```

`app/main.py`：
```python
"""FastAPI 入口：注册 API 路由、托管前端静态文件、启动时初始化数据库。"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import router as api_router
from app.database import init_db

ROOT = Path(__file__).resolve().parent.parent


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="BiliScope", lifespan=lifespan)
app.include_router(api_router)
app.mount("/", StaticFiles(directory=str(ROOT / "web"), html=True), name="web")
```

> 注：`app.main` 依赖 `app.api` 与 `app.database`，这两个模块在 Task 2 / Task 9 才实现。为了本 Task 能独立通过，先创建 `app/api.py`、`app/database.py` 的**最小占位**（见下方），Task 2 / Task 9 会填充完整实现。

`app/database.py`（占位，Task 2 填充）：
```python
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
```

`app/api.py`（占位，Task 9 填充）：
```python
"""REST API 路由。"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api")


@router.get("/ping")
def ping() -> dict:
    return {"ok": True}
```

`tests/__init__.py`：空文件。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_config.py -v`
Expected: 3 passed

- [ ] **Step 5: 冒烟验证服务可启动**

Run: `python -c "from app.main import app; print(app.title)"`
Expected: `BiliScope`

- [ ] **Step 6: 提交**

```bash
git add requirements.txt run.py app tests
git commit -m "feat: M1 项目骨架与配置管理"
```

---

### Task 2: 数据库层

**Files:**
- Modify: `app/database.py`（替换占位）
- Test: `tests/test_database.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `app.database.get_conn(db_path=None) -> sqlite3.Connection`（row_factory=Row，自动建父目录）
  - `app.database.init_db(conn=None) -> None`（执行 SCHEMA，幂等）
  - 建表：videos / history / fav_folders / fav_items / coins / followings / updates / invalid_items / reports / alerts

- [ ] **Step 1: 写失败的测试**

`tests/test_database.py`：
```python
from __future__ import annotations

from app import database


def test_init_db_creates_tables(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"videos", "history", "fav_folders", "fav_items", "coins",
                "followings", "updates", "invalid_items", "reports", "alerts"} <= tables
    finally:
        conn.close()


def test_insert_and_query_video(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    try:
        conn.execute(
            "INSERT INTO videos (bvid, title, up_mid, up_name) VALUES (?, ?, ?, ?)",
            ("BV1", "测试视频", 1001, "阿测"),
        )
        conn.commit()
        row = conn.execute("SELECT title, up_name FROM videos WHERE bvid='BV1'").fetchone()
        assert dict(row) == {"title": "测试视频", "up_name": "阿测"}
    finally:
        conn.close()


def test_history_unique_constraint(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    try:
        conn.execute("INSERT OR IGNORE INTO history (bvid, view_at, progress) VALUES ('BV1', 100, 50)")
        conn.execute("INSERT OR IGNORE INTO history (bvid, view_at, progress) VALUES ('BV1', 100, 50)")
        conn.commit()
        n = conn.execute("SELECT COUNT(*) FROM history").fetchone()[0]
        assert n == 1
    finally:
        conn.close()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_database.py -v`
Expected: FAIL（NotImplementedError）

- [ ] **Step 3: 写实现**

`app/database.py`：
```python
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
    conn.commit()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_database.py -v`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add app/database.py tests/test_database.py
git commit -m "feat: M1 数据库层建表"
```

---

### Task 3: B 站 API 客户端

**Files:**
- Create: `app/bilibili/__init__.py`
- Create: `app/bilibili/client.py`
- Test: `tests/test_client.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `BiliError(Exception)`：接口 code 非 0 时抛出
  - `BiliClient(cookies: dict | None = None, session: httpx.Client | None = None)`
    - `.get_json(path: str, params: dict | None = None) -> dict`
    - `.is_logged_in() -> bool`
    - `.session`（httpx.Client，测试注入 MockTransport）
    - `.close()` / `__enter__` / `__exit__`
  - `app.bilibili.client.UA`（浏览器 UA 常量）

- [ ] **Step 1: 写失败的测试**

`tests/test_client.py`：
```python
from __future__ import annotations

import httpx
import pytest

from app.bilibili.client import BiliClient, BiliError, UA


def make_client(handler) -> BiliClient:
    return BiliClient(session=httpx.Client(transport=httpx.MockTransport(handler)))


def test_get_json_ok():
    def handler(request):
        return httpx.Response(200, json={"code": 0, "data": {"x": 1}})

    client = make_client(handler)
    assert client.get_json("/x/web-interface/nav")["data"] == {"x": 1}


def test_get_json_raises_on_error_code():
    def handler(request):
        return httpx.Response(200, json={"code": -101, "message": "账号未登录"})

    client = make_client(handler)
    with pytest.raises(BiliError, match="账号未登录"):
        client.get_json("/x/v2/history")


def test_is_logged_in_true():
    def handler(request):
        return httpx.Response(200, json={"code": 0, "data": {"isLogin": True}})

    assert make_client(handler).is_logged_in() is True


def test_is_logged_in_false():
    def handler(request):
        return httpx.Response(200, json={"code": 0, "data": {"isLogin": False}})

    assert make_client(handler).is_logged_in() is False


def test_cookies_attached():
    captured = {}

    def handler(request):
        captured["cookie"] = request.headers.get("cookie", "")
        return httpx.Response(200, json={"code": 0, "data": {}})

    make_client({"SESSDATA": "abc123"}).get_json("/x/web-interface/nav")
    assert "SESSDATA=abc123" in captured["cookie"]
    assert "bilibili" in UA
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_client.py -v`
Expected: FAIL（ImportError）

- [ ] **Step 3: 写实现**

`app/bilibili/__init__.py`：空文件。

`app/bilibili/client.py`：
```python
"""B 站 API 客户端：统一封装请求、Cookie、登录态检测。"""
from __future__ import annotations

import httpx

BASE_URL = "https://api.bilibili.com"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class BiliError(Exception):
    """B 站接口返回非 0 code 或请求异常。"""


class BiliClient:
    def __init__(self, cookies: dict | None = None,
                 session: httpx.Client | None = None) -> None:
        self.session = session or httpx.Client(
            base_url=BASE_URL,
            timeout=15.0,
            headers={"User-Agent": UA, "Referer": "https://www.bilibili.com/"},
        )
        if cookies:
            self.session.cookies.update(cookies)

    def get_json(self, path: str, params: dict | None = None) -> dict:
        resp = self.session.get(path, params=params)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") not in (0, None):
            raise BiliError(f"{path} 返回错误: code={data.get('code')} {data.get('message', '')}")
        return data

    def is_logged_in(self) -> bool:
        data = self.get_json("/x/web-interface/nav")
        return bool(data.get("data", {}).get("isLogin"))

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> "BiliClient":
        return self

    def __exit__(self, *args) -> None:
        self.close()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_client.py -v`
Expected: 5 passed

- [ ] **Step 5: 提交**

```bash
git add app/bilibili tests/test_client.py
git commit -m "feat: M1 B 站 API 客户端"
```

---

### Task 4: 扫码登录（后端）

**Files:**
- Create: `app/bilibili/login.py`
- Test: `tests/test_login.py`

**Interfaces:**
- Consumes: `app.config.save_cookies`
- Produces:
  - `QRLogin(session: httpx.Client | None = None)`
    - `.generate() -> dict`（含 `url`、`qrcode_key`）
    - `.poll(qrcode_key: str) -> dict`（status: ok / pending / scanned / expired）

- [ ] **Step 1: 写失败的测试**

`tests/test_login.py`：
```python
from __future__ import annotations

import httpx

from app.bilibili import login
from app.config import load_config


def make_login(handler) -> login.QRLogin:
    return login.QRLogin(session=httpx.Client(transport=httpx.MockTransport(handler)))


def test_generate_returns_url_and_key():
    def handler(request):
        return httpx.Response(200, json={
            "code": 0,
            "data": {"url": "https://passport.bilibili.com/h5/login?key=K", "qrcode_key": "K"},
        })

    result = make_login(handler).generate()
    assert result["qrcode_key"] == "K"
    assert "passport.bilibili.com" in result["url"]


def test_generate_raises_on_error():
    def handler(request):
        return httpx.Response(200, json={"code": -400, "message": "请求太频繁"})

    import pytest
    with pytest.raises(RuntimeError, match="请求太频繁"):
        make_login(handler).generate()


def test_poll_success_saves_cookies(tmp_path):
    from app import config
    config.set_config_path(tmp_path / "config.json")

    def handler(request):
        resp = httpx.Response(200, json={"code": 0, "data": {"url": "https://www.bilibili.com/"}})
        resp.headers["set-cookie"] = "SESSDATA=abc; bili_jct=def; Path=/"
        return resp

    result = make_login(handler).poll("K")
    assert result["status"] == "ok"
    cookies = load_config()["cookies"]
    assert cookies["SESSDATA"] == "abc"
    assert cookies["bili_jct"] == "def"


def test_poll_expired():
    def handler(request):
        return httpx.Response(200, json={"code": 86038, "data": None})

    assert make_login(handler).poll("K")["status"] == "expired"


def test_poll_pending_and_scanned():
    pending = make_login(lambda r: httpx.Response(200, json={"code": 86101, "data": None}))
    assert pending.poll("K")["status"] == "pending"

    scanned = make_login(lambda r: httpx.Response(200, json={"code": 86090, "data": None}))
    assert scanned.poll("K")["status"] == "scanned"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_login.py -v`
Expected: FAIL（ImportError）

- [ ] **Step 3: 写实现**

`app/bilibili/login.py`：
```python
"""扫码登录：生成二维码、轮询扫码结果、保存 Cookie。"""
from __future__ import annotations

import httpx

from app.bilibili.client import UA
from app.config import save_cookies

QR_GENERATE_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
QR_POLL_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"


class QRLogin:
    def __init__(self, session: httpx.Client | None = None) -> None:
        self.session = session or httpx.Client(
            timeout=15.0,
            headers={"User-Agent": UA, "Referer": "https://www.bilibili.com/"},
        )

    def generate(self) -> dict:
        resp = self.session.get(QR_GENERATE_URL)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"生成二维码失败: {data.get('message', data)}")
        return data["data"]

    def poll(self, qrcode_key: str) -> dict:
        resp = self.session.get(QR_POLL_URL, params={"qrcode_key": qrcode_key})
        resp.raise_for_status()
        data = resp.json()
        code = data.get("code")
        if code == 0:
            cookies = {k: v for k, v in self.session.cookies.items()}
            save_cookies(cookies)
            return {"status": "ok", "message": "登录成功"}
        if code == 86038:
            return {"status": "expired", "message": "二维码已失效，请刷新"}
        if code == 86090:
            return {"status": "scanned", "message": "已扫码，请在手机确认"}
        if code == 86101:
            return {"status": "pending", "message": "等待扫码"}
        return {"status": "pending", "message": f"未知状态 code={code}"}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_login.py -v`
Expected: 5 passed

- [ ] **Step 5: 提交**

```bash
git add app/bilibili/login.py tests/test_login.py
git commit -m "feat: M1 扫码登录后端"
```

---

### Task 5: 观看历史采集

**Files:**
- Create: `app/bilibili/history.py`
- Test: `tests/test_history.py`

**Interfaces:**
- Consumes: `BiliClient.get_json`
- Produces:
  - `normalize_history_item(item: dict) -> dict`（字段：bvid/title/up_mid/up_name/view_at/progress/duration/pic/tname/ctime）
  - `fetch_history(client: BiliClient, max_pages: int = 20) -> list[dict]`

- [ ] **Step 1: 写失败的测试**

`tests/test_history.py`：
```python
from __future__ import annotations

import httpx

from app.bilibili.client import BiliClient
from app.bilibili import history as h


def make_client(handler) -> BiliClient:
    return BiliClient(session=httpx.Client(transport=httpx.MockTransport(handler)))


def item(bvid, view_at, **kw):
    base = {
        "bvid": bvid, "title": "标题", "author_mid": 1001, "author_name": "阿测",
        "view_at": view_at, "progress": 30, "duration": 600,
        "pic": "http://x/pic.jpg", "tname": "生活", "ctime": 1700000000,
    }
    base.update(kw)
    return base


def test_normalize_history_item():
    it = item("BV1", 1234567890)
    n = h.normalize_history_item(it)
    assert n["bvid"] == "BV1"
    assert n["up_name"] == "阿测"
    assert n["tname"] == "生活"


def test_fetch_history_single_page():
    pages = iter([{
        "code": 0,
        "data": {"list": [item("BV1", 100), item("BV2", 99)], "max_id": None},
    }])

    def handler(request):
        return httpx.Response(200, json=next(pages))

    rows = h.fetch_history(make_client(handler))
    assert len(rows) == 2
    assert rows[0]["bvid"] == "BV1"


def test_fetch_history_paginates_until_empty():
    responses = [
        {"code": 0, "data": {"list": [item("BV1", 100)], "max_id": 50}},
        {"code": 0, "data": {"list": [item("BV2", 99)], "max_id": 25}},
        {"code": 0, "data": {"list": [], "max_id": None}},
    ]
    requested_max_ids = []

    def handler(request):
        requested_max_ids.append(request.url.params.get("max_id"))
        return httpx.Response(200, json=responses.pop(0))

    rows = h.fetch_history(make_client(handler))
    assert len(rows) == 2
    assert requested_max_ids == [None, "50", "25"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_history.py -v`
Expected: FAIL（ImportError）

- [ ] **Step 3: 写实现**

`app/bilibili/history.py`：
```python
"""观看历史采集。"""
from __future__ import annotations

from app.bilibili.client import BiliClient


def normalize_history_item(item: dict) -> dict:
    return {
        "bvid": item["bvid"],
        "title": item.get("title", ""),
        "up_mid": item.get("author_mid", 0),
        "up_name": item.get("author_name", ""),
        "view_at": item.get("view_at", 0),
        "progress": item.get("progress", 0),
        "duration": item.get("duration", 0),
        "pic": item.get("pic", ""),
        "tname": item.get("tname", ""),
        "ctime": item.get("ctime", 0),
    }


def fetch_history(client: BiliClient, max_pages: int = 20) -> list[dict]:
    """分页拉取观看历史，返回规范化记录（按时间倒序）。"""
    result: list[dict] = []
    cursor = None
    for _ in range(max_pages):
        params: dict = {"pn": 1, "ps": 100}
        if cursor:
            params["max_id"] = cursor
        data = client.get_json("/x/v2/history", params)
        items = data.get("data", {}).get("list") or []
        if not items:
            break
        result.extend(normalize_history_item(i) for i in items)
        cursor = data.get("data", {}).get("max_id")
        if not cursor:
            break
    return result
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_history.py -v`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add app/bilibili/history.py tests/test_history.py
git commit -m "feat: M1 观看历史采集"
```

---

### Task 6: 收藏夹采集

**Files:**
- Create: `app/bilibili/favorite.py`
- Test: `tests/test_favorite.py`

**Interfaces:**
- Consumes: `BiliClient.get_json`
- Produces:
  - `fetch_folders(client: BiliClient) -> list[dict]`（media_id/name/count/created_at）
  - `fetch_folder_items(client: BiliClient, media_id: int, max_pages: int = 100) -> list[dict]`（media_id/bvid/title/up_mid/up_name/fav_time/duration/pic/tname）

- [ ] **Step 1: 写失败的测试**

`tests/test_favorite.py`：
```python
from __future__ import annotations

import httpx

from app.bilibili.client import BiliClient
from app.bilibili import favorite as f


def make_client(handler) -> BiliClient:
    return BiliClient(session=httpx.Client(transport=httpx.MockTransport(handler)))


def test_fetch_folders():
    def handler(request):
        return httpx.Response(200, json={
            "code": 0,
            "data": {"list": [
                {"id": 101, "title": "动画", "media_count": 12, "ctime": 1700000000},
                {"id": 102, "title": "科技", "media_count": 5, "ctime": 1700000100},
            ]},
        })

    folders = f.fetch_folders(make_client(handler))
    assert folders == [
        {"media_id": 101, "name": "动画", "count": 12, "created_at": 1700000000},
        {"media_id": 102, "name": "科技", "count": 5, "created_at": 1700000100},
    ]


def test_fetch_folder_items_single_page():
    def handler(request):
        return httpx.Response(200, json={
            "code": 0,
            "data": {"medias": [
                {"bvid": "BV1", "title": "视频一", "fav_time": 1600000000,
                 "upper": {"mid": 1, "name": "UP甲"}, "duration": 300,
                 "cover": "http://x/a.jpg", "tname": "动画"},
                {"bvid": "BV2", "title": "视频二", "fav_time": 1600000001,
                 "upper": {"mid": 2, "name": "UP乙"}, "duration": 400,
                 "cover": "http://x/b.jpg", "tname": "科技"},
            ]},
        })

    items = f.fetch_folder_items(make_client(handler), 101)
    assert len(items) == 2
    assert items[0]["bvid"] == "BV1"
    assert items[0]["media_id"] == 101
    assert items[0]["up_name"] == "UP甲"


def test_fetch_folder_items_paginates_until_short_page():
    pages = iter([
        {"code": 0, "data": {"medias": [{"bvid": f"BV{i}", "upper": {}, "fav_time": 1} for i in range(20)]}},
        {"code": 0, "data": {"medias": []}},
    ])

    def handler(request):
        return httpx.Response(200, json=next(pages))

    items = f.fetch_folder_items(make_client(handler), 101, max_pages=100)
    assert len(items) == 20
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_favorite.py -v`
Expected: FAIL（ImportError）

- [ ] **Step 3: 写实现**

`app/bilibili/favorite.py`：
```python
"""收藏夹采集。"""
from __future__ import annotations

from app.bilibili.client import BiliClient


def fetch_folders(client: BiliClient) -> list[dict]:
    data = client.get_json("/x/v3/fav/folder/created/list-all")
    folders = data.get("data", {}).get("list") or []
    return [
        {
            "media_id": fl["id"],
            "name": fl.get("title", ""),
            "count": fl.get("media_count", 0),
            "created_at": fl.get("ctime", 0),
        }
        for fl in folders
    ]


def fetch_folder_items(client: BiliClient, media_id: int, max_pages: int = 100) -> list[dict]:
    result: list[dict] = []
    for pn in range(1, max_pages + 1):
        data = client.get_json(
            "/x/v3/fav/resource/list",
            {"media_id": media_id, "pn": pn, "ps": 20},
        )
        medias = data.get("data", {}).get("medias") or []
        if not medias:
            break
        for m in medias:
            upper = m.get("upper") or {}
            result.append({
                "media_id": media_id,
                "bvid": m.get("bvid", ""),
                "title": m.get("title", ""),
                "up_mid": upper.get("mid", 0),
                "up_name": upper.get("name", ""),
                "fav_time": m.get("fav_time", 0),
                "duration": m.get("duration", 0),
                "pic": m.get("cover", ""),
                "tname": m.get("tname", ""),
            })
        if len(medias) < 20:
            break
    return result
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_favorite.py -v`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add app/bilibili/favorite.py tests/test_favorite.py
git commit -m "feat: M1 收藏夹采集"
```

---

### Task 7: 关注列表采集

**Files:**
- Create: `app/bilibili/relation.py`
- Test: `tests/test_relation.py`

**Interfaces:**
- Consumes: `BiliClient.get_json`
- Produces: `fetch_followings(client: BiliClient, vmid: int, max_pages: int = 100) -> list[dict]`（mid/uname/face）

- [ ] **Step 1: 写失败的测试**

`tests/test_relation.py`：
```python
from __future__ import annotations

import httpx

from app.bilibili.client import BiliClient
from app.bilibili import relation as r


def make_client(handler) -> BiliClient:
    return BiliClient(session=httpx.Client(transport=httpx.MockTransport(handler)))


def test_fetch_followings_single_page():
    def handler(request):
        return httpx.Response(200, json={
            "code": 0,
            "data": {"list": [
                {"mid": 1, "uname": "UP甲", "face": "http://x/1.jpg"},
                {"mid": 2, "uname": "UP乙", "face": "http://x/2.jpg"},
            ]},
        })

    rows = r.fetch_followings(make_client(handler), 123)
    assert len(rows) == 2
    assert rows[0] == {"mid": 1, "uname": "UP甲", "face": "http://x/1.jpg"}


def test_fetch_followings_paginates_until_short_page():
    pages = iter([
        {"code": 0, "data": {"list": [{"mid": i, "uname": f"U{i}", "face": ""} for i in range(50)]}},
        {"code": 0, "data": {"list": [{"mid": 100, "uname": "U100", "face": ""}]}},
        {"code": 0, "data": {"list": []}},
    ])
    pns = []

    def handler(request):
        pns.append(request.url.params.get("pn"))
        return httpx.Response(200, json=next(pages))

    rows = r.fetch_followings(make_client(handler), 123)
    assert len(rows) == 51
    assert pns == ["1", "2", "3"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_relation.py -v`
Expected: FAIL（ImportError）

- [ ] **Step 3: 写实现**

`app/bilibili/relation.py`：
```python
"""关注列表采集。"""
from __future__ import annotations

from app.bilibili.client import BiliClient


def fetch_followings(client: BiliClient, vmid: int, max_pages: int = 100) -> list[dict]:
    result: list[dict] = []
    for pn in range(1, max_pages + 1):
        data = client.get_json(
            "/x/relation/followings",
            {"vmid": vmid, "pn": pn, "ps": 50, "order": "desc"},
        )
        items = data.get("data", {}).get("list") or []
        if not items:
            break
        result.extend({
            "mid": it.get("mid", 0),
            "uname": it.get("uname", ""),
            "face": it.get("face", ""),
        } for it in items)
        if len(items) < 50:
            break
    return result
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_relation.py -v`
Expected: 2 passed

- [ ] **Step 5: 提交**

```bash
git add app/bilibili/relation.py tests/test_relation.py
git commit -m "feat: M1 关注列表采集"
```

---

### Task 8: 数据同步编排

**Files:**
- Create: `app/sync.py`
- Test: `tests/test_sync.py`

**Interfaces:**
- Consumes: `BiliClient`、`normalize_history_item`/`fetch_history`、`fetch_folders`/`fetch_folder_items`、`fetch_followings`、`app.database`、`app.config.get_cookies`
- Produces:
  - `upsert_video(conn, v: dict) -> None`
  - `sync_history(conn, client) -> int`（新增历史条数）
  - `sync_favorites(conn, client) -> int`（新增收藏条数）
  - `sync_followings(conn, client, uid: int) -> int`
  - `run_full_sync(client: BiliClient | None = None) -> dict`（`{"history": n, "favorites": n, "followings": n}`；未登录抛 `BiliError`；成功后把 uid 写入 config）

- [ ] **Step 1: 写失败的测试**

`tests/test_sync.py`：
```python
from __future__ import annotations

import httpx
import pytest

from app import database
from app.bilibili.client import BiliClient, BiliError
from app.bilibili import history as h
from app.bilibili import favorite as fav
from app.bilibili import relation as rel
from app import sync
from app import config


def hist_item(bvid, view_at):
    return {"bvid": bvid, "title": f"T-{bvid}", "up_mid": 1, "up_name": "UP甲",
            "view_at": view_at, "progress": 10, "duration": 100, "pic": "", "tname": "动画", "ctime": 1}


def folder_item(media_id, bvid):
    return {"media_id": media_id, "bvid": bvid, "title": f"F-{bvid}", "up_mid": 2,
            "up_name": "UP乙", "fav_time": 1600000000, "duration": 100, "pic": "", "tname": "科技"}


def follow_item(mid):
    return {"mid": mid, "uname": f"U{mid}", "face": ""}


def test_sync_history_and_dedup(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()

    class FakeClient:
        def get_json(self, path, params=None):
            if path == "/x/v2/history":
                return {"code": 0, "data": {"list": [hist_item("BV1", 100), hist_item("BV2", 99)], "max_id": None}}
            raise AssertionError(f"unexpected path {path}")

    n = sync.sync_history(conn, FakeClient())  # type: ignore
    assert n == 2
    n = sync.sync_history(conn, FakeClient())  # type: ignore
    assert n == 0  # 幂等：不重复插入
    assert conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM history").fetchone()[0] == 2
    conn.close()


def test_sync_favorites_and_followings(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()

    class FakeClient:
        def get_json(self, path, params=None):
            if path == "/x/v3/fav/folder/created/list-all":
                return {"code": 0, "data": {"list": [{"id": 101, "title": "动画", "media_count": 1, "ctime": 1}]}}
            if path == "/x/v3/fav/resource/list":
                return {"code": 0, "data": {"medias": [{
                    "bvid": "BV9", "title": "F-BV9", "fav_time": 1,
                    "upper": {"mid": 2, "name": "UP乙"}, "duration": 100, "cover": "", "tname": ""}]}}
            if path == "/x/relation/followings":
                return {"code": 0, "data": {"list": [follow_item(1), follow_item(2)]}}
            raise AssertionError(f"unexpected path {path}")

    client = FakeClient()  # type: ignore
    n_fav = sync.sync_favorites(conn, client)
    n_fol = sync.sync_followings(conn, client, uid=123)
    assert n_fav == 1
    assert n_fol == 2
    assert conn.execute("SELECT COUNT(*) FROM fav_items").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM followings").fetchone()[0] == 2
    conn.close()


def test_run_full_sync_requires_login(tmp_path, monkeypatch):
    config.set_config_path(tmp_path / "config.json")
    monkeypatch.setattr(config, "get_cookies", lambda: {})
    with pytest.raises(BiliError, match="未登录"):
        sync.run_full_sync()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_sync.py -v`
Expected: FAIL（ImportError: app.sync）

- [ ] **Step 3: 写实现**

`app/sync.py`：
```python
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


def sync_favorites(conn: sqlite3.Connection, client: BiliClient) -> int:
    folders = favorite_mod.fetch_folders(client)
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
        n_hist = sync_history(conn, client)
        n_fav = sync_favorites(conn, client)
        nav = client.get_json("/x/web-interface/nav")
        uid = nav.get("data", {}).get("mid", 0)
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_sync.py -v`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add app/sync.py tests/test_sync.py
git commit -m "feat: M1 数据同步编排"
```

---

### Task 9: 查询与统计 API

**Files:**
- Modify: `app/api.py`（替换占位）
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `run_full_sync`、`BiliError`、`get_cookies/load_config`、`database.get_conn/init_db`、`QRLogin`
- Produces（FastAPI 路由）：
  - `GET /api/status` → `{logged_in, login_at, uid, counts:{history,favorites,followings,folders}}`
  - `GET /api/login/qrcode` → `{url, qrcode_key}`
  - `GET /api/login/poll?qrcode_key=` → `{status, message}`
  - `POST /api/sync` → `{history, favorites, followings}`（401 未登录 / 502 同步失败）
  - `GET /api/history?search=&page=&page_size=` → `{total, items}`
  - `GET /api/favorites` → `[{media_id,name,count,created_at}]`
  - `GET /api/favorites/{media_id}?page=&page_size=` → `{total, items}`
  - `GET /api/followings` → `[{mid,uname,face}]`
  - `GET /api/stats/overview` → `{counts, trend, top_ups, hours, tnames}`

- [ ] **Step 1: 写失败的测试**

`tests/test_api.py`：
```python
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import config, database
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_state(tmp_path):
    config.set_config_path(tmp_path / "config.json")
    database.set_db_path(tmp_path / "api.db")
    database.init_db()


def test_ping():
    assert client.get("/api/ping").json() == {"ok": True}


def test_status_not_logged_in():
    r = client.get("/api/status")
    assert r.status_code == 200
    body = r.json()
    assert body["logged_in"] is False
    assert body["counts"]["history"] == 0


def test_status_logged_in_with_counts(tmp_path):
    database.set_db_path(tmp_path / "api.db")
    conn = database.get_conn()
    conn.execute("INSERT INTO videos (bvid, title) VALUES ('BV1', 'T')")
    conn.execute("INSERT INTO history (bvid, view_at, progress) VALUES ('BV1', 100, 10)")
    conn.execute("INSERT INTO fav_folders (media_id, name) VALUES (101, '动画')")
    conn.execute("INSERT INTO fav_items (media_id, bvid) VALUES (101, 'BV1')")
    conn.execute("INSERT INTO followings (mid, uname) VALUES (1, 'U')")
    conn.commit()
    conn.close()
    config.save_cookies({"SESSDATA": "abc"})

    body = client.get("/api/status").json()
    assert body["logged_in"] is True
    assert body["counts"]["history"] == 1
    assert body["counts"]["favorites"] == 1
    assert body["counts"]["folders"] == 1
    assert body["counts"]["followings"] == 1


def test_history_search():
    database.set_db_path(__import__("app.config", fromlist=["ROOT"]).ROOT)  # noqa: F401
    conn = database.get_conn()
    conn.execute("INSERT INTO videos (bvid, title, up_name, tname, duration) VALUES ('BV1', 'Python 教程', 'UP甲', '科技', 300)")
    conn.execute("INSERT INTO videos (bvid, title, up_name, tname, duration) VALUES ('BV2', '美食探店', 'UP乙', '美食', 400)")
    conn.execute("INSERT INTO history (bvid, view_at, progress) VALUES ('BV1', 200, 50)")
    conn.execute("INSERT INTO history (bvid, view_at, progress) VALUES ('BV2', 100, 20)")
    conn.commit()
    conn.close()

    r = client.get("/api/history", params={"search": "Python", "page": 1, "page_size": 10})
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Python 教程"


def test_sync_returns_401_when_not_logged_in():
    r = client.post("/api/sync")
    assert r.status_code == 401


def test_overview_stats():
    conn = database.get_conn()
    conn.execute("INSERT INTO videos (bvid, title, up_name, tname, duration) VALUES ('BV1', 'T', 'UP甲', '动画', 300)")
    conn.execute("INSERT INTO history (bvid, view_at, progress) VALUES ('BV1', 1723400000, 50)")
    conn.commit()
    conn.close()

    body = client.get("/api/stats/overview").json()
    assert body["counts"]["history"] == 1
    assert body["top_ups"][0]["up_name"] == "UP甲"
    assert body["tnames"][0]["tname"] == "动画"
```

> 说明：`test_history_search` 中 `__import__("app.config", fromlist=["ROOT"]).ROOT` 仅用于兼容引用占位实现；实际实现后该行可简化为 `from app.config import ROOT`。在 Task 9 实现阶段将 `database.set_db_path(...)` 依赖的路径替换为 tmp 路径。

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_api.py -v`
Expected: FAIL（`/api/status` 返回 404，因为占位 api.py 只有 /ping）

- [ ] **Step 3: 写实现**

`app/api.py`：
```python
"""REST API 路由。"""
from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Query

from app.bilibili import login as login_mod
from app.bilibili.client import BiliError
from app.config import get_cookies, load_config, save_config
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
```

- [ ] **Step 4: 修正测试并确认通过**

将 `tests/test_api.py` 中 `test_history_search` 的脏写法改为：
```python
def test_history_search(tmp_path):
    database.set_db_path(tmp_path / "api.db")
    conn = database.get_conn()
    conn.execute("INSERT INTO videos (bvid, title, up_name, tname, duration) VALUES ('BV1', 'Python 教程', 'UP甲', '科技', 300)")
    conn.execute("INSERT INTO videos (bvid, title, up_name, tname, duration) VALUES ('BV2', '美食探店', 'UP乙', '美食', 400)")
    conn.execute("INSERT INTO history (bvid, view_at, progress) VALUES ('BV1', 200, 50)")
    conn.execute("INSERT INTO history (bvid, view_at, progress) VALUES ('BV2', 100, 20)")
    conn.commit()
    conn.close()

    r = client.get("/api/history", params={"search": "Python", "page": 1, "page_size": 10})
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Python 教程"
```

Run: `python -m pytest tests/test_api.py -v`
Expected: 6 passed

> 注意：`clean_state` fixture 已把数据库指向 `tmp_path/api.db`，所以 `test_history_search` 不需要再 `set_db_path`——但 fixture 是 autouse 的，会先执行 `set_db_path(tmp_path/"api.db")`，因此测试函数内**直接** `database.get_conn()` 即可，无需重复调用 `set_db_path`。请按上面修正版执行。

- [ ] **Step 5: 提交**

```bash
git add app/api.py tests/test_api.py
git commit -m "feat: M1 查询与统计 API"
```

---

### Task 10: 前端骨架 + 概览页

**Files:**
- Create: `web/index.html`
- Create: `web/css/style.css`
- Create: `web/js/app.js`

**Interfaces:**
- Consumes: `GET /api/status`、`GET /api/stats/overview`
- Produces: 可打开的 Web 页面（`http://localhost:8000`），含左侧边栏 + 概览页（统计卡片 + 4 张图表）

- [ ] **Step 1: 创建前端骨架**

`web/index.html`：
```html
<!DOCTYPE html>
<html lang="zh-CN" class="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BiliScope</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/element-plus@2.9.1/dist/index.css">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/element-plus@2.9.1/theme-chalk/dark/css-vars.css">
<link rel="stylesheet" href="css/style.css">
</head>
<body>
<div id="app"></div>
<script src="https://cdn.jsdelivr.net/npm/vue@3.5.13/dist/vue.global.prod.js"></script>
<script src="https://cdn.jsdelivr.net/npm/element-plus@2.9.1/dist/index.full.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/@element-plus/icons-vue@2.3.1/dist/index.iife.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js"></script>
<script src="https://cdn.jsdelivr.net/gh/davidshimjs/qrcodejs@master/qrcode.min.js"></script>
<script src="js/app.js"></script>
</body>
</html>
```

`web/css/style.css`：
```css
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body, #app { height: 100%; }
body { background: #141414; color: #e5e5e5; font-family: 'Microsoft YaHei', sans-serif; }
.layout { height: 100%; }
.aside { background: #1e1e1e; border-right: 1px solid #333; position: relative; }
.logo { color: #fb7299; font-size: 22px; font-weight: 700; padding: 20px 16px; }
.menu { border-right: none; background: transparent; }
.sync-status { position: absolute; bottom: 20px; left: 16px; }
.card-num { font-size: 30px; font-weight: 700; color: #fb7299; text-align: center; }
.card-label { color: #999; margin-top: 6px; text-align: center; font-size: 13px; }
.chart { height: 280px; }
.charts .el-card { margin-bottom: 16px; }
.fav-name { font-size: 16px; font-weight: 600; }
.fav-count { color: #999; font-size: 12px; margin-top: 6px; }
h2 { margin: 8px 0 16px; font-size: 20px; }
.cards .el-card { margin-bottom: 16px; }
```

`web/js/app.js`（骨架 + 概览组件，历史/收藏/设置组件 Task 11 填充）：
```javascript
const { createApp, ref, onMounted, nextTick } = Vue;

async function api(path, options = {}) {
  const res = await fetch('/api' + path, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `请求失败(${res.status})`);
  return data;
}

const Overview = {
  props: ['status'],
  template: `
    <h2>概览</h2>
    <el-row :gutter="16" class="cards">
      <el-col :span="6" v-for="c in cards" :key="c.label">
        <el-card><div class="card-num">{{ c.value }}</div><div class="card-label">{{ c.label }}</div></el-card>
      </el-col>
    </el-row>
    <el-row :gutter="16" class="charts">
      <el-col :span="12"><el-card><div ref="trendChart" class="chart"></div></el-card></el-col>
      <el-col :span="12"><el-card><div ref="upChart" class="chart"></div></el-card></el-col>
      <el-col :span="12"><el-card><div ref="hourChart" class="chart"></div></el-card></el-col>
      <el-col :span="12"><el-card><div ref="tnameChart" class="chart"></div></el-card></el-col>
    </el-row>
  `,
  computed: {
    cards() {
      const c = this.status.counts || {};
      return [
        { label: '观看历史', value: c.history ?? '-' },
        { label: '收藏视频', value: c.favorites ?? '-' },
        { label: '收藏夹', value: c.folders ?? '-' },
        { label: '关注', value: c.followings ?? '-' },
      ];
    },
  },
  async mounted() {
    const s = await api('/stats/overview').catch(() => null);
    if (s) this.renderCharts(s);
  },
  methods: {
    renderCharts(s) {
      nextTick(() => {
        const specs = {
          trendChart: { type: 'line', title: '近30天观看趋势',
            x: s.trend.map(t => t.day), y: s.trend.map(t => t.n) },
          upChart: { type: 'bar', title: '常看UP主 TOP10',
            x: s.top_ups.map(u => u.up_name), y: s.top_ups.map(u => u.n) },
          hourChart: { type: 'bar', title: '观看时段分布',
            x: s.hours.map(h => h.hour + '时'), y: s.hours.map(h => h.n) },
          tnameChart: { type: 'pie', title: '视频分区分布',
            data: s.tnames.map(t => ({ name: t.tname, value: t.n })) },
        };
        for (const [refName, spec] of Object.entries(specs)) {
          const el = this.$refs[refName];
          if (!el) continue;
          const chart = echarts.init(el, 'dark');
          const axis = spec.type === 'pie'
            ? {}
            : {
                xAxis: { type: 'category', data: spec.x, axisLabel: { rotate: spec.x.length > 8 ? 30 : 0 } },
                yAxis: { type: 'value' },
              };
          chart.setOption({
            title: { text: spec.title, textStyle: { fontSize: 14 } },
            tooltip: { trigger: 'axis' },
            ...axis,
            series: [{ type: spec.type, data: spec.y || spec.data, smooth: true }],
          });
        }
      });
    },
  },
};

const App = {
  components: { Overview },
  template: `
    <el-container class="layout">
      <el-aside width="220px" class="aside">
        <div class="logo">BiliScope</div>
        <el-menu :default-active="route" @select="route = $event" class="menu">
          <el-menu-item index="overview"><el-icon><DataLine/></el-icon>概览</el-menu-item>
          <el-menu-item index="history"><el-icon><Clock/></el-icon>观看历史</el-menu-item>
          <el-menu-item index="favorites"><el-icon><Star/></el-icon>收藏夹</el-menu-item>
          <el-menu-item index="settings"><el-icon><Setting/></el-icon>设置</el-menu-item>
        </el-menu>
        <div class="sync-status">
          <el-tag :type="status.logged_in ? 'success' : 'danger'" size="small">
            {{ status.logged_in ? '已登录' : '未登录' }}
          </el-tag>
        </div>
      </el-aside>
      <el-main>
        <Overview v-if="route === 'overview'" :status="status"/>
      </el-main>
    </el-container>
  `,
  setup() {
    const route = ref('overview');
    const status = ref({ logged_in: false, counts: {} });
    async function loadStatus() {
      try { status.value = await api('/status'); } catch (e) {}
    }
    onMounted(loadStatus);
    return { route, status };
  },
};

const app = createApp(App);
for (const [name, comp] of Object.entries(ElementPlusIconsVue)) {
  app.component(name, comp);
}
app.use(ElementPlus).mount('#app');
```

- [ ] **Step 2: 启动服务人工验证概览页**

Run: `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`
Expected:
- 打开 `http://localhost:8000` 显示深色侧边栏 + 概览页，4 张统计卡片显示 `-`
- 4 个图表区域渲染出「近30天观看趋势 / 常看UP主 / 观看时段分布 / 视频分区分布」标题（空数据状态）
- 浏览器控制台无报错

- [ ] **Step 3: 提交**

```bash
git add web
git commit -m "feat: M1 前端骨架与概览页"
```

---

### Task 11: 前端历史 / 收藏 / 设置页

**Files:**
- Modify: `web/js/app.js`（补充 History / Favorites / Settings 组件并注册到 App）

**Interfaces:**
- Consumes: `GET /api/history`、`GET /api/favorites`、`GET /api/favorites/{media_id}`、`GET /api/login/qrcode`、`GET /api/login/poll`、`POST /api/sync`

- [ ] **Step 1: 在 app.js 中追加三个组件

在 `Overview` 定义之后、`const App = ...` 之前追加：

```javascript
const History = {
  template: `
    <h2>观看历史</h2>
    <div style="margin-bottom:12px">
      <el-input v-model="search" placeholder="搜索标题或UP主" clearable style="width:320px"
                @keyup.enter="load(1)"/>
      <el-button type="primary" @click="load(1)">搜索</el-button>
    </div>
    <el-table :data="items" v-loading="loading" style="width:100%">
      <el-table-column label="观看时间" width="180">
        <template #default="s">{{ fmt(s.row.view_at) }}</template>
      </el-table-column>
      <el-table-column prop="title" label="标题" min-width="260"/>
      <el-table-column prop="up_name" label="UP主" width="140"/>
      <el-table-column prop="tname" label="分区" width="100"/>
      <el-table-column label="进度" width="100">
        <template #default="s">{{ pct(s.row.progress, s.row.duration) }}</template>
      </el-table-column>
    </el-table>
    <el-pagination layout="prev, pager, next" :total="total" :page-size="pageSize"
                   :current-page="page" @current-change="load" style="margin-top:12px"/>
  `,
  setup() {
    const search = ref(''); const items = ref([]); const total = ref(0);
    const page = ref(1); const pageSize = 20; const loading = ref(false);
    async function load(p) {
      page.value = p || 1; loading.value = true;
      try {
        const d = await api(`/history?search=${encodeURIComponent(search.value)}&page=${page.value}&page_size=${pageSize}`);
        items.value = d.items; total.value = d.total;
      } finally { loading.value = false; }
    }
    const fmt = ts => ts ? new Date(ts * 1000).toLocaleString('zh-CN') : '';
    const pct = (prog, dur) => dur ? Math.round(prog / dur * 100) + '%' : (prog || '-');
    onMounted(() => load(1));
    return { search, items, total, page, pageSize, loading, load, fmt, pct };
  },
};

const Favorites = {
  template: `
    <h2>收藏夹</h2>
    <el-row :gutter="12">
      <el-col :span="8" v-for="f in folders" :key="f.media_id">
        <el-card @click="open(f)" style="margin-bottom:12px;cursor:pointer">
          <div class="fav-name">{{ f.name }}</div>
          <div class="fav-count">{{ f.count }} 个视频 · {{ fmt(f.created_at) }}</div>
        </el-card>
      </el-col>
    </el-row>
    <el-dialog v-model="dialog" :title="current?.name" width="70%">
      <el-table :data="items" v-loading="loading">
        <el-table-column label="标题" min-width="260">
          <template #default="s">
            <span v-if="s.row.title">{{ s.row.title }}</span>
            <el-tag v-else type="danger">已失效</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="up_name" label="UP主" width="140"/>
        <el-table-column label="收藏时间" width="180">
          <template #default="s">{{ fmt(s.row.fav_time) }}</template>
        </el-table-column>
      </el-table>
    </el-dialog>
  `,
  setup() {
    const folders = ref([]); const items = ref([]); const current = ref(null);
    const dialog = ref(false); const loading = ref(false);
    const fmt = ts => ts ? new Date(ts * 1000).toLocaleString('zh-CN') : '';
    async function loadFolders() {
      folders.value = await api('/favorites');
    }
    async function open(f) {
      current.value = f; dialog.value = true; loading.value = true;
      try {
        const d = await api(`/favorites/${f.media_id}?page_size=200`);
        items.value = d.items;
      } finally { loading.value = false; }
    }
    onMounted(loadFolders);
    return { folders, items, current, dialog, loading, fmt, open };
  },
};

const Settings = {
  props: ['status'],
  emits: ['refresh'],
  template: `
    <h2>设置</h2>
    <el-card style="max-width:520px">
      <template #header>账号</template>
      <div v-if="status.logged_in">
        <p>已登录 <el-tag type="success">UID {{ status.uid || '-' }}</el-tag></p>
        <p v-if="status.login_at" style="margin-top:8px">登录时间：{{ fmt(status.login_at) }}</p>
      </div>
      <p v-else>尚未登录，点击下方按钮扫码登录 B 站账号。</p>
      <div style="margin-top:16px">
        <el-button type="primary" @click="openQr">扫码登录</el-button>
        <el-button type="success" :disabled="!status.logged_in" @click="sync" :loading="syncing">
          立即同步数据
        </el-button>
      </div>
    </el-card>
    <el-dialog v-model="qrVisible" title="扫码登录 B 站" width="340px" @closed="stopPoll">
      <div id="qrcode" style="display:flex;justify-content:center"></div>
      <p style="text-align:center;margin-top:12px">{{ qrMsg }}</p>
    </el-dialog>
  `,
  setup(props, { emit }) {
    const qrVisible = ref(false); const qrMsg = ref('等待扫码'); const syncing = ref(false);
    const fmt = ts => ts ? new Date(ts * 1000).toLocaleString('zh-CN') : '';
    let timer = null; let qrKey = '';
    async function openQr() {
      qrVisible.value = true; qrMsg.value = '等待扫码';
      try {
        const d = await api('/login/qrcode');
        qrKey = d.qrcode_key;
        nextTick(() => {
          const el = document.getElementById('qrcode');
          el.innerHTML = '';
          new QRCode(el, { text: d.url, width: 220, height: 220 });
        });
        startPoll();
      } catch (e) { qrMsg.value = e.message; }
    }
    function startPoll() {
      stopPoll();
      timer = setInterval(async () => {
        try {
          const r = await api(`/login/poll?qrcode_key=${qrKey}`);
          qrMsg.value = r.message || '...';
          if (r.status === 'ok') { stopPoll(); qrVisible.value = false; ElementPlus.ElMessage.success('登录成功'); emit('refresh'); }
          else if (r.status === 'expired') { stopPoll(); ElementPlus.ElMessage.warning('二维码已失效'); }
        } catch (e) { /* 网络抖动忽略 */ }
      }, 2000);
    }
    function stopPoll() { if (timer) { clearInterval(timer); timer = null; } }
    async function sync() {
      syncing.value = true;
      try {
        const r = await api('/sync', { method: 'POST' });
        ElementPlus.ElMessage.success(`同步完成：历史+${r.history} 收藏+${r.favorites} 关注+${r.followings}`);
        emit('refresh');
      } catch (e) { ElementPlus.ElMessage.error(e.message); }
      finally { syncing.value = false; }
    }
    return { qrVisible, qrMsg, syncing, fmt, openQr, stopPoll, sync };
  },
};
```

然后更新 App 组件：`components` 加入三个组件，`el-main` 内用 `v-else-if` 渲染，并在 `setup` 中导出 `loadStatus`：

```javascript
const App = {
  components: { Overview, History, Favorites, Settings },
  template: `
    <el-container class="layout">
      <el-aside width="220px" class="aside">
        <div class="logo">BiliScope</div>
        <el-menu :default-active="route" @select="route = $event" class="menu">
          <el-menu-item index="overview"><el-icon><DataLine/></el-icon>概览</el-menu-item>
          <el-menu-item index="history"><el-icon><Clock/></el-icon>观看历史</el-menu-item>
          <el-menu-item index="favorites"><el-icon><Star/></el-icon>收藏夹</el-menu-item>
          <el-menu-item index="settings"><el-icon><Setting/></el-icon>设置</el-menu-item>
        </el-menu>
        <div class="sync-status">
          <el-tag :type="status.logged_in ? 'success' : 'danger'" size="small">
            {{ status.logged_in ? '已登录' : '未登录' }}
          </el-tag>
        </div>
      </el-aside>
      <el-main>
        <Overview v-if="route === 'overview'" :status="status" @refresh="loadStatus"/>
        <History v-else-if="route === 'history'"/>
        <Favorites v-else-if="route === 'favorites'"/>
        <Settings v-else-if="route === 'settings'" :status="status" @refresh="loadStatus"/>
      </el-main>
    </el-container>
  `,
  setup() {
    const route = ref('overview');
    const status = ref({ logged_in: false, counts: {} });
    async function loadStatus() {
      try { status.value = await api('/status'); } catch (e) {}
    }
    onMounted(loadStatus);
    return { route, status, loadStatus };
  },
};
```

- [ ] **Step 2: 启动服务人工验证三个页面**

Run: `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`
Expected:
- 「观看历史」页显示空表格 + 分页器
- 「收藏夹」页显示收藏夹卡片列表（若有数据）
- 「设置」页点击「扫码登录」弹出二维码，用 B 站 App 扫码后标签变为「已登录」
- 登录后点「立即同步数据」出现成功提示，切到「概览」页看到真实统计数据与图表

- [ ] **Step 3: 提交**

```bash
git add web/js/app.js
git commit -m "feat: M1 前端历史/收藏/设置页"
```

---

### Task 12: 集成冒烟测试 + README

**Files:**
- Modify: `README.md`（新建）
- Test: `tests/test_integration.py`

**Interfaces:**
- Consumes: 全部 M1 模块

- [ ] **Step 1: 写集成测试**

`tests/test_integration.py`：
```python
"""端到端：mock 的 B 站接口 → 同步 → 查询全链路。"""
from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app import config, database
from app.bilibili import login as login_mod
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated(tmp_path):
    config.set_config_path(tmp_path / "config.json")
    database.set_db_path(tmp_path / "int.db")
    database.init_db()


def make_sync_client():
    """一个完整的 mock B 站客户端，覆盖同步所需全部接口。"""
    responses = {
        "/x/web-interface/nav": {"code": 0, "data": {"isLogin": True, "mid": 123}},
        "/x/v2/history": {"code": 0, "data": {"list": [
            {"bvid": "BV1", "title": "历史一", "author_mid": 1, "author_name": "UP甲",
             "view_at": 100, "progress": 50, "duration": 300, "pic": "", "tname": "动画", "ctime": 1},
        ], "max_id": None}},
        "/x/v3/fav/folder/created/list-all": {"code": 0, "data": {"list": [
            {"id": 101, "title": "动画", "media_count": 1, "ctime": 1},
        ]}},
        "/x/v3/fav/resource/list": {"code": 0, "data": {"medias": [
            {"bvid": "BV2", "title": "收藏一", "fav_time": 2,
             "upper": {"mid": 2, "name": "UP乙"}, "duration": 400, "cover": "", "tname": "科技"},
        ]}},
        "/x/relation/followings": {"code": 0, "data": {"list": [
            {"mid": 1, "uname": "UP甲", "face": ""},
        ]}},
    }

    def handler(request):
        return httpx.Response(200, json=responses.get(request.url.path, {"code": 0, "data": {}}))

    from app.bilibili.client import BiliClient
    return BiliClient(session=httpx.Client(transport=httpx.MockTransport(handler)))


def test_full_flow(tmp_path, monkeypatch):
    from app import sync
    config.save_cookies({"SESSDATA": "abc"})
    monkeypatch.setattr(config, "get_cookies", lambda: {"SESSDATA": "abc"})
    monkeypatch.setattr(sync, "run_full_sync", lambda client=None: {
        "history": 1, "favorites": 1, "followings": 1,
    })

    # 通过 API 触发同步
    r = client.post("/api/sync")
    assert r.status_code == 200
    assert r.json() == {"history": 1, "favorites": 1, "followings": 1}


def test_database_seeded_from_client():
    from app.bilibili.client import BiliClient
    from app import sync
    conn = database.get_conn()
    n_h = sync.sync_history(conn, make_sync_client())
    n_f = sync.sync_favorites(conn, make_sync_client())
    assert n_h == 1 and n_f == 1
    conn.close()

    body = client.get("/api/status").json()
    assert body["counts"]["history"] == 1
    assert body["counts"]["favorites"] == 1
```

- [ ] **Step 2: 运行全部测试确认通过**

Run: `python -m pytest tests/ -v`
Expected: 全部通过（Task 1–11 测试 + 集成测试）

- [ ] **Step 3: 启动服务冒烟验证**

Run: `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`
Expected:
- `http://localhost:8000` 正常打开
- `http://localhost:8000/api/ping` 返回 `{"ok": true}`

- [ ] **Step 4: 写 README**

`README.md`：
```markdown
# BiliScope

读取并分析自己 B 站账号数据的本地工具：扫码登录 → 自动拉取观看历史、收藏、关注 → SQLite 存储 → Web 仪表盘可视化。

## 运行

```bash
pip install -r requirements.txt
python run.py
```

打开 http://localhost:8000 ，在「设置」页扫码登录 B 站账号，点「立即同步数据」。

## 功能（M1）

- 扫码登录（Cookie 存本地 config.json）
- 同步观看历史 / 收藏夹 / 关注列表
- 概览仪表盘：近 30 天观看趋势、常看 UP 主 TOP10、观看时段/分区分布

## 测试

```bash
python -m pytest tests/ -v
```

> 测试全部使用 mock 数据，不会真实请求 B 站。
```

- [ ] **Step 5: 提交**

```bash
git add README.md tests/test_integration.py
git commit -m "feat: M1 集成测试与 README"
```

---

## 收尾

M1 完成后：
1. `git push origin main`
2. 汇总 M1 交付结果（功能清单 + 测试通过情况）
3. 若需继续，进入 **M2 计划**：失效监测 + UP 主更新 + APScheduler 定时任务 + Web 提醒
