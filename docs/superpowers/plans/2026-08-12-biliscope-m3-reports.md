# BiliScope M3（报告与配置）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 加入观看数据报告（周报/月报）、SMTP 邮件通知、设置页完整化（SMTP 配置/任务间隔）。

**Architecture:** 复用 M1/M2 的 `database`/`api`/`scheduler`/前端结构。新增 `app/report.py`（报告生成）、`app/emailer.py`（SMTP 发送）。前端「设置」页补全 SMTP 表单。config.json 的 `smtp`/`task_interval` 结构在 M1 已定义。

**Tech Stack:** 标准库 `smtplib`/`email`（无新依赖）。

**依赖关系：** Task 1→2（报告），Task 3（邮件），Task 4（配置 API+前端），Task 5（调度扩展，依赖 1/3），Task 6 收尾。

## Global Constraints

- Python ≥ 3.10；测试不得真实发邮件（mock `smtplib.SMTP_SSL`）
- 不新增第三方依赖
- 每个 Task 提交一次 git；M3 完成后推送 GitHub
- 遵循 M1/M2 已有代码模式

---

### Task 1: 报告生成

**Files:**
- Create: `app/report.py`
- Test: `tests/test_report.py`

**Interfaces:**
- Produces:
  - `generate_report(conn, type_: str = "weekly") -> dict`（返回 `{id, period, type, stats}`；写入 reports 表）
  - `report_to_html(stats: dict, period: str) -> str`（生成 HTML 摘要，供邮件/展示）

- [ ] **Step 1: 写失败的测试**

`tests/test_report.py`：
```python
from __future__ import annotations

import json
import time

from app import database
from app.report import generate_report, report_to_html


def seed(conn):
    now = int(time.time())
    conn.execute("INSERT INTO videos (bvid, title, up_name, tname, duration) VALUES ('BV1', 'A', 'UP甲', '动画', 300)")
    conn.execute("INSERT INTO history (bvid, view_at, progress) VALUES ('BV1', ?, 50)", (now - 3600,))
    conn.execute("INSERT INTO videos (bvid, title, up_name, tname, duration) VALUES ('BV2', 'B', 'UP乙', '科技', 400)")
    conn.execute("INSERT INTO history (bvid, view_at, progress) VALUES ('BV2', ?, 20)", (now - 7200,))
    conn.commit()


def test_generate_weekly(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    seed(conn)

    result = generate_report(conn, "weekly")
    assert result["type"] == "weekly"
    assert result["stats"]["views"] == 2
    assert result["stats"]["top_ups"][0]["up_name"] == "UP甲"
    assert len(result["stats"]["tnames"]) == 2

    row = conn.execute("SELECT * FROM reports WHERE id=?", (result["id"],)).fetchone()
    assert json.loads(row["content_json"])["views"] == 2
    conn.close()


def test_report_to_html_contains_numbers():
    html = report_to_html({"views": 3, "top_ups": [], "tnames": [], "hours": []}, "2026-01-01~2026-01-07")
    assert "3" in html
    assert "周报" in html
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_report.py -v`
Expected: FAIL（app.report 不存在）

- [ ] **Step 3: 写实现**

