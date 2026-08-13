# AI 观看画像（里程碑 2a）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 洞察页新增「AI 观看画像」卡片：聚合全部本地观看数据，用 LLM 生成一段观看人格描绘。

**Architecture:** 新建 `app/insights/persona.py`（`generate_persona(conn, llm_client)`，复用 `app.analyze` 聚合函数 + LLM 层 `chat()`），`app/api.py` 加一个薄路由 `POST /api/insights/persona`，前端 `Insights` 组件顶部加卡片。不落库、不新增依赖/表/采集。

**Tech Stack:** FastAPI + SQLite + 现有 `app/llm`（chat 接口）+ Vue3。

**设计文档：** `docs/superpowers/specs/2026-08-14-watching-persona-design.md`

## Global Constraints

- Python ≥ 3.10；测试全部离线（mock LLM client），不得真实请求 LLM / B 站
- 不新增数据库表 / 字段；不新增 Python 依赖
- 模块化：`persona.py` 独立模块 + `tests/test_persona.py` 独立测试文件
- 无 LLM 配置时 API 返回 400（复用 `report_weekly_ai` 的校验方式）
- 画像不落库；`persona` 文案 130-180 字，prompt 要求不罗列数字

---

### Task 1: `app/insights/persona.py` + 测试

**Files:**
- Create: `app/insights/persona.py`
- Create: `tests/test_persona.py`

**Interfaces:**
- Consumes: `app.analyze.watch_profile / up_depth / fav_tnames / category_distribution / time_buckets / watch_completion / popularity`；`app.llm.base.LLMClient.chat(messages) -> ChatResult.text`
- Produces:
  - `app.insights.persona.generate_persona(conn, llm_client) -> {"persona": str, "summary": str}`

- [ ] **Step 1: 写失败的测试**

`tests/test_persona.py`：
```python
from __future__ import annotations

import time

from app import database
from app.insights.persona import generate_persona


class FakeLLM:
    def chat(self, messages, tools=None):
        class R:
            text = "你是个深夜深度学习者，喜欢在安静时刷长视频。"
        return R()


def test_generate_persona(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    now = int(time.time())
    conn.execute("INSERT INTO videos (bvid, title, up_name, tname, duration, view_count) "
                 "VALUES ('BV1', 'A', 'UP甲', '科技', 3000, 50000)")
    conn.execute("INSERT INTO history (bvid, view_at, progress) VALUES ('BV1', ?, 3000)", (now,))
    conn.commit()
    conn.close()

    result = generate_persona(database.get_conn(), FakeLLM())
    assert result["persona"] == "你是个深夜深度学习者，喜欢在安静时刷长视频。"
    assert "总观看" in result["summary"]
    assert "UP甲" in result["summary"]


def test_generate_persona_empty_db(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    result = generate_persona(database.get_conn(), FakeLLM())
    assert result["persona"]
    assert result["summary"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_persona.py -v`
Expected: FAIL（`ModuleNotFoundError: app.insights.persona`）

- [ ] **Step 3: 写实现**

`app/insights/persona.py`：
```python
"""AI 观看人格画像：聚合观看数据交给 LLM 生成人格描绘。"""
from __future__ import annotations

import sqlite3

from app.analyze import (category_distribution, fav_tnames, popularity,
                         time_buckets, up_depth, watch_completion, watch_profile)
from app.llm.base import LLMClient


def _summary(conn: sqlite3.Connection) -> str:
    p = watch_profile(conn)
    ups = [f"{u['up_name']}({u['views']})" for u in up_depth(conn, 5)] or ["无"]
    tns = [f"{t['tname']}({t['n']})" for t in fav_tnames(conn, 5)] or ["无"]
    cat = category_distribution(conn)["distribution"]
    cat_str = "、".join(f"{c['category']}({c['n']})" for c in cat[:5]) or "无"
    tb = time_buckets(conn)
    peak_bucket = max(tb, key=lambda x: x["n"])["bucket"] if tb else "未知"
    comp = watch_completion(conn)
    comp_str = "、".join(f"{c['bucket']}({c['n']})" for c in comp[:4]) or "无"
    pop = popularity(conn)
    pop_str = "、".join(f"{x['bucket']}({x['n']})" for x in pop[:4]) or "无"
    return (
        f"总观看 {p['total_views']} 个，累计时长 {p['total_duration_h']} 小时，"
        f"活跃 {p['active_days']} 天，日均 {p['avg_daily']} 个，"
        f"黄金时段在{p['peak_hour']}，最活跃{p['peak_weekday']}。"
        f"常看UP主：{'、'.join(ups)}。常看分区：{'、'.join(tns)}。"
        f"用途分布：{cat_str}。观看时段主力：{peak_bucket}。"
        f"完整度：{comp_str}。热门分布：{pop_str}。"
    )


def generate_persona(conn: sqlite3.Connection, llm_client: LLMClient) -> dict:
    summary = _summary(conn)
    prompt = (
        "你是数据洞察助手。以下是某位 B 站用户的观看数据摘要：\n"
        f"{summary}\n"
        "请描绘他的「B站观看人格画像」（130-180字），要求：\n"
        "1. 不要罗列具体数字，从整体抽象概括他的观看风格与节奏（如深夜党/碎片党/深度沉浸/广泛涉猎等）\n"
        "2. 点出他关注内容的偏向（学习成长型/娱乐放松型/资讯型）和观看习惯特征\n"
        "3. 用有画面感但不夸张的语言，像在和朋友聊天\n"
        "4. 结尾给一句简短的鼓励或建议\n"
        "用连贯段落，不要列表、不要重复数据。"
    )
    text = llm_client.chat([{"role": "user", "content": prompt}]).text.strip()
    return {"persona": text, "summary": summary}
```

