# BiliScope M4（内容分析）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用可插拔 LLM（Claude / OpenAI 兼容 / Ollama）分析视频「标题+简介」，生成内容标签与摘要，聚合出主题分布，并按硬件自动推荐本地模型。

**Architecture:** 新增 `app/llm/`（提供层：base 抽象 + anthropic/openai/ollama 三个 provider + 工厂）、`app/analyze.py`（分析编排）、`app/hardware.py`（硬件检测+模型推荐）。DB 增加 `videos.desc` 列与 `video_analysis` 表。前端新增「内容分析」页与设置页 LLM 配置。

**Tech Stack:** 新增依赖 `anthropic`、`openai`、`psutil`、`nvidia-ml-py`（后两者可选）。

**依赖关系：** Task 1（DB+配置）→ 2/3（LLM 提供层）→ 4/5（分析编排+聚合）→ 6（API）→ 7（前端）→ 8（收尾）。

## Global Constraints

- Python ≥ 3.10；测试不得真实调用 LLM API（注入 fake client / monkeypatch）
- 新增依赖锁定：`anthropic`、`openai`、`psutil`（`nvidia-ml-py` 可选，检测不到 GPU 时静默降级）
- 每个 Task 提交一次 git；M4 完成后推送 GitHub
- LLM 配置存 config.json `llm` 块，provider 可切换

---

### Task 1: DB 迁移 + LLM 配置

**Files:**
- Modify: `app/database.py`（videos 加 desc、新增 video_analysis 表、init_db 迁移）
- Modify: `app/config.py`（DEFAULT_CONFIG 加 llm 块）
- Test: `tests/test_database.py`（追加）

**Interfaces:**
- Produces:
  - `videos` 表含 `desc TEXT` 列（旧库自动 ALTER）
  - `video_analysis` 表：`bvid PRIMARY KEY, tags_json TEXT, summary TEXT, analyzed_at INTEGER, model TEXT`
  - `DEFAULT_CONFIG["llm"] = {"provider": "ollama", "api_key": "", "base_url": "", "model": ""}`

- [ ] **Step 1: 追加测试**

`tests/test_database.py` 追加：
```python
def test_videos_has_desc_and_analysis_table(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    cols = {r[1] for r in conn.execute("PRAGMA table_info(videos)")}
    assert "desc" in cols
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "video_analysis" in tables
    conn.close()


def test_old_db_migrates_desc_column(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    conn = database.get_conn()
    conn.execute("CREATE TABLE videos (bvid TEXT PRIMARY KEY, title TEXT)")  # 旧表无 desc
    conn.commit()
    conn.close()
    database.init_db()  # 应迁移
    conn = database.get_conn()
    cols = {r[1] for r in conn.execute("PRAGMA table_info(videos)")}
    assert "desc" in cols
    conn.close()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_database.py -v`
Expected: FAIL（缺 desc / video_analysis）

- [ ] **Step 3: 写实现**

`app/database.py`：
- SCHEMA 中 videos 定义加 `desc TEXT,`（在 `updated_at INTEGER` 前）
- SCHEMA 末尾追加：
```sql
CREATE TABLE IF NOT EXISTS video_analysis (
    bvid TEXT PRIMARY KEY,
    tags_json TEXT,
    summary TEXT,
    analyzed_at INTEGER,
    model TEXT
);
```
- init_db 迁移：
```python
def init_db(conn: sqlite3.Connection | None = None) -> None:
    conn = conn or get_conn()
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.commit()


def _migrate(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(videos)")}
    if "desc" not in cols:
        conn.execute("ALTER TABLE videos ADD COLUMN desc TEXT")
```

`app/config.py` DEFAULT_CONFIG 加：
```python
    "llm": {"provider": "ollama", "api_key": "", "base_url": "", "model": ""},
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_database.py -v`
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add app/database.py app/config.py tests/test_database.py
git commit -m "feat: M4 DB 迁移与 LLM 配置"
```

---

### Task 2: LLM 提供层（base + anthropic）

**Files:**
- Create: `app/llm/__init__.py`（占位，Task 3 填充）
- Create: `app/llm/base.py`
- Create: `app/llm/anthropic_provider.py`
- Test: `tests/test_llm_anthropic.py`

**Interfaces:**
- Produces:
  - `app.llm.base.VideoTags`（Pydantic：tags: list[str], summary: str）
  - `app.llm.base.LLMClient`（ABC，`analyze_video(title, desc) -> VideoTags`）
  - `app.llm.anthropic_provider.AnthropicLLM(api_key, model="claude-haiku-4-5", client=None)`

- [ ] **Step 1: 写失败的测试**

`tests/test_llm_anthropic.py`：
```python
from __future__ import annotations