`app/report.py`：
```python
"""观看数据报告生成（周报/月报）。"""
from __future__ import annotations

import json
import sqlite3
import time


def _range(type_: str) -> tuple[int, str]:
    now = int(time.time())
    if type_ == "weekly":
        start = now - 7 * 86400
        period = f"{time.strftime('%Y-%m-%d', time.localtime(start))} ~ {time.strftime('%Y-%m-%d', time.localtime(now))}"
    else:
        start = now - 30 * 86400
        period = f"{time.strftime('%Y-%m-%d', time.localtime(start))} ~ {time.strftime('%Y-%m-%d', time.localtime(now))}"
    return start, period


def generate_report(conn: sqlite3.Connection, type_: str = "weekly") -> dict:
    """聚合最近 7/30 天观看数据并写入 reports 表。"""
    start, period = _range(type_)
    views = conn.execute(
        "SELECT COUNT(*) FROM history WHERE view_at >= ?", (start,)
    ).fetchone()[0]
    top_ups = [dict(r) for r in conn.execute(
        """SELECT v.up_name, COUNT(*) AS n FROM history h
           JOIN videos v ON h.bvid = v.bvid
           WHERE h.view_at >= ? AND v.up_name != ''
           GROUP BY v.up_name ORDER BY n DESC LIMIT 5""",
        (start,),
    ).fetchall()]
    tnames = [dict(r) for r in conn.execute(
        """SELECT v.tname, COUNT(*) AS n FROM history h
           JOIN videos v ON h.bvid = v.bvid
           WHERE h.view_at >= ? AND v.tname != ''
           GROUP BY v.tname ORDER BY n DESC LIMIT 8""",
        (start,),
    ).fetchall()]
    hours = [dict(r) for r in conn.execute(
        """SELECT CAST(strftime('%H', view_at, 'unixepoch', 'localtime') AS INTEGER) AS h, COUNT(*) AS n
           FROM history WHERE view_at >= ? GROUP BY h""",
        (start,),
    ).fetchall()]
    stats = {"views": views, "top_ups": top_ups, "tnames": tnames, "hours": hours}
    cur = conn.execute(
        "INSERT INTO reports (period, type, content_json, created_at) VALUES (?, ?, ?, ?)",
        (period, type_, json.dumps(stats, ensure_ascii=False), int(time.time())),
    )
    conn.commit()
    return {"id": cur.lastrowid, "period": period, "type": type_, "stats": stats}


def report_to_html(stats: dict, period: str) -> str:
    """生成报告 HTML 摘要。"""
    top = "、".join(f"{u['up_name']}({u['n']})" for u in stats.get("top_ups", [])) or "无"
    tnames = "、".join(f"{t['tname']}({t['n']})" for t in stats.get("tnames", [])) or "无"
    return f"""
    <h3>观看报告（{period}）</h3>
    <p>观看视频数：<b>{stats.get('views', 0)}</b></p>
    <p>常看 UP 主 TOP：{top}</p>
    <p>内容分区：{tnames}</p>
    """
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_report.py -v`
Expected: 2 passed

- [ ] **Step 5: 提交**

```bash
git add app/report.py tests/test_report.py
git commit -m "feat: M3 报告生成"
```

---

### Task 2: 报告 API

**Files:**
- Modify: `app/api.py`
- Test: `tests/test_report_api.py`

**Interfaces:**
- Produces:
  - `GET /api/reports` → `[{id,period,type,created_at}]`
  - `GET /api/reports/{id}` → `{id,period,type,created_at,stats}`
  - `POST /api/reports/generate?type=weekly|monthly` → `{id,period,type,stats}`

- [ ] **Step 1: 写失败的测试**

`tests/test_report_api.py`：
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


def test_generate_and_list():
    r = client.post("/api/reports/generate", params={"type": "weekly"})
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "weekly"

    items = client.get("/api/reports").json()
    assert len(items) == 1

    one = client.get(f"/api/reports/{body['id']}").json()
    assert one["stats"]["views"] == 0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_report_api.py -v`
Expected: FAIL（404）

- [ ] **Step 3: 写实现**

`app/api.py` 追加 import 与路由：
```python
from app.report import generate_report
```
```python
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_report_api.py -v`
Expected: 1 passed

- [ ] **Step 5: 提交**

```bash
git add app/api.py tests/test_report_api.py
git commit -m "feat: M3 报告 API"
```

---

### Task 3: 邮件通知

**Files:**
- Create: `app/emailer.py`
- Test: `tests/test_emailer.py`

**Interfaces:**
- Consumes: `load_config`（smtp 配置）、`report_to_html`
- Produces:
  - `send_email(cfg: dict, subject: str, html: str) -> None`（SMTP_SSL 发送）
  - `send_report_email(report: dict) -> bool`（配置齐全才发，返回是否发送）
  - `send_alerts_email(alerts: list[dict]) -> bool`

- [ ] **Step 1: 写失败的测试**

`tests/test_emailer.py`：
```python
from __future__ import annotations

import smtplib
from unittest import mock

from app import emailer


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

    assert sent["args"][0] == "smtp.qq.com"
    assert sent["login"] == ("a@qq.com", "secret")
    assert sent["sendmail"][1] == ["b@qq.com"]
    assert "测试" in sent["sendmail"][2]


