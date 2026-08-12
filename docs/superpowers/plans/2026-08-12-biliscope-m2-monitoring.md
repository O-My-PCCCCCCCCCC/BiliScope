# BiliScope M2（监测）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 M1 基础上加入监测能力：视频失效检测、UP 主新投稿检测、APScheduler 定时任务、Web 页内提醒（监测中心页 + 未读角标）。

**Architecture:** 复用 M1 的 `BiliClient`/`database`/`api`/前端结构。新增 `app/notify.py`（提醒入库）、`app/monitor.py`（失效检测 + UP 主更新）、`app/bilibili/wbi.py`（UP 主投稿接口需要 WBI 签名）、`app/scheduler.py`（APScheduler）。前端新增「监测中心」页。

**Tech Stack:** 在 M1 依赖上新增 `APScheduler==3.11.0`。

**依赖关系：** Task 1（notify+alerts API）是 Task 2/3 的基础；Task 2/3 是 Task 4/5 的基础；Task 6/7 收尾。

## Global Constraints

- Python ≥ 3.10；测试不得真实请求 B 站（一律 `httpx.MockTransport`）
- 失效/更新检测必须节流（请求间 `time.sleep`），避免触发风控
- 新增依赖只允许：`APScheduler==3.11.0`
- 每个 Task 结束提交一次 git；M2 全部完成后推送 GitHub
- `app/api.py`、`app/main.py` 为既有文件，遵循 M1 已有模式

---

### Task 1: 提醒写入与 API

**Files:**
- Create: `app/notify.py`
- Modify: `app/api.py`（新增 `/api/alerts`、`/api/alerts/{id}/read`，`/api/status` 增加 unread）
- Test: `tests/test_notify.py`

**Interfaces:**
- Produces:
  - `app.notify.add_alert(conn, type: str, title: str, content: str) -> None`
  - `GET /api/alerts?unread_only=` → `{"unread": n, "items": [{id,type,title,content,created_at,read}]}`
  - `POST /api/alerts/{id}/read` → `{"ok": true}`
  - `GET /api/status` 返回新增 `alerts_unread` 字段

- [ ] **Step 1: 写失败的测试**

`tests/test_notify.py`：
```python
from __future__ import annotations

from app import database
from app.notify import add_alert


def test_add_alert(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    add_alert(conn, "invalid", "视频失效", "BV1 检测为失效")
    conn.commit()
    row = conn.execute("SELECT * FROM alerts").fetchone()
    assert row["type"] == "invalid"
    assert row["title"] == "视频失效"
    assert row["read"] == 0
    conn.close()


def test_list_alerts_and_unread_count():
    from fastapi.testclient import TestClient
    from app.main import app
    from app import config
    import tempfile, pathlib

    tmp = pathlib.Path(tempfile.mkdtemp())
    config.set_config_path(tmp / "config.json")
    database.set_db_path(tmp / "t.db")
    database.init_db()

    conn = database.get_conn()
    add_alert(conn, "invalid", "A", "x")
    add_alert(conn, "update", "B", "y")
    conn.commit()
    conn.execute("UPDATE alerts SET read=1 WHERE title='A'")
    conn.commit()
    conn.close()

    client = TestClient(app)
    body = client.get("/api/alerts").json()
    assert body["unread"] == 1
    assert len(body["items"]) == 2

    r = client.post(f"/api/alerts/{body['items'][0]['id']}/read")
    assert r.json() == {"ok": True}
    assert client.get("/api/alerts").json()["unread"] == 1  # 只剩 B 未读

    body = client.get("/api/status").json()
    assert body["alerts_unread"] == 1
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_notify.py -v`
Expected: FAIL（app.notify 不存在 / 路由 404）

- [ ] **Step 3: 写实现**

`app/notify.py`：
```python
"""提醒入库。"""
from __future__ import annotations

import sqlite3
import time


def add_alert(conn: sqlite3.Connection, type_: str, title: str, content: str) -> None:
    conn.execute(
        "INSERT INTO alerts (type, title, content, created_at) VALUES (?, ?, ?, ?)",
        (type_, title, content, int(time.time())),
    )
```

`app/api.py` 追加：
```python
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
```