import pytest

from app.llm.anthropic_provider import AnthropicLLM
from app.llm.base import VideoTags


class FakeMessage:
    parsed_output = VideoTags(tags=["科技", "AI"], summary="讲人工智能")


class FakeMessages:
    def parse(self, **kw):
        captured["kw"] = kw
        return FakeMessage()


captured = {}


def test_anthropic_analyze_video():
    captured.clear()
    fake = type("FakeClient", (), {"messages": FakeMessages()})()
    llm = AnthropicLLM(api_key="k", model="claude-haiku-4-5", client=fake)
    result = llm.analyze_video("标题", "简介")
    assert result.tags == ["科技", "AI"]
    assert captured["kw"]["model"] == "claude-haiku-4-5"
    assert "标题" in captured["kw"]["messages"][0]["content"]
    assert captured["kw"]["output_format"] is VideoTags


def test_anthropic_default_model():
    llm = AnthropicLLM(api_key="k")
    assert llm.model == "claude-haiku-4-5"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_llm_anthropic.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 写实现**

`app/llm/base.py`：
```python
"""LLM 提供层抽象。"""
from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel


class VideoTags(BaseModel):
    tags: list[str]
    summary: str


class LLMClient(ABC):
    @abstractmethod
    def analyze_video(self, title: str, desc: str) -> VideoTags:
        ...


PROMPT = """根据视频的标题和简介，用 3-5 个中文标签概括其内容主题，并写一句话中文总结。
标题：{title}
简介：{desc}
"""
```

`app/llm/anthropic_provider.py`：
```python
"""Anthropic Claude provider。"""
from __future__ import annotations

import anthropic

from app.llm.base import LLMClient, PROMPT, VideoTags


class AnthropicLLM(LLMClient):
    def __init__(self, api_key: str, model: str = "claude-haiku-4-5",
                 client: anthropic.Anthropic | None = None) -> None:
        self.model = model
        self.client = client or anthropic.Anthropic(api_key=api_key)

    def analyze_video(self, title: str, desc: str) -> VideoTags:
        msg = self.client.messages.parse(
            model=self.model,
            max_tokens=512,
            output_format=VideoTags,
            messages=[{"role": "user", "content": PROMPT.format(title=title, desc=desc)}],
        )
        return msg.parsed_output
```

`app/llm/__init__.py`（占位）：
```python
"""LLM 提供层（Task 3 填充工厂）。"""
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_llm_anthropic.py -v`
Expected: 2 passed

- [ ] **Step 5: 提交**

```bash
git add app/llm tests/test_llm_anthropic.py
git commit -m "feat: M4 LLM 提供层 base + anthropic"
```

---

### Task 3: OpenAI/Ollama provider + 工厂

**Files:**
- Create: `app/llm/openai_provider.py`
- Create: `app/llm/ollama_provider.py`
- Modify: `app/llm/__init__.py`（工厂）
- Test: `tests/test_llm_providers.py`

**Interfaces:**
- Produces:
  - `OpenAIClient(api_key, base_url=None, model="deepseek-chat", client=None)`（OpenAI 兼容，json_object 模式）
  - `OllamaClient(model="qwen2.5:7b", base_url="http://localhost:11434", session=None)`（本地 HTTP）
  - `get_llm_client(cfg: dict) -> LLMClient`（按 provider 选择）

- [ ] **Step 1: 写失败的测试**