> 注：`up_depth` 返回的 dict 含 `views` 键；`fav_tnames` 返回 `tname/n`；`category_distribution` 返回 `distribution` 列表（含 `category/n`）。空库时各聚合返回空列表，`_summary` 用「无」兜底。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_persona.py -v`
Expected: 2 passed

- [ ] **Step 5: 提交**

```bash
git add app/insights/persona.py tests/test_persona.py
git commit -m "feat: AI 观看画像生成"
```

---

### Task 2: API 路由

**Files:**
- Modify: `app/api.py`
- Modify: `tests/test_persona.py`（追加 API 测试）

**Interfaces:**
- Consumes: `generate_persona`（Task 1）
- Produces: `POST /api/insights/persona` → `{"persona", "summary"}`；未配置 LLM → 400

- [ ] **Step 1: 追加失败的测试**

`tests/test_persona.py` 追加（复用顶部已有的 `client = TestClient(app)` 需要——测试文件开头需 import）：
```python
from fastapi.testclient import TestClient

from app import config
from app.main import app

client = TestClient(app)


def test_persona_requires_llm(tmp_path):
    config.set_config_path(tmp_path / "config.json")  # 默认无 llm 配置
    assert client.post("/api/insights/persona").status_code == 400


def test_persona_generates(monkeypatch, tmp_path):
    config.set_config_path(tmp_path / "config.json")
    config.save_config({**config.load_config(),
                        "llm": {"provider": "openai", "api_key": "k", "base_url": "", "model": ""}})
    import app.api as api_mod
    monkeypatch.setattr(api_mod, "generate_persona",
                        lambda conn, llm_client: {"persona": "画像", "summary": "s"})
    r = client.post("/api/insights/persona")
    assert r.status_code == 200
    assert r.json() == {"persona": "画像", "summary": "s"}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_persona.py -v`
Expected: 后两个 API 测试 FAIL（404 / 无路由）

- [ ] **Step 3: 写实现**

`app/api.py` 追加 import（`from app.insights.time_invest import time_invest` 之后）：
```python
from app.insights.persona import generate_persona
```
在 `/insights/invest` 路由之后追加：
```python
@router.post("/insights/persona")
def insights_persona() -> dict:
    llm_cfg = load_config().get("llm") or {}
    if not llm_cfg.get("provider"):
        raise HTTPException(status_code=400, detail="未配置 LLM，请先在设置中选择")
    conn = get_conn()
    init_db(conn)
    try:
        return generate_persona(conn, get_llm_client(llm_cfg))
    finally:
        conn.close()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_persona.py -v`
Expected: 4 passed

- [ ] **Step 5: 提交**

```bash
git add app/api.py tests/test_persona.py
git commit -m "feat: AI 观看画像 API"
```

---

### Task 3: 前端卡片 + 验证 + 推送

**Files:**
- Modify: `web/js/app.js`

**Interfaces:**
- Consumes: `POST /api/insights/persona`

- [ ] **Step 1: Insights 组件顶部加卡片**

`app.js` 的 `Insights` 组件 template 里 `<h2>洞察</h2>` 之后加：
```html
    <el-card style="margin-bottom:16px">
      <template #header>AI 观看画像</template>
      <el-button type="primary" @click="genPersona" :loading="personaLoading">生成我的观看画像</el-button>
      <div v-if="persona" class="weekly-report" style="margin-top:12px">{{ persona }}</div>
      <div v-else style="color:#999;font-size:12px;margin-top:8px">
        用 AI 根据你的全部观看数据，描绘你的 B 站观看人格（深夜党 / 碎片党 / 深度爱好者…）。需先在设置页配置 LLM。
      </div>
    </el-card>
```

`setup()` 里加状态与函数，并在 `return` 中暴露：
```javascript
    const persona = ref('');
    const personaLoading = ref(false);
    async function genPersona() {
      personaLoading.value = true;
      try {
        const r = await api('/insights/persona', { method: 'POST' });
        persona.value = r.persona;
      } catch (e) { ElementPlus.ElMessage.error(e.message); }
      finally { personaLoading.value = false; }
    }
```
`return { interest, crossDim, loadCross, persona, personaLoading, genPersona };`

- [ ] **Step 2: 验证**

Run: `node --check web/js/app.js`
Run: `python -m pytest tests/ -v` → 全部通过
Run: 启动 `python -m uvicorn app.main:app --port 8002`，`curl -X POST http://localhost:8002/api/insights/persona` → 200（本机已配置 LLM）或 400（未配置则改 curl 预期）；确认页面在浏览器可生成画像。

- [ ] **Step 3: 提交 + 推送**

```bash
git add web/js/app.js
git commit -m "feat: AI 观看画像前端卡片"
git push origin main
```

---

## 收尾

汇总交付结果。