`app/api.py` 的 `status()` 返回值追加 `"alerts_unread": conn.execute("SELECT COUNT(*) FROM alerts WHERE read=0").fetchone()[0]`（在 counts 之后、return 之前）。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_notify.py -v`
Expected: 2 passed

- [ ] **Step 5: 提交**

```bash
git add app/notify.py app/api.py tests/test_notify.py
git commit -m "feat: M2 提醒写入与 alerts API"
```

---

### Task 2: 失效检测

**Files:**
- Modify: `app/bilibili/client.py`（BiliError 增加 `code` 属性）
- Create: `app/monitor.py`（`check_invalid`）
- Test: `tests/test_monitor.py`

**Interfaces:**
- Consumes: `add_alert`、`BiliClient.get_json`
- Produces: `check_invalid(conn, client, limit=100, delay=0.3) -> int`（返回新失效数；写入 invalid_items + alerts）

- [ ] **Step 1: 写失败的测试**

`tests/test_monitor.py`：
```python
from __future__ import annotations

import httpx
import pytest

from app import database
from app.bilibili.client import BiliClient, BiliError
from app.monitor import check_invalid


def make_client(handler) -> BiliClient:
    return BiliClient(session=httpx.Client(transport=httpx.MockTransport(handler)))


def test_checks_invalid_videos(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    conn.execute("INSERT INTO videos (bvid, title) VALUES ('BV1', 'A')")
    conn.execute("INSERT INTO history (bvid, view_at) VALUES ('BV1', 100)")
    conn.execute("INSERT INTO videos (bvid, title) VALUES ('BV2', 'B')")
    conn.execute("INSERT INTO history (bvid, view_at) VALUES ('BV2', 200)")
    conn.commit()

    def handler(request):
        if request.url.params.get("bvid") == "BV1":
            return httpx.Response(200, json={"code": -404, "message": "啥都木有"})
        return httpx.Response(200, json={"code": 0, "data": {}})

    n = check_invalid(conn, make_client(handler), limit=10, delay=0)
    assert n == 1
    assert conn.execute("SELECT COUNT(*) FROM invalid_items").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM alerts WHERE type='invalid'").fetchone()[0] == 1

    # 第二次运行不重复记录
    n2 = check_invalid(conn, make_client(handler), limit=10, delay=0)
    assert n2 == 0
    conn.close()


def test_skips_when_no_videos(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    assert check_invalid(conn, make_client(lambda r: httpx.Response(200, json={"code": 0})), limit=10) == 0
    conn.close()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_monitor.py -v`
Expected: FAIL（app.monitor 不存在）

- [ ] **Step 3: 写实现**

`app/bilibili/client.py` 修改 BiliError：
```python
class BiliError(Exception):
    """B 站接口返回非 0 code 或请求异常。"""

    def __init__(self, message: str, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code
```
并把 `get_json` 中抛错处改为带 code：
```python
        if data.get("code") not in (0, None):
            raise BiliError(
                f"{path} 返回错误: code={data.get('code')} {data.get('message', '')}",
                code=data.get("code"),
            )
```

`app/monitor.py`：
```python
"""监测：视频失效检测、UP 主更新检测。"""
from __future__ import annotations

import sqlite3
import time

from app.bilibili.client import BiliClient, BiliError
from app.notify import add_alert


def check_invalid(conn: sqlite3.Connection, client: BiliClient,
                  limit: int = 100, delay: float = 0.3) -> int:
    """检查历史+收藏中的视频是否失效，返回新失效数。"""
    rows = conn.execute(
        "SELECT DISTINCT bvid FROM history "
        "UNION SELECT DISTINCT bvid FROM fav_items "
        "LIMIT ?",
        (limit,),
    ).fetchall()
    new_invalid = 0
    now = int(time.time())
    for row in rows:
        bvid = row["bvid"]
        if conn.execute(
            "SELECT 1 FROM invalid_items WHERE bvid = ?", (bvid,)
        ).fetchone():
            continue
        try:
            client.get_json("/x/web-interface/view", {"bvid": bvid})
        except BiliError as e:
            if e.code != -404:
                continue
            conn.execute(
                "INSERT INTO invalid_items (bvid, source, checked_at) VALUES (?, 'check', ?)",
                (bvid, now),
            )
            add_alert(conn, "invalid", "视频已失效", f"{bvid} 检测为失效，来源：历史/收藏")
            new_invalid += 1
        time.sleep(delay)
    conn.commit()
    return new_invalid
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_monitor.py -v`
Expected: 2 passed

- [ ] **Step 5: 提交**

```bash
git add app/bilibili/client.py app/monitor.py tests/test_monitor.py
git commit -m "feat: M2 视频失效检测"
```

---

### Task 3: WBI 签名 + UP 主更新检测

**Files:**
- Create: `app/bilibili/wbi.py`
- Modify: `app/bilibili/client.py`（新增 `get_wbi_json`）
- Modify: `app/monitor.py`（新增 `check_updates`）
- Test: `tests/test_wbi.py`、`tests/test_monitor.py`（追加）

**Interfaces:**
- Consumes: `add_alert`、`BiliClient`
- Produces:
  - `app.bilibili.wbi.sign_wbi(client, params: dict) -> dict`（注入 wts/w_rid 签名参数）
  - `BiliClient.get_wbi_json(path, params)`（自动签名后 GET）
  - `check_updates(conn, client, limit=20, delay=0.5) -> int`（返回新投稿提醒数；维护 updates 表）

- [ ] **Step 1: 写失败的测试**

`tests/test_wbi.py`：
```python
from __future__ import annotations

import httpx

from app.bilibili import wbi
from app.bilibili.client import BiliClient


def make_client(handler) -> BiliClient:
    return BiliClient(session=httpx.Client(transport=httpx.MockTransport(handler)))


def test_mixin_key():
    img_key = "7cd084941338484aae1ad9425b84077c"
    sub_key = "4932caff0ff746eab6f01bf08b70ac45"
    mixin = wbi.get_mixin_key(img_key, sub_key)
    assert len(mixin) == 32
    assert mixin == "ea1db124af3c7062474693fa704f4ff8"


def test_sign_wbi_adds_wts_and_w_rid(monkeypatch):
    import time as _time
    monkeypatch.setattr(_time, "time", lambda: 1700000000)

    def handler(request):
        return httpx.Response(200, json={"code": 0, "data": {
            "wbi_img": {
                "img_url": "https://i0.hdslb.com/bfs/wbi/7cd084941338484aae1ad9425b84077c.png",
                "sub_url": "https://i0.hdslb.com/bfs/wbi/4932caff0ff746eab6f01bf08b70ac45.png",
            },
        }})

    client = make_client(handler)
    # 先拉取 wbi keys 并缓存
    signed = wbi.sign_wbi(client, {"mid": 123})
    assert signed["mid"] == 123
    assert signed["wts"] == 1700000000
    assert "w_rid" in signed
    assert len(signed["w_rid"]) == 32


def test_get_wbi_json_signs_request():
    captured = {}

    def handler(request):
        captured["query"] = str(request.url.query)
        return httpx.Response(200, json={"code": 0, "data": {"list": {"vlist": []}}})

    client = make_client(handler)
    client.get_wbi_json("/x/space/wbi/arc/search", {"mid": 1})
    assert "w_rid=" in captured["query"]
    assert "wts=" in captured["query"]
```

> 注：mixin key 期望值依赖 B 站固定的 MIXIN_KEY_ENC_TAB 与上述两个示例 key；若实际实现与期望不符，说明转换表错误，需对照修复。

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_wbi.py -v`
Expected: FAIL（app.bilibili.wbi 不存在）

- [ ] **Step 3: 写实现**

`app/bilibili/wbi.py`：
```python
"""B 站 WBI 签名。部分接口（如 /x/space/wbi/arc/search）需要。"""
from __future__ import annotations

import hashlib
import time
import urllib.parse

MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52,
]

_wbi_cache: dict = {}


def get_mixin_key(img_key: str, sub_key: str) -> str:
    raw = img_key + sub_key
    return "".join(raw[i] for i in MIXIN_KEY_ENC_TAB)[:32]


def _fetch_keys(client) -> tuple[str, str]:
    if "keys" in _wbi_cache:
        return _wbi_cache["keys"]
    data = client.get_json("/x/web-interface/nav")["data"]
    img_url = data["wbi_img"]["img_url"]
    sub_url = data["wbi_img"]["sub_url"]
    img_key = img_url.rsplit("/", 1)[-1].split(".")[0]
    sub_key = sub_url.rsplit("/", 1)[-1].split(".")[0]
    _wbi_cache["keys"] = (img_key, sub_key)
    return img_key, sub_key


def sign_wbi(client, params: dict) -> dict:
    img_key, sub_key = _fetch_keys(client)
    mixin = get_mixin_key(img_key, sub_key)
    params = dict(params)
    params["wts"] = int(time.time())
    params = dict(sorted(params.items()))
    query = urllib.parse.urlencode(params)
    params["w_rid"] = hashlib.md5((query + mixin).encode()).hexdigest()
    return params
```

`app/bilibili/client.py` 追加方法：
```python
    def get_wbi_json(self, path: str, params: dict | None = None) -> dict:
        from app.bilibili import wbi
        signed = wbi.sign_wbi(self, params or {})
        return self.get_json(path, signed)
```

`app/monitor.py` 追加：
```python
def check_updates(conn: sqlite3.Connection, client: BiliClient,
                  limit: int = 20, delay: float = 0.5) -> int:
    """检查关注列表 UP 主最新投稿，有更新则写提醒。返回新提醒数。"""
    rows = conn.execute(
        "SELECT mid, uname FROM followings LIMIT ?", (limit,)
    ).fetchall()
    new_updates = 0
    now = int(time.time())
    for row in rows:
        mid = row["mid"]
        try:
            data = client.get_wbi_json(
                "/x/space/wbi/arc/search",
                {"mid": mid, "pn": 1, "ps": 1, "order": "pubdate"},
            )
            vlist = (data.get("data", {}).get("list") or {}).get("vlist") or []
            if not vlist:
                continue
            v = vlist[0]
            bvid = v["bvid"]
            cur = conn.execute(
                "SELECT last_bvid FROM updates WHERE mid = ?", (mid,)
            ).fetchone()
            if cur is None:
                conn.execute(
                    "INSERT INTO updates (mid, last_bvid, last_pubdate, checked_at) VALUES (?, ?, ?, ?)",
                    (mid, bvid, v.get("created", 0), now),
                )
            elif cur["last_bvid"] != bvid:
                conn.execute(
                    "UPDATE updates SET last_bvid = ?, last_pubdate = ?, checked_at = ? WHERE mid = ?",
                    (bvid, v.get("created", 0), now, mid),
                )
                add_alert(conn, "update", f"{row['uname']} 发布了新视频",
                          f"{v.get('title', '')} ({bvid})")
                new_updates += 1
            else:
                conn.execute("UPDATE updates SET checked_at = ? WHERE mid = ?", (now, mid))
        except Exception:
            continue
        time.sleep(delay)
    conn.commit()
    return new_updates
```

- [ ] **Step 4: 追加 UP 主更新测试**

`tests/test_monitor.py` 追加：
```python
def test_check_updates_detects_new(monkeypatch, tmp_path):
    from app.monitor import check_updates

    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    conn.execute("INSERT INTO followings (mid, uname) VALUES (1, 'UP甲')")
    conn.execute("INSERT INTO updates (mid, last_bvid, last_pubdate, checked_at) VALUES (1, 'BV_OLD', 1, 1)")
    conn.commit()

    def handler(request):
        return httpx.Response(200, json={"code": 0, "data": {"list": {"vlist": [
            {"bvid": "BV_NEW", "title": "新视频", "created": 999},
        ]}}})

    # 需要 nav 返回 wbi keys
    def nav_handler(request):
        return httpx.Response(200, json={"code": 0, "data": {"wbi_img": {
            "img_url": "https://i0.hdslb.com/bfs/wbi/7cd084941338484aae1ad9425b84077c.png",
            "sub_url": "https://i0.hdslb.com/bfs/wbi/4932caff0ff746eab6f01bf08b70ac45.png",
        }}})

    calls = {"n": 0}

    def handler(request):
        if "/x/space/wbi/arc/search" in request.url.path:
            return httpx.Response(200, json={"code": 0, "data": {"list": {"vlist": [
                {"bvid": "BV_NEW", "title": "新视频", "created": 999}]}}})
        return nav_handler(request)

    n = check_updates(conn, make_client(handler), limit=5, delay=0)
    assert n == 1
    assert conn.execute("SELECT last_bvid FROM updates WHERE mid=1").fetchone()[0] == "BV_NEW"
    assert conn.execute("SELECT COUNT(*) FROM alerts WHERE type='update'").fetchone()[0] == 1
    conn.close()
```

- [ ] **Step 5: 运行全部相关测试**

Run: `python -m pytest tests/test_wbi.py tests/test_monitor.py -v`
Expected: 全部通过

- [ ] **Step 6: 提交**

```bash
git add app/bilibili/wbi.py app/bilibili/client.py app/monitor.py tests/test_wbi.py tests/test_monitor.py
git commit -m "feat: M2 WBI 签名与 UP 主更新检测"
```

---

### Task 4: APScheduler 定时任务

**Files:**
- Modify: `requirements.txt`（追加 `APScheduler==3.11.0`）
- Create: `app/scheduler.py`
- Modify: `app/main.py`（lifespan 启动 scheduler）
- Test: `tests/test_scheduler.py`

**Interfaces:**
- Consumes: `run_full_sync`、`check_invalid`、`check_updates`、`get_cookies`、`get_conn`
- Produces: `start_scheduler() -> BackgroundScheduler`（幂等，防重复启动）

- [ ] **Step 1: 装依赖 + 写测试**

```bash
python -m pip install APScheduler==3.11.0
```

`tests/test_scheduler.py`：
```python
from __future__ import annotations

from app.scheduler import start_scheduler


def test_scheduler_registers_jobs():
    sched = start_scheduler()
    try:
        jobs = {j.id for j in sched.get_jobs()}
        assert {"sync", "invalid", "updates"} <= jobs
    finally:
        sched.shutdown(wait=False)


def test_scheduler_idempotent():
    s1 = start_scheduler()
    s2 = start_scheduler()
    try:
        assert s1 is s2
    finally:
        s1.shutdown(wait=False)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_scheduler.py -v`
Expected: FAIL（app.scheduler 不存在）

- [ ] **Step 3: 写实现**

`app/scheduler.py`：
```python
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
    from app.monitor import check_invalid, check_updates
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

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(job_sync, "cron", hour=3, minute=0, id="sync")
    _scheduler.add_job(job_invalid, "cron", hour=4, minute=0, id="invalid")
    _scheduler.add_job(job_updates, "interval", hours=6, id="updates")
    _scheduler.start()
    return _scheduler
```

`app/main.py` lifespan 修改：
```python
@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    from app.scheduler import start_scheduler
    start_scheduler()
    yield
```

`requirements.txt` 追加 `APScheduler==3.11.0`。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_scheduler.py -v`
Expected: 2 passed

- [ ] **Step 5: 提交**

```bash
git add requirements.txt app/scheduler.py app/main.py tests/test_scheduler.py
git commit -m "feat: M2 APScheduler 定时任务"
```

---

### Task 5: 监测中心 API

**Files:**
- Modify: `app/api.py`（`/api/monitor/run`、`/api/monitor/invalid`、`/api/monitor/updates`）
- Test: `tests/test_monitor_api.py`

**Interfaces:**
- Consumes: `check_invalid`、`check_updates`、`get_cookies`
- Produces:
  - `POST /api/monitor/run` → `{"invalid": n, "updates": n}`（未登录 401）
  - `GET /api/monitor/invalid` → `[{id,bvid,source,checked_at}]`
  - `GET /api/monitor/updates` → `[{mid,uname,last_bvid,last_pubdate,checked_at}]`

- [ ] **Step 1: 写失败的测试**

`tests/test_monitor_api.py`：
```python
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import config, database
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean(tmp_path):
    config.set_config_path(tmp_path / "config.json")
    database.set_db_path(tmp_path / "t.db")
    database.init_db()


def test_run_requires_login():
    assert client.post("/api/monitor/run").status_code == 401


def test_run_and_lists(monkeypatch):
    import app.api as api_mod
    config.save_cookies({"SESSDATA": "abc"})
    monkeypatch.setattr(api_mod, "check_invalid", lambda conn, client, **kw: 2)
    monkeypatch.setattr(api_mod, "check_updates", lambda conn, client, **kw: 1)

    r = client.post("/api/monitor/run")
    assert r.status_code == 200
    assert r.json() == {"invalid": 2, "updates": 1}


def test_invalid_and_updates_lists():
    conn = database.get_conn()
    conn.execute("INSERT INTO invalid_items (bvid, source, checked_at) VALUES ('BV1', 'check', 100)")
    conn.execute("INSERT INTO followings (mid, uname) VALUES (1, 'UP甲')")
    conn.execute("INSERT INTO updates (mid, last_bvid, last_pubdate, checked_at) VALUES (1, 'BVX', 50, 60)")
    conn.commit()
    conn.close()

    invalid = client.get("/api/monitor/invalid").json()
    assert len(invalid) == 1 and invalid[0]["bvid"] == "BV1"

    updates = client.get("/api/monitor/updates").json()
    assert len(updates) == 1 and updates[0]["uname"] == "UP甲"
```

> 说明：`test_run_and_lists` 通过替换 `app.api.check_invalid/check_updates` 的名字来隔离真实网络。`/api/monitor/run` 的实现需 `from app.monitor import check_invalid, check_updates`，这样测试可 patch 接口模块里的引用。

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_monitor_api.py -v`
Expected: FAIL（404）

- [ ] **Step 3: 写实现**

`app/api.py` 追加（顶部 import 增加）：
```python
from app.monitor import check_invalid, check_updates
```

路由：
```python
@router.post("/monitor/run")
def monitor_run() -> dict:
    if not get_cookies():
        raise HTTPException(status_code=401, detail="未登录，请先扫码登录")
    conn = get_conn()
    init_db(conn)
    try:
        from app.bilibili.client import BiliClient
        with BiliClient(cookies=get_cookies()) as client:
            n_invalid = check_invalid(conn, client, limit=100)
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_monitor_api.py -v`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add app/api.py tests/test_monitor_api.py
git commit -m "feat: M2 监测中心 API"
```

---

### Task 6: 前端监测中心页 + 未读角标

**Files:**
- Modify: `web/js/app.js`（新增 Monitor 组件、侧边栏菜单项、未读角标）
- Modify: `web/css/style.css`（角标样式）

**Interfaces:**
- Consumes: `GET /api/alerts`、`POST /api/alerts/{id}/read`、`POST /api/monitor/run`、`GET /api/monitor/invalid`、`GET /api/monitor/updates`、`GET /api/status`

- [ ] **Step 1: 追加 Monitor 组件并注册

在 `app.js` 中 `const History` 之前插入 `const Monitor = {...}`：

```javascript
const Monitor = {
  props: ['status'],
  emits: ['refresh'],
  template: `
    <h2>监测中心</h2>
    <div style="margin-bottom:12px">
      <el-button type="primary" @click="run" :loading="running">立即检测</el-button>
      <el-tag v-if="result" style="margin-left:8px">失效 {{ result.invalid }} · UP更新 {{ result.updates }}</el-tag>
    </div>
    <el-tabs v-model="tab">
      <el-tab-pane label="提醒" name="alerts">
        <el-table :data="alerts" style="width:100%">
          <el-table-column prop="title" label="标题" min-width="160"/>
          <el-table-column prop="content" label="内容" min-width="260"/>
          <el-table-column label="时间" width="180">
            <template #default="s">{{ fmt(s.row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="100">
            <template #default="s">
              <el-button v-if="!s.row.read" size="small" @click="markRead(s.row.id)">标为已读</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
      <el-tab-pane label="失效视频" name="invalid">
        <el-table :data="invalidList" style="width:100%">
          <el-table-column prop="bvid" label="BV号" width="180"/>
          <el-table-column prop="source" label="来源" width="100"/>
          <el-table-column label="检测时间" width="180">
            <template #default="s">{{ fmt(s.row.checked_at) }}</template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
      <el-tab-pane label="UP主更新" name="updates">
        <el-table :data="updates" style="width:100%">
          <el-table-column prop="uname" label="UP主" width="160"/>
          <el-table-column prop="last_bvid" label="最新投稿" width="180"/>
          <el-table-column prop="last_pubdate" label="发布时间" width="180">
            <template #default="s">{{ fmt(s.row.last_pubdate) }}</template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>
  `,
  setup(props, { emit }) {
    const tab = ref('alerts');
    const alerts = ref([]); const invalidList = ref([]); const updates = ref([]);
    const running = ref(false); const result = ref(null);
    const fmt = ts => ts ? new Date(ts * 1000).toLocaleString('zh-CN') : '';
    async function loadAll() {
      const d = await api('/alerts');
      alerts.value = d.items;
      invalidList.value = await api('/monitor/invalid');
      updates.value = await api('/monitor/updates');
    }
    async function run() {
      running.value = true;
      try {
        result.value = await api('/monitor/run', { method: 'POST' });
        await loadAll();
        emit('refresh');
      } catch (e) { ElementPlus.ElMessage.error(e.message); }
      finally { running.value = false; }
    }
    async function markRead(id) {
      await api(`/alerts/${id}/read`, { method: 'POST' });
      await loadAll();
      emit('refresh');
    }
    onMounted(() => loadAll().catch(() => {}));
    return { tab, alerts, invalidList, updates, running, result, fmt, run, markRead };
  },
};
```

`App` 模板修改：
- `components` 加 `Monitor`
- 侧边栏菜单加一项：`<el-menu-item index="monitor"><el-icon><Bell/></el-icon>监测中心<el-badge :value="status.alerts_unread || 0" :hidden="!(status.alerts_unread)" style="margin-left:auto;padding-left:12px"/></el-menu-item>`
- `el-main` 加：`<Monitor v-else-if="route === 'monitor'" :status="status" @refresh="loadStatus"/>`

- [ ] **Step 2: 启动服务人工验证**

Run: `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`
Expected:
- 侧边栏出现「监测中心」，有未读提醒时显示红点角标
- 页面三个 tab 正常展示；「立即检测」按钮触发后显示结果数
- 无 JS 报错

- [ ] **Step 3: 提交**

```bash
git add web/js/app.js web/css/style.css
git commit -m "feat: M2 前端监测中心页与未读角标"
```

---

### Task 7: 集成测试 + README + 推送

**Files:**
- Modify: `tests/test_integration.py`（追加监测链路）
- Modify: `README.md`（更新功能与里程碑）

- [ ] **Step 1: 追加集成测试**

`tests/test_integration.py` 追加：
```python
def test_monitor_chain(tmp_path, monkeypatch):
    import app.api as api_mod
    config.save_cookies({"SESSDATA": "abc"})
    monkeypatch.setattr(api_mod, "check_invalid", lambda conn, client, **kw: 1)
    monkeypatch.setattr(api_mod, "check_updates", lambda conn, client, **kw: 0)

    r = client.post("/api/monitor/run")
    assert r.status_code == 200
    assert r.json() == {"invalid": 1, "updates": 0}

    # 写入一条提醒并确认未读数暴露到 status
    from app.notify import add_alert
    conn = database.get_conn()
    add_alert(conn, "invalid", "失效", "BV1")
    conn.commit()
    conn.close()
    assert client.get("/api/status").json()["alerts_unread"] == 1
```

- [ ] **Step 2: 运行全部测试**

Run: `python -m pytest tests/ -v`
Expected: 全部通过（M1 + M2）

- [ ] **Step 3: 更新 README**

`README.md` 功能部分追加：
```markdown
- **M2 监测**：失效视频检测、UP 主更新提醒、定时任务（APScheduler）、监测中心页
```
里程碑部分把 M2 标记 ✅。

- [ ] **Step 4: 提交 + 推送**

```bash
git add tests/test_integration.py README.md
git commit -m "feat: M2 集成测试与 README 更新"
git push origin main
```

---

## 收尾

M2 完成后汇总交付结果。若网络仍不通，push 留待恢复后补推。