`tests/test_llm_providers.py`：
```python
from __future__ import annotations

import json

from app.llm import get_llm_client
from app.llm.openai_provider import OpenAIClient
from app.llm.ollama_provider import OllamaClient


class FakeChoices:
    class M:
        content = json.dumps({"tags": ["游戏"], "summary": "评测"}, ensure_ascii=False)
    choices = [M()]


class FakeOpenAI:
    def __init__(self, *a, **kw):
        self.kw = kw
    class chat:
        class completions:
            @staticmethod
            def create(**kw):
                captured["kw"] = kw
                return FakeChoices()


captured = {}


def test_openai_analyze_video():
    captured.clear()
    fake = type("FakeClient", (), {"chat": FakeOpenAI.chat})()
    llm = OpenAIClient(api_key="k", client=fake)
    r = llm.analyze_video("标题", "简介")
    assert r.tags == ["游戏"]
    assert captured["kw"]["response_format"] == {"type": "json_object"}


def test_ollama_analyze_video(monkeypatch):
    sent = {}

    def fake_post(url, json=None, timeout=None):
        sent["url"] = url
        sent["json"] = json
        class Resp:
            def json(self):
                return {"message": {"content": json.dumps({"tags": ["音乐"], "summary": "演奏"})}}
        return Resp()

    monkeypatch.setattr("app.llm.ollama_provider.requests.post", fake_post)
    llm = OllamaClient(model="qwen2.5:7b")
    r = llm.analyze_video("标题", "简介")
    assert r.tags == ["音乐"]
    assert "localhost:11434" in sent["url"]
    assert sent["json"]["format"] == "json"


def test_factory_provider_selection():
    assert isinstance(get_llm_client({"provider": "anthropic", "api_key": "k"}),
                      __import__("app.llm.anthropic_provider", fromlist=["AnthropicLLM"]).AnthropicLLM)
    assert isinstance(get_llm_client({"provider": "openai", "api_key": "k"}),
                      OpenAIClient)
    assert isinstance(get_llm_client({"provider": "ollama"}), OllamaClient)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_llm_providers.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 写实现**

`app/llm/openai_provider.py`：
```python
"""OpenAI 兼容 provider（DeepSeek / 通义 / Kimi 等）。"""
from __future__ import annotations

import json

from openai import OpenAI

from app.llm.base import LLMClient, PROMPT, VideoTags


class OpenAIClient(LLMClient):
    def __init__(self, api_key: str, base_url: str | None = None,
                 model: str = "deepseek-chat", client: OpenAI | None = None) -> None:
        self.model = model
        self.client = client or (OpenAI(api_key=api_key, base_url=base_url) if base_url
                                 else OpenAI(api_key=api_key))

    def analyze_video(self, title: str, desc: str) -> VideoTags:
        resp = self.client.chat.completions.create(
            model=self.model,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content":
                       PROMPT.format(title=title, desc=desc) +
                       '\n请以 JSON 返回 {"tags": ["标签1","标签2"], "summary": "一句话总结"}。'}],
        )
        text = resp.choices[0].message.content
        data = json.loads(text)
        return VideoTags(tags=data["tags"], summary=data["summary"])
```

`app/llm/ollama_provider.py`：
```python
"""本地 Ollama provider。"""
from __future__ import annotations

import json

import requests

from app.llm.base import LLMClient, PROMPT, VideoTags


class OllamaClient(LLMClient):
    def __init__(self, model: str = "qwen2.5:7b",
                 base_url: str = "http://localhost:11434",
                 session: requests.Session | None = None) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.session = session

    def analyze_video(self, title: str, desc: str) -> VideoTags:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content":
                          PROMPT.format(title=title, desc=desc) +
                          '\n只输出 JSON：{"tags": [...], "summary": "..."}'}],
            "format": "json",
            "stream": False,
        }
        if self.session:
            resp = self.session.post(f"{self.base_url}/api/chat", json=payload, timeout=120)
        else:
            resp = requests.post(f"{self.base_url}/api/chat", json=payload, timeout=120)
        content = resp.json()["message"]["content"]
        data = json.loads(content)
        return VideoTags(tags=data["tags"], summary=data["summary"])
```

`app/llm/__init__.py`：
```python
"""LLM 提供层：按配置选择 provider。"""
from __future__ import annotations

from app.llm.anthropic_provider import AnthropicLLM
from app.llm.base import LLMClient, VideoTags
from app.llm.ollama_provider import OllamaClient
from app.llm.openai_provider import OpenAIClient