def test_send_report_email_skips_without_config():
    from app import config
    import pathlib, tempfile
    config.set_config_path(pathlib.Path(tempfile.mkdtemp()) / "config.json")
    config.save_config({"smtp": {"host": "", "port": 465, "user": "", "password": "", "to": ""}})
    assert emailer.send_report_email({"period": "x", "type": "weekly", "stats": {}}) is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_emailer.py -v`
Expected: FAIL（app.emailer 不存在）

- [ ] **Step 3: 写实现**

`app/emailer.py`：
```python
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_emailer.py -v`
Expected: 2 passed

- [ ] **Step 5: 提交**

```bash
git add app/emailer.py tests/test_emailer.py
git commit -m "feat: M3 邮件通知"
```

---

### Task 4: 配置 API + 设置页完整化

**Files:**
- Modify: `app/api.py`（`/api/config` GET/POST、`/api/config/test-email`）
- Modify: `web/js/app.js`（Settings 页加 SMTP 表单 + 任务间隔 + 测试邮件按钮）
- Test: `tests/test_config_api.py`

**Interfaces:**
- Produces:
  - `GET /api/config` → `{"smtp": {host,port,user,to,password(掩码或空)}, "task_interval": {...}}`
  - `POST /api/config` body `{"smtp": {...}}` → 保存（密码为 `******` 时保持不变）→ `{"ok": true}`
  - `POST /api/config/test-email` → 发送测试邮件 → `{"ok": true}`（未配置 400）

- [ ] **Step 1: 写失败的测试**

`tests/test_config_api.py`：
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


def test_get_config_defaults():
    body = client.get("/api/config").json()
    assert "smtp" in body
    assert "task_interval" in body


def test_post_config_saves_and_masks_password():
    client.post("/api/config", json={"smtp": {
        "host": "smtp.qq.com", "port": 465, "user": "a@qq.com",
        "password": "mysecret", "to": "b@qq.com",
    }})
    cfg = config.load_config()
    assert cfg["smtp"]["password"] == "mysecret"

    body = client.get("/api/config").json()
    assert body["smtp"]["password"] == "******"


def test_post_config_keeps_password_when_masked():
    config.save_config({"smtp": {"host": "smtp.qq.com", "port": 465, "user": "a@qq.com",
                                  "password": "realpw", "to": "b@qq.com"}})
    client.post("/api/config", json={"smtp": {"host": "smtp.qq.com", "password": "******"}})
    assert config.load_config()["smtp"]["password"] == "realpw"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_config_api.py -v`
Expected: FAIL（404）

- [ ] **Step 3: 写实现**

`app/api.py` 追加：
```python
from pydantic import BaseModel


class SmtpPayload(BaseModel):
    host: str | None = None
    port: int | None = None
    user: str | None = None
    password: str | None = None
    to: str | None = None


class ConfigPayload(BaseModel):
    smtp: SmtpPayload | None = None
```
路由：
```python
@router.get("/config")
def config_get() -> dict:
    cfg = load_config()
    smtp = dict(cfg.get("smtp") or {})
    if smtp.get("password"):
        smtp["password"] = "******"
    else:
        smtp["password"] = ""
    return {"smtp": smtp, "task_interval": cfg.get("task_interval")}


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
        if pw and pw != "******":
            smtp["password"] = pw
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
```

`app/api.py` 需要 import `save_config`（检查现有 import，M1 时 `from app.config import get_cookies, load_config`，需补 `save_config`）与 `BaseModel`。

- [ ] **Step 4: 设置页前端**