def get_llm_client(cfg: dict) -> LLMClient:
    provider = cfg.get("provider", "ollama")
    api_key = cfg.get("api_key", "")
    base_url = cfg.get("base_url", "")
    model = cfg.get("model", "")
    if provider == "anthropic":
        return AnthropicLLM(api_key=api_key, model=model or "claude-haiku-4-5")
    if provider == "openai":
        return OpenAIClient(api_key=api_key, base_url=base_url or None,
                            model=model or "deepseek-chat")
    return OllamaClient(model=model or "qwen2.5:7b", base_url=base_url or "http://localhost:11434")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_llm_providers.py -v`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add app/llm tests/test_llm_providers.py
git commit -m "feat: M4 OpenAI/Ollama provider 与工厂"
```

---

### Task 4: 简介补采 + 分析编排

**Files:**
- Modify: `app/sync.py`（`sync_descriptions`）
- Create: `app/analyze.py`
- Test: `tests/test_analyze.py`

**Interfaces:**
- Produces:
  - `sync_descriptions(conn, client, limit=100) -> int`（补拉 videos.desc）
  - `analyze_unanalyzed(conn, llm_client, limit=50) -> int`（分析未分析视频并写入 video_analysis）
  - `analysis_stats(conn) -> dict`（`{analyzed, total}`）

- [ ] **Step 1: 写失败的测试**

`tests/test_analyze.py`：
```python
from __future__ import annotations

from app import database
from app.analyze import analyze_unanalyzed, analysis_stats
from app.llm.base import VideoTags


class FakeLLM:
    def analyze_video(self, title, desc):
        return VideoTags(tags=["科技"], summary=f"关于{title}")


def test_sync_descriptions(tmp_path):
    from app.sync import sync_descriptions

    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    conn.execute("INSERT INTO videos (bvid, title) VALUES ('BV1', 'A')")
    conn.commit()

    class FakeClient:
        def get_json(self, path, params=None):
            return {"code": 0, "data": {"desc": "这是简介"}}

    n = sync_descriptions(conn, FakeClient(), limit=10)
    assert n == 1
    assert conn.execute("SELECT desc FROM videos WHERE bvid='BV1'").fetchone()[0] == "这是简介"
    conn.close()


def test_analyze_unanalyzed(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    conn.execute("INSERT INTO videos (bvid, title, desc) VALUES ('BV1', 'A', '简介1')")
    conn.execute("INSERT INTO videos (bvid, title, desc) VALUES ('BV2', 'B', '简介2')")
    conn.commit()

    n = analyze_unanalyzed(conn, FakeLLM(), limit=10)
    assert n == 2
    assert conn.execute("SELECT COUNT(*) FROM video_analysis").fetchone()[0] == 2

    # 已分析的跳过
    n2 = analyze_unanalyzed(conn, FakeLLM(), limit=10)
    assert n2 == 0

    stats = analysis_stats(conn)
    assert stats["analyzed"] == 2 and stats["total"] == 2
    conn.close()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_analyze.py -v`
Expected: FAIL（app.analyze 不存在）

- [ ] **Step 3: 写实现**

`app/sync.py` 追加：
```python
def sync_descriptions(conn: sqlite3.Connection, client: BiliClient,
                      limit: int = 100, delay: float = 0.3) -> int:
    """补拉视频简介（videos.desc）。返回更新的条数。"""
    rows = conn.execute(
        "SELECT bvid FROM videos WHERE desc IS NULL OR desc = '' LIMIT ?",
        (limit,),
    ).fetchall()
    n = 0
    for row in rows:
        try:
            data = client.get_json("/x/web-interface/view", {"bvid": row["bvid"]})
            desc = data.get("data", {}).get("desc", "")
            if desc:
                conn.execute("UPDATE videos SET desc = ? WHERE bvid = ?", (desc, row["bvid"]))
                n += 1
        except BiliError:
            continue
        time.sleep(delay)
    conn.commit()
    return n
```

`app/analyze.py`：
```python
"""内容分析编排：把视频标题+简介交给 LLM 生成标签并入库。"""
from __future__ import annotations

import json
import sqlite3
import time

from app.llm.base import LLMClient


def analyze_unanalyzed(conn: sqlite3.Connection, llm_client: LLMClient,
                       limit: int = 50) -> int:
    rows = conn.execute(
        """SELECT bvid, title, desc FROM videos
           WHERE desc IS NOT NULL AND desc != ''
             AND bvid NOT IN (SELECT bvid FROM video_analysis)
           LIMIT ?""",
        (limit,),
    ).fetchall()
    n = 0
    model = getattr(llm_client, "model", "")
    for row in rows:
        try:
            result = llm_client.analyze_video(row["title"], row["desc"])
            conn.execute(
                "INSERT OR REPLACE INTO video_analysis (bvid, tags_json, summary, analyzed_at, model) VALUES (?, ?, ?, ?, ?)",
                (row["bvid"], json.dumps(result.tags, ensure_ascii=False), result.summary,
                 int(time.time()), model),
            )
            n += 1
        except Exception:
            continue
    conn.commit()
    return n


def analysis_stats(conn: sqlite3.Connection) -> dict:
    analyzed = conn.execute("SELECT COUNT(*) FROM video_analysis").fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM videos WHERE desc IS NOT NULL AND desc != ''").fetchone()[0]
    return {"analyzed": analyzed, "total": total}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_analyze.py -v`
Expected: 2 passed

- [ ] **Step 5: 提交**

```bash
git add app/sync.py app/analyze.py tests/test_analyze.py
git commit -m "feat: M4 简介补采与分析编排"
```

---

### Task 5: 主题聚合 + 硬件检测

**Files:**
- Modify: `app/analyze.py`（`aggregate_themes`）
- Create: `app/hardware.py`
- Test: `tests/test_hardware.py`、`tests/test_analyze.py`（追加）

**Interfaces:**
- Produces:
  - `aggregate_themes(conn, limit=20) -> list[dict]`（`[{tag, n}]` 按出现次数降序）
  - `detect_hardware() -> dict`（cpu/ram_gb/gpu）
  - `recommend_ollama_model(hw: dict) -> str`

- [ ] **Step 1: 追加测试**

`tests/test_analyze.py` 追加：
```python
def test_aggregate_themes(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    conn.execute("INSERT INTO video_analysis (bvid, tags_json, summary) VALUES ('BV1', '[\"科技\",\"AI\"]', 'a')")
    conn.execute("INSERT INTO video_analysis (bvid, tags_json, summary) VALUES ('BV2', '[\"科技\",\"游戏\"]', 'b')")
    conn.commit()

    themes = __import__("app.analyze", fromlist=["aggregate_themes"]).aggregate_themes(conn)
    by_tag = {t["tag"]: t["n"] for t in themes}
    assert by_tag["科技"] == 2
    assert by_tag["AI"] == 1
    conn.close()
```

`tests/test_hardware.py`：
```python
from __future__ import annotations

from app.hardware import recommend_ollama_model


def test_recommend_by_gpu_vram():
    assert recommend_ollama_model({"gpu": [{"vram_gb": 6}]}) == "qwen2.5:7b"
    assert recommend_ollama_model({"gpu": [{"vram_gb": 10}]}) == "qwen2.5:14b"
    assert recommend_ollama_model({"gpu": [{"vram_gb": 18}]}) == "qwen2.5:32b"


def test_recommend_by_ram_no_gpu():
    assert recommend_ollama_model({"gpu": [], "ram_gb": 8}) == "qwen2.5:3b"
    assert recommend_ollama_model({"gpu": [], "ram_gb": 16}) == "qwen2.5:7b"
    assert recommend_ollama_model({"gpu": [], "ram_gb": 4}) == "qwen2.5:1.5b"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_hardware.py -v`
Expected: FAIL（app.hardware 不存在）

- [ ] **Step 3: 写实现**

`app/analyze.py` 追加：
```python
def aggregate_themes(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    rows = conn.execute("SELECT tags_json FROM video_analysis").fetchall()
    counter: dict[str, int] = {}
    for row in rows:
        try:
            tags = json.loads(row["tags_json"] or "[]")
        except json.JSONDecodeError:
            continue
        for t in tags:
            counter[t] = counter.get(t, 0) + 1
    return sorted(
        ({"tag": k, "n": v} for k, v in counter.items()),
        key=lambda x: x["n"], reverse=True,
    )[:limit]
```