`web/js/app.js` 中 Settings 组件的 `el-card` 账号块之后追加 SMTP 卡片：
```javascript
      <el-card style="max-width:520px;margin-top:16px">
        <template #header>邮件通知（SMTP）</template>
        <el-form :model="smtp" label-width="80px" label-position="left">
          <el-form-item label="SMTP 主机"><el-input v-model="smtp.host" placeholder="smtp.qq.com"/></el-form-item>
          <el-form-item label="端口"><el-input v-model.number="smtp.port" placeholder="465"/></el-form-item>
          <el-form-item label="邮箱"><el-input v-model="smtp.user" placeholder="发件邮箱"/></el-form-item>
          <el-form-item label="授权码"><el-input v-model="smtp.password" type="password" placeholder="SMTP 授权码"/></el-form-item>
          <el-form-item label="收件人"><el-input v-model="smtp.to" placeholder="收件邮箱"/></el-form-item>
          <el-form-item>
            <el-button type="primary" @click="saveSmtp">保存配置</el-button>
            <el-button @click="testEmail" :loading="testing">发送测试邮件</el-button>
          </el-form-item>
        </el-form>
      </el-card>
```
Settings setup 追加：
```javascript
    const smtp = ref({ host: '', port: 465, user: '', password: '', to: '' });
    const testing = ref(false);
    async function loadConfig() {
      const c = await api('/config');
      smtp.value = { ...c.smtp };
    }
    async function saveSmtp() {
      await api('/config', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ smtp: smtp.value }) });
      ElementPlus.ElMessage.success('配置已保存');
      emit('refresh');
    }
    async function testEmail() {
      testing.value = true;
      try {
        await api('/config/test-email', { method: 'POST' });
        ElementPlus.ElMessage.success('测试邮件已发送');
      } catch (e) { ElementPlus.ElMessage.error(e.message); }
      finally { testing.value = false; }
    }
    onMounted(() => { loadConfig().catch(() => {}); });
    return { ...existing, smtp, testing, saveSmtp, testEmail };
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/test_config_api.py -v`
Expected: 3 passed

- [ ] **Step 6: 提交**

```bash
git add app/api.py web/js/app.js tests/test_config_api.py
git commit -m "feat: M3 配置 API 与设置页完整化"
```

---

### Task 5: 定时任务扩展（周报/月报）

**Files:**
- Modify: `app/scheduler.py`（追加周报/月报任务）
- Modify: `tests/test_scheduler.py`（断言新增 job id）

**Interfaces:**
- Consumes: `generate_report`、`send_report_email`

- [ ] **Step 1: 更新测试**

`tests/test_scheduler.py` 断言改为：
```python
        assert {"sync", "invalid", "updates", "report_weekly", "report_monthly"} <= jobs
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_scheduler.py -v`
Expected: FAIL（缺 report_weekly/report_monthly）

- [ ] **Step 3: 写实现**

`app/scheduler.py` 追加 import 与任务：
```python
    from app.emailer import send_report_email
    from app.report import generate_report
```
```python
    def job_report(kind: str) -> None:
        try:
            conn = get_conn()
            init_db(conn)
            report = generate_report(conn, kind)
            conn.close()
            send_report_email(report)
        except Exception:
            pass
```
注册：
```python
    _scheduler.add_job(lambda: job_report("weekly"), "cron", day_of_week="sun", hour=5, minute=0, id="report_weekly")
    _scheduler.add_job(lambda: job_report("monthly"), "cron", day=1, hour=5, minute=0, id="report_monthly")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_scheduler.py -v`
Expected: 2 passed

- [ ] **Step 5: 提交**

```bash
git add app/scheduler.py tests/test_scheduler.py
git commit -m "feat: M3 周报/月报定时任务"
```

---

### Task 6: 集成测试 + README + 推送

**Files:**
- Modify: `tests/test_integration.py`（追加报告链路）
- Modify: `README.md`

- [ ] **Step 1: 追加集成测试**

`tests/test_integration.py` 追加：
```python
def test_report_chain():
    from app.report import generate_report
    conn = database.get_conn()
    result = generate_report(conn, "weekly")
    conn.close()

    items = client.get("/api/reports").json()
    assert len(items) == 1
    detail = client.get(f"/api/reports/{result['id']}").json()
    assert detail["type"] == "weekly"
```

- [ ] **Step 2: 运行全部测试**

Run: `python -m pytest tests/ -v`
Expected: 全部通过（M1+M2+M3）

- [ ] **Step 3: 更新 README**

功能部分追加：
```markdown
## 功能（M3 报告与配置）

- 观看数据周报/月报：观看量、常看 UP 主、分区分布
- SMTP 邮件通知：报告/提醒发到邮箱
- 设置页完整化：SMTP 配置、测试邮件、任务间隔
```
里程碑：M3 标 ✅。

- [ ] **Step 4: 提交 + 推送**

```bash
git add tests/test_integration.py README.md
git commit -m "feat: M3 集成测试与 README 更新"
git push origin main
```

---

## 收尾

M3 完成后汇总交付结果。