`app/hardware.py`：
```python
"""硬件检测与本地模型推荐。"""
from __future__ import annotations

import os
import shutil


def detect_hardware() -> dict:
    try:
        import psutil
        ram_gb = round(psutil.virtual_memory().total / (1024 ** 3))
        cpu = os.cpu_count() or 0
    except ImportError:
        ram_gb = 0
        cpu = os.cpu_count() or 0

    gpus = []
    # NVIDIA：优先 pynvml，其次 nvidia-smi
    try:
        from pynvml import (nvmlInit, nvmlDeviceGetCount, nvmlDeviceGetHandleByIndex,
                            nvmlDeviceGetMemoryInfo, nvmlShutdown)
        nvmlInit()
        for i in range(nvmlDeviceGetCount()):
            handle = nvmlDeviceGetHandleByIndex(i)
            mem = nvmlDeviceGetMemoryInfo(handle)
            gpus.append({"vram_gb": round(mem.total / (1024 ** 3))})
        nvmlShutdown()
    except Exception:
        if shutil.which("nvidia-smi"):
            import subprocess, re
            out = subprocess.run(["nvidia-smi", "--query-gpu=memory.total",
                                  "--format=csv,noheader,nounits"],
                                 capture_output=True, text=True).stdout
            for line in out.strip().splitlines():
                m = re.search(r"(\d+)", line)
                if m:
                    gpus.append({"vram_gb": round(int(m.group(1)) / 1024)})
    return {"cpu": cpu, "ram_gb": ram_gb, "gpu": gpus}


def recommend_ollama_model(hw: dict) -> str:
    gpus = hw.get("gpu") or []
    if gpus:
        vram = max(g["vram_gb"] for g in gpus)
        if vram >= 16:
            return "qwen2.5:32b"
        if vram >= 8:
            return "qwen2.5:14b"
        if vram >= 4:
            return "qwen2.5:7b"
        return "qwen2.5:1.5b"
    ram = hw.get("ram_gb") or 0
    if ram >= 16:
        return "qwen2.5:7b"
    if ram >= 8:
        return "qwen2.5:3b"
    if ram >= 4:
        return "qwen2.5:1.5b"
    return "qwen2.5:0.5b"
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_hardware.py tests/test_analyze.py -v`
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add app/analyze.py app/hardware.py tests/test_hardware.py tests/test_analyze.py
git commit -m "feat: M4 主题聚合与硬件检测"
```

---

### Task 6: 内容分析 API

**Files:**
- Modify: `app/api.py`
- Test: `tests/test_analysis_api.py`

**Interfaces:**
- Produces:
  - `POST /api/analysis/run?limit=` → `{analyzed: n}`（未登录 401；需 config.llm 已配）
  - `GET /api/analysis/themes` → `[{tag, n}]`
  - `GET /api/analysis/status` → `{analyzed, total}`
  - `GET /api/hardware` → `{cpu, ram_gb, gpu, recommended_model}`

- [ ] **Step 1: 写失败的测试**

`tests/test_analysis_api.py`：
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
    assert client.post("/api/analysis/run").status_code == 401


def test_run_and_themes(monkeypatch):
    import app.api as api_mod
    config.save_cookies({"SESSDATA": "abc"})
    config.save_config({**config.load_config(), "llm": {"provider": "ollama", "api_key": "", "base_url": "", "model": "qwen2.5:7b"}})
    monkeypatch.setattr(api_mod, "analyze_unanalyzed", lambda conn, llm_client, limit=50: 3)

    r = client.post("/api/analysis/run", params={"limit": 10})
    assert r.status_code == 200
    assert r.json() == {"analyzed": 3}


def test_analysis_status_and_themes():
    conn = database.get_conn()
    conn.execute("INSERT INTO video_analysis (bvid, tags_json, summary) VALUES ('BV1', '[\"科技\"]', 'a')")
    conn.commit()
    conn.close()

    assert client.get("/api/analysis/status").json()["analyzed"] == 1
    themes = client.get("/api/analysis/themes").json()
    assert themes[0]["tag"] == "科技"


def test_hardware_endpoint():
    body = client.get("/api/hardware").json()
    assert "recommended_model" in body
    assert "ram_gb" in body
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_analysis_api.py -v`
Expected: FAIL（404）

- [ ] **Step 3: 写实现**

`app/api.py` 追加 import：
```python
from app.analyze import aggregate_themes, analysis_stats, analyze_unanalyzed
from app.config import get_cookies, load_config, save_config
from app.hardware import detect_hardware, recommend_ollama_model
from app.llm import get_llm_client
```
路由：
```python
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


@router.get("/hardware")
def hardware() -> dict:
    hw = detect_hardware()
    hw["recommended_model"] = recommend_ollama_model(hw)
    return hw
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_analysis_api.py -v`
Expected: 4 passed

- [ ] **Step 5: 提交**

```bash
git add app/api.py tests/test_analysis_api.py
git commit -m "feat: M4 内容分析 API"
```

---

### Task 7: 前端分析页 + 设置页 LLM 配置

**Files:**
- Modify: `web/js/app.js`（新增 Analysis 组件、侧边栏项、设置页 LLM 表单）
- Modify: `web/css/style.css`

**Interfaces:**
- Consumes: `POST /api/analysis/run`、`GET /api/analysis/themes`、`GET /api/analysis/status`、`GET /api/hardware`、`GET/POST /api/config`

- [ ] **Step 1: 新增 Analysis 组件并注册

`app.js` 中 `const Overview` 之前插入：
```javascript
const Analysis = {
  template: `
    <h2>内容分析</h2>
    <div style="margin-bottom:12px">
      <el-button type="primary" @click="run" :loading="running">分析未分析视频</el-button>
      <el-tag style="margin-left:8px">已分析 {{ status.analyzed }} / {{ status.total }}</el-tag>
    </div>
    <el-card>
      <template #header>观看内容主题分布</template>
      <div ref="themeChart" class="chart"></div>
    </el-card>
  `,
  setup() {
    const running = ref(false); const status = ref({ analyzed: 0, total: 0 });
    async function run() {
      running.value = true;
      try {
        const r = await api('/analysis/run?limit=50');
        ElementPlus.ElMessage.success(`分析完成：${r.analyzed} 条`);
        await loadStatus();
      } catch (e) { ElementPlus.ElMessage.error(e.message); }
      finally { running.value = false; }
    }
    async function loadStatus() {
      try { status.value = await api('/analysis/status'); } catch (e) {}
    }
    onMounted(async () => {
      await loadStatus();
      const themes = await api('/analysis/themes').catch(() => []);
      nextTick(() => {
        const el = document.querySelector('[data-theme-chart]');
        if (!el) return;
        const chart = echarts.init(el, 'dark');
        chart.setOption({
          title: { text: '主题标签 TOP', textStyle: { fontSize: 14 } },
          tooltip: {},
          xAxis: { type: 'category', data: themes.map(t => t.tag), axisLabel: { rotate: 30 } },
          yAxis: { type: 'value' },
          series: [{ type: 'bar', data: themes.map(t => t.n) }],
        });
      });
    });
    return { running, status, run };
  },
};
```
> 注：`data-theme-chart` 用 `document.querySelector` 定位图表容器（因该组件未用 ref 绑定，统一改用 `ref="themeChart"` 更稳妥——执行时用 `this.$refs` 方案并在 template 中 `ref="themeChart"`）。

- [ ] **Step 2: 注册到 App + 设置页 LLM 表单

App 组件：`components` 加 `Analysis`；菜单加 `<el-menu-item index="analysis"><el-icon><DataAnalysis/></el-icon>内容分析</el-menu-item>`；`el-main` 加 `<Analysis v-else-if="route === 'analysis'"/>`。

Settings 模板（SMTP 卡片之后）追加 LLM 卡片：
```javascript
      <el-card style="max-width:520px;margin-top:16px">
        <template #header>内容分析（LLM）</template>
        <el-form :model="llm" label-width="80px" label-position="left">
          <el-form-item label="提供商">
            <el-select v-model="llm.provider" style="width:100%">
              <el-option label="Ollama（本地免费）" value="ollama"/>
              <el-option label="Claude" value="anthropic"/>
              <el-option label="OpenAI 兼容（DeepSeek等）" value="openai"/>
            </el-select>
          </el-form-item>
          <el-form-item label="API Key"><el-input v-model="llm.api_key" type="password"/></el-form-item>
          <el-form-item label="Base URL"><el-input v-model="llm.base_url" placeholder="OpenAI 兼容地址，如 https://api.deepseek.com/v1"/></el-form-item>
          <el-form-item label="模型"><el-input v-model="llm.model" placeholder="如 qwen2.5:7b / deepseek-chat"/></el-form-item>
          <el-form-item>
            <el-button type="primary" @click="saveLlm">保存</el-button>
            <el-button @click="recommendLocal" :loading="hwLoading">检测硬件推荐模型</el-button>
          </el-form-item>
          <el-form-item v-if="hwModel"><el-tag type="success">推荐：{{ hwModel }}</el-tag></el-form-item>
        </el-form>
      </el-card>
```
Settings setup 追加：
```javascript
    const llm = ref({ provider: 'ollama', api_key: '', base_url: '', model: '' });
    const hwLoading = ref(false); const hwModel = ref('');
    async function loadLlm() {
      const c = await api('/config');
      llm.value = { provider: 'ollama', api_key: '', base_url: '', model: '', ...c.llm };
    }
    async function saveLlm() {
      await api('/config', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ llm: llm.value }) });
      ElementPlus.ElMessage.success('LLM 配置已保存');
    }
    async function recommendLocal() {
      hwLoading.value = true;
      try {
        const h = await api('/hardware');
        hwModel.value = h.recommended_model;
        llm.value.provider = 'ollama';
        llm.value.model = h.recommended_model;
        ElementPlus.ElMessage.success(`推荐 ${h.recommended_model}（内存 ${h.ram_gb}G / 显存 ${(h.gpu[0]?.vram_gb || 0)}G）`);
      } finally { hwLoading.value = false; }
    }
```
`/api/config` 后端需返回/保存 `llm` 块（Task 4 的 config API 未含 llm——执行时在 `config_get`/`config_save` 补齐 llm 字段，见下方 Note）。

> **Note（Task 4 补充）**：`config_get` 返回中加 `"llm": cfg.get("llm")`；`ConfigPayload` 加 `llm: LlmPayload | None`，`config_save` 中合并 `payload.llm`（`api_key` 掩码处理同 password）。执行 Task 7 时一并修改 api.py。

- [ ] **Step 3: 启动服务人工验证**

Run: `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`
Expected: 「内容分析」页正常显示状态与图表；设置页 LLM 表单可切换 provider、保存、「检测硬件推荐模型」能出推荐。

- [ ] **Step 4: 提交**

```bash
git add web/js/app.js web/css/style.css app/api.py
git commit -m "feat: M4 前端分析页与设置页 LLM 配置"
```

---

### Task 8: 集成测试 + README + 推送

**Files:**
- Modify: `tests/test_integration.py`、`README.md`

- [ ] **Step 1: 追加集成测试**

`tests/test_integration.py` 追加：
```python
def test_analysis_chain(monkeypatch):
    import app.api as api_mod
    config.save_cookies({"SESSDATA": "abc"})
    config.save_config({**config.load_config(),
                        "llm": {"provider": "ollama", "api_key": "", "base_url": "", "model": "qwen2.5:7b"}})
    monkeypatch.setattr(api_mod, "analyze_unanalyzed", lambda conn, llm_client, limit=50: 2)

    r = client.post("/api/analysis/run", params={"limit": 10})
    assert r.status_code == 200
    assert r.json() == {"analyzed": 2}

    hw = client.get("/api/hardware").json()
    assert "recommended_model" in hw
```

- [ ] **Step 2: 运行全部测试**

Run: `python -m pytest tests/ -v`
Expected: 全部通过（M1+M2+M3+M4）

- [ ] **Step 3: 更新 README**

功能部分追加：
```markdown
## 功能（M4 内容分析）

- 多 LLM 提供层：Claude / OpenAI 兼容（DeepSeek 等）/ Ollama 本地
- 视频内容标签 + 摘要，主题分布图表
- 硬件检测 + 本地模型自动推荐
```
里程碑：M4 标 ✅。

- [ ] **Step 4: 提交 + 推送**

```bash
git add tests/test_integration.py README.md
git commit -m "feat: M4 集成测试与 README 更新"
git push origin main
```

---

## 收尾

M4 完成后汇总交付结果。
