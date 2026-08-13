# 行为洞察（里程碑 1）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增「洞察」页，提供三个纯本地数据聚合的分析维度：兴趣漂移（标签×月份）、时段×内容交叉、时间投资榜（实际观看时长）。

**Architecture:** 新建 `app/insights/` 包，每功能一个独立模块（interest / cross_time / time_invest），`app/api.py` 只加薄路由，前端新增 `Insights` 组件 + 菜单项。全部用现有表（history / videos / video_analysis）聚合，不新增采集、不新增依赖、不加表。

**Tech Stack:** FastAPI + SQLite + Python stdlib（json/time/datetime/collections.Counter）+ ECharts（前端）。

**设计文档：** `docs/superpowers/specs/2026-08-13-behavior-insights-design.md`

## Global Constraints

- Python ≥ 3.10；测试全部离线（本地 SQLite 造数据），不得真实请求 B 站 / LLM
- 不新增数据库表 / 字段；不新增 Python 依赖
- 每个模块独立文件 + 独立测试文件（用户强调模块化，出问题好修）
- 每个 Task 提交一次 git；全部完成后推送 GitHub
- 时间聚合统一用本地时区（`strftime(..., 'localtime')` / `datetime.fromtimestamp`）

---

### Task 1: `app/insights` 包 + 兴趣漂移 `interest.py`

**Files:**
- Create: `app/insights/__init__.py`
- Create: `app/insights/interest.py`
- Test: `tests/test_insights_interest.py`

**Interfaces:**
- Produces:
  - `app.insights.interest.interest_drift(conn, months=12, top_n=10) -> {"months": list[str], "series": [{"tag": str, "data": [int]}]}`
  - `app.insights.__init__` 导出 `interest_drift`

- [ ] **Step 1: 写失败的测试**

`tests/test_insights_interest.py`：
```python
from __future__ import annotations

import time

from app import database
from app.insights.interest import interest_drift


def _seed(conn):
    conn.execute("INSERT INTO videos (bvid, title) VALUES ('BV1', 'A')")
    conn.execute("INSERT INTO videos (bvid, title) VALUES ('BV2', 'B')")


def test_interest_drift_basic(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    now = int(time.time())
    _seed(conn)
    conn.execute("INSERT INTO history (bvid, view_at, progress) VALUES ('BV1', ?, 100)", (now,))
    conn.execute("INSERT INTO history (bvid, view_at, progress) VALUES ('BV2', ?, 100)", (now - 40 * 86400,))
    conn.execute("INSERT INTO video_analysis (bvid, tags_json, summary) VALUES ('BV1', '[\"科技\",\"AI\"]', 's')")
    conn.execute("INSERT INTO video_analysis (bvid, tags_json, summary) VALUES ('BV2', '[\"游戏\"]', 's')")
    conn.commit()
    conn.close()

    result = interest_drift(database.get_conn(), months=3)
    this_m = time.strftime("%Y-%m", time.localtime(now))
    last_m = time.strftime("%Y-%m", time.localtime(now - 40 * 86400))
    by_tag = {s["tag"]: dict(zip(result["months"], s["data"])) for s in result["series"]}
    assert by_tag["科技"][this_m] == 1
    assert by_tag["AI"][this_m] == 1
    assert by_tag["游戏"][last_m] == 1


def test_interest_drift_topn_and_other(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    now = int(time.time())
    _seed(conn)
    conn.execute("INSERT INTO history (bvid, view_at, progress) VALUES ('BV1', ?, 100)", (now,))
    conn.execute("INSERT INTO video_analysis (bvid, tags_json, summary) VALUES ('BV1', '[\"A\",\"B\",\"C\"]', 's')")
    conn.commit()
    conn.close()

    result = interest_drift(database.get_conn(), months=3, top_n=2)
    tags = [s["tag"] for s in result["series"]]
    assert "其他" in tags
    assert len(tags) == 3  # TOP2 + 其他
    this_m = time.strftime("%Y-%m", time.localtime(now))
    by_tag = {s["tag"]: dict(zip(result["months"], s["data"])) for s in result["series"]}
    assert by_tag["其他"][this_m] == 1


def test_interest_drift_empty(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    result = interest_drift(database.get_conn(), months=3)
    assert result["series"] == []
    assert len(result["months"]) == 3
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_insights_interest.py -v`
Expected: FAIL（`ModuleNotFoundError: app.insights`）

- [ ] **Step 3: 写实现**

`app/insights/__init__.py`：
```python
"""行为洞察后端包：每个分析维度一个独立模块。"""
from app.insights.interest import interest_drift

__all__ = ["interest_drift"]
```

`app/insights/interest.py`：
```python
"""兴趣漂移分析：LLM 主题标签 × 观看月份，看兴趣随时间迁移。"""
from __future__ import annotations

import json
import sqlite3
import time
from collections import Counter
from datetime import datetime


def _month_series(months: int) -> list[str]:
    """从 months 个月前到本月的月份列表，如 ['2026-06', '2026-07', '2026-08']。"""
    today = datetime.now()
    y, m = today.year, today.month - (months - 1)
    while m <= 0:
        y -= 1
        m += 12
    out = []
    for _ in range(months):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def interest_drift(conn: sqlite3.Connection, months: int = 12,
                   top_n: int = 10) -> dict:
    """近 N 个月每个主题标签的观看数。series 为 TOP 标签 + 一个「其他」。"""
    months_list = _month_series(months)
    start = int(datetime(int(months_list[0][:4]), int(months_list[0][5:7]), 1).timestamp())
    rows = conn.execute(
        """SELECT va.bvid, va.tags_json, MIN(h.view_at) AS t
           FROM video_analysis va JOIN history h ON va.bvid = h.bvid
           WHERE h.view_at >= ?
           GROUP BY va.bvid""",
        (start,),
    ).fetchall()
    monthly: dict[str, Counter] = {m: Counter() for m in months_list}
    all_tags: Counter = Counter()
    for r in rows:
        try:
            tags = json.loads(r["tags_json"] or "[]")
        except json.JSONDecodeError:
            continue
        mo = time.strftime("%Y-%m", time.localtime(r["t"]))
        if mo not in monthly:
            continue
        for t in tags:
            monthly[mo][t] += 1
            all_tags[t] += 1
    if not all_tags:
        return {"months": months_list, "series": []}
    top = [t for t, _ in all_tags.most_common(top_n)]
    series: dict[str, list[int]] = {t: [0] * len(months_list) for t in top}
    series["其他"] = [0] * len(months_list)
    for i, mo in enumerate(months_list):
        for t, n in monthly[mo].items():
            if t in series:
                series[t][i] += n
            else:
                series["其他"][i] += n
    return {
        "months": months_list,
        "series": [{"tag": k, "data": v} for k, v in series.items()],
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_insights_interest.py -v`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add app/insights tests/test_insights_interest.py
git commit -m "feat: 洞察-兴趣漂移分析"
```

---

### Task 2: 时段×内容交叉 `cross_time.py`

**Files:**
- Modify: `app/insights/__init__.py`
- Create: `app/insights/cross_time.py`
- Test: `tests/test_insights_cross.py`

**Interfaces:**
- Consumes: 无（独立）
- Produces:
  - `app.insights.cross_time.time_content_cross(conn, dim="tname", top_n=10) -> {"buckets": [str], "categories": [str], "matrix": [[int]]}`
    - `dim="tname"`（分区，JOIN videos）或 `dim="category"`（用途，LEFT JOIN video_analysis）
    - `matrix[i][j]` = 时段桶 i（凌晨/上午/下午/晚上）× 分类 j 的观看数

- [ ] **Step 1: 写失败的测试**

`tests/test_insights_cross.py`：
```python
from __future__ import annotations

import datetime

from app import database
from app.insights.cross_time import time_content_cross


def _at(hour: int) -> int:
    """今天该时刻的时间戳（保证跨测试可用任意整点）。"""
    now = datetime.datetime.now()
    return int(now.replace(hour=hour, minute=0, second=0, microsecond=0).timestamp())


def _seed_cross(conn, rows):
    for bvid, tname, hour in rows:
        conn.execute("INSERT INTO videos (bvid, title, tname) VALUES (?, 'T', ?)", (bvid, tname))
        conn.execute("INSERT INTO history (bvid, view_at, progress) VALUES (?, ?, 100)", (bvid, _at(hour)))


def test_cross_by_tname(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    _seed_cross(conn, [
        ("BV1", "科技", 3), ("BV2", "科技", 3), ("BV3", "游戏", 3),  # 凌晨：科技2 游戏1
        ("BV4", "科技", 20),                                          # 晚上：科技1
    ])
    conn.commit()
    conn.close()

    result = time_content_cross(database.get_conn(), dim="tname")
    li, ni = result["buckets"].index("凌晨(0-6)"), result["buckets"].index("晚上(18-24)")
    ci, gi = result["categories"].index("科技"), result["categories"].index("游戏")
    assert result["matrix"][li][ci] == 2
    assert result["matrix"][li][gi] == 1
    assert result["matrix"][ni][ci] == 1
    assert result["matrix"][ni][gi] == 0


def test_cross_by_category(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    _seed_cross(conn, [("BV1", "科技", 3), ("BV2", "游戏", 20)])
    conn.execute("INSERT INTO video_analysis (bvid, tags_json, summary, category) VALUES ('BV1', '[]', 's', '学习提升')")
    conn.execute("INSERT INTO video_analysis (bvid, tags_json, summary, category) VALUES ('BV2', '[]', 's', '娱乐消遣')")
    conn.commit()
    conn.close()

    result = time_content_cross(database.get_conn(), dim="category")
    assert "学习提升" in result["categories"]
    li = result["buckets"].index("凌晨(0-6)")
    assert result["matrix"][li][result["categories"].index("学习提升")] == 1


def test_cross_empty(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    result = time_content_cross(database.get_conn(), dim="tname")
    assert result["categories"] == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_insights_cross.py -v`
Expected: FAIL（`ModuleNotFoundError: app.insights.cross_time`）

- [ ] **Step 3: 写实现**

`app/insights/__init__.py` 追加一行：
```python
from app.insights.cross_time import time_content_cross
```
（`__all__` 也追加 `"time_content_cross"`）

`app/insights/cross_time.py`：
```python
"""时段 × 内容交叉：什么时间在看什么内容。"""
from __future__ import annotations

import sqlite3

TIME_BUCKETS = ["凌晨(0-6)", "上午(6-12)", "下午(12-18)", "晚上(18-24)"]


def _bucket(hour: int) -> str:
    if 0 <= hour < 6:
        return TIME_BUCKETS[0]
    if 6 <= hour < 12:
        return TIME_BUCKETS[1]
    if 12 <= hour < 18:
        return TIME_BUCKETS[2]
    return TIME_BUCKETS[3]


def time_content_cross(conn: sqlite3.Connection, dim: str = "tname",
                       top_n: int = 10) -> dict:
    """时段 × 分区/用途 观看数矩阵。dim='tname' 或 'category'。"""
    if dim == "category":
        dim_expr = "COALESCE(va.category, '其他')"
        join_clause = "LEFT JOIN video_analysis va ON h.bvid = va.bvid"
    else:
        dim_expr = "COALESCE(NULLIF(v.tname, ''), '其他')"
        join_clause = "JOIN videos v ON h.bvid = v.bvid"
    rows = [dict(r) for r in conn.execute(
        f"""SELECT {dim_expr} AS dim,
                   CAST(strftime('%H', h.view_at, 'unixepoch', 'localtime') AS INTEGER) AS hour,
                   COUNT(*) AS n
            FROM history h {join_clause}
            GROUP BY dim, hour"""
    ).fetchall()]
    totals: dict[str, int] = {}
    for r in rows:
        totals[r["dim"]] = totals.get(r["dim"], 0) + r["n"]
    categories = sorted(totals, key=lambda d: totals[d], reverse=True)[:top_n]
    buckets = list(TIME_BUCKETS)
    matrix = [[0] * len(categories) for _ in buckets]
    for r in rows:
        if r["dim"] not in categories:
            continue
        ci = categories.index(r["dim"])
        bi = buckets.index(_bucket(r["hour"]))
        matrix[bi][ci] += r["n"]
    return {"buckets": buckets, "categories": categories, "matrix": matrix}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_insights_cross.py -v`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add app/insights tests/test_insights_cross.py
git commit -m "feat: 洞察-时段×内容交叉"
```

---

### Task 3: 时间投资榜 `time_invest.py`

**Files:**
- Modify: `app/insights/__init__.py`
- Create: `app/insights/time_invest.py`
- Test: `tests/test_insights_invest.py`

**Interfaces:**
- Consumes: 无（独立）
- Produces:
  - `app.insights.time_invest.time_invest(conn) -> {"by_category": [{"name","seconds"}], "by_tag": [...], "by_up": [...]}`（各 TOP 15）
  - 实际观看时长 = `COALESCE(NULLIF(h.progress, 0), v.duration)`（progress 优先，0/空用全片长兜底）
  - 每个观看事件都计（重刷也算真实时间投入），三个维度一致

- [ ] **Step 1: 写失败的测试**

`tests/test_insights_invest.py`：
```python
from __future__ import annotations

import time

from app import database
from app.insights.time_invest import time_invest


def test_time_invest(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    now = int(time.time())
    conn.execute("INSERT INTO videos (bvid, title, up_name, tname, duration) VALUES ('BV1','A','UP甲','科技',3000)")
    conn.execute("INSERT INTO videos (bvid, title, up_name, tname, duration) VALUES ('BV2','B','UP甲','科技',1000)")
    conn.execute("INSERT INTO videos (bvid, title, up_name, tname, duration) VALUES ('BV3','C','UP乙','游戏',500)")
    conn.execute("INSERT INTO history (bvid, view_at, progress) VALUES ('BV1', ?, 3000)", (now,))
    conn.execute("INSERT INTO history (bvid, view_at, progress) VALUES ('BV2', ?, 0)", (now,))  # progress 0 → duration 兜底
    conn.execute("INSERT INTO history (bvid, view_at, progress) VALUES ('BV3', ?, 200)", (now,))
    conn.execute("INSERT INTO video_analysis (bvid, tags_json, summary, category) VALUES ('BV1','[\"AI\"]','s','学习提升')")
    conn.commit()
    conn.close()

    result = time_invest(database.get_conn())
    by_up = {r["name"]: r["seconds"] for r in result["by_up"]}
    assert by_up["UP甲"] == 4000      # BV1 progress 3000 + BV2 duration 兜底 1000
    assert by_up["UP乙"] == 200
    by_cat = {r["name"]: r["seconds"] for r in result["by_category"]}
    assert by_cat["学习提升"] == 3000
    assert by_cat["其他"] == 1200     # BV2(1000) + BV3(200) 无 category
    by_tag = {r["name"]: r["seconds"] for r in result["by_tag"]}
    assert by_tag["AI"] == 3000
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_insights_invest.py -v`
Expected: FAIL（`ModuleNotFoundError: app.insights.time_invest`）

- [ ] **Step 3: 写实现**

`app/insights/__init__.py` 追加一行：
```python
from app.insights.time_invest import time_invest
```
（`__all__` 也追加 `"time_invest"`）

`app/insights/time_invest.py`：
```python
"""时间投资榜：按用途/主题/UP主 累计实际观看时长。"""
from __future__ import annotations

import json
import sqlite3


def time_invest(conn: sqlite3.Connection, top_n: int = 15) -> dict:
    rows = conn.execute(
        """SELECT h.bvid, h.progress, v.duration, v.up_name, va.tags_json, va.category
           FROM history h
           JOIN videos v ON h.bvid = v.bvid
           LEFT JOIN video_analysis va ON h.bvid = va.bvid"""
    ).fetchall()
    by_category: dict[str, int] = {}
    by_up: dict[str, int] = {}
    by_tag: dict[str, int] = {}
    for r in rows:
        secs = r["progress"] or r["duration"] or 0
        if secs <= 0:
            continue
        cat = r["category"] or "其他"
        by_category[cat] = by_category.get(cat, 0) + secs
        up = r["up_name"] or "未知UP"
        by_up[up] = by_up.get(up, 0) + secs
        try:
            tags = json.loads(r["tags_json"] or "[]")
        except json.JSONDecodeError:
            tags = []
        for t in tags:
            by_tag[t] = by_tag.get(t, 0) + secs

    def top(d: dict[str, int]) -> list[dict]:
        return [{"name": k, "seconds": v} for k, v in
                sorted(d.items(), key=lambda x: -x[1])[:top_n]]

    return {"by_category": top(by_category), "by_tag": top(by_tag), "by_up": top(by_up)}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_insights_invest.py -v`
Expected: 1 passed

- [ ] **Step 5: 提交**

```bash
git add app/insights tests/test_insights_invest.py
git commit -m "feat: 洞察-时间投资榜"
```

---

### Task 4: API 路由

**Files:**
- Modify: `app/api.py`
- Test: `tests/test_insights_api.py`

**Interfaces:**
- Consumes: `interest_drift` / `time_content_cross` / `time_invest`（Task 1-3）
- Produces:
  - `GET /api/insights/interest?months=12` → interest_drift 返回值
  - `GET /api/insights/cross?dim=tname|category` → time_content_cross 返回值（非法 dim 400）
  - `GET /api/insights/invest` → time_invest 返回值

- [ ] **Step 1: 写失败的测试**

`tests/test_insights_api.py`：
```python
from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app import database
from app.main import app

client = TestClient(app)


def _seed(conn):
    conn.execute("INSERT INTO videos (bvid, title, tname) VALUES ('BV1', 'A', '科技')")
    conn.execute("INSERT INTO history (bvid, view_at, progress) VALUES ('BV1', ?, 100)", (int(time.time()),))
    conn.execute("INSERT INTO video_analysis (bvid, tags_json, summary, category) VALUES ('BV1', '[\"科技\"]', 's', '学习提升')")


def test_insights_endpoints(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    _seed(conn)
    conn.commit()
    conn.close()

    assert client.get("/api/insights/invest").status_code == 200
    assert client.get("/api/insights/interest").status_code == 200
    body = client.get("/api/insights/cross").json()
    assert "matrix" in body and body["categories"] == ["科技"]
    # 非法 dim 报 400
    assert client.get("/api/insights/cross", params={"dim": "xxx"}).status_code == 400
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_insights_api.py -v`
Expected: FAIL（404，路由不存在）

- [ ] **Step 3: 写实现**

`app/api.py` 追加 import（在 `from app.llm import get_llm_client` 之后）：
```python
from app.insights.cross_time import time_content_cross
from app.insights.interest import interest_drift
from app.insights.time_invest import time_invest
```

在 `/analysis/status` 路由之后追加三个路由：
```python
@router.get("/insights/interest")
def insights_interest(months: int = Query(12, ge=1, le=36)) -> dict:
    conn = get_conn()
    init_db(conn)
    try:
        return interest_drift(conn, months=months)
    finally:
        conn.close()


@router.get("/insights/cross")
def insights_cross(dim: str = Query("tname")) -> dict:
    if dim not in ("tname", "category"):
        raise HTTPException(status_code=400, detail="dim 仅支持 tname / category")
    conn = get_conn()
    init_db(conn)
    try:
        return time_content_cross(conn, dim=dim)
    finally:
        conn.close()


@router.get("/insights/invest")
def insights_invest() -> dict:
    conn = get_conn()
    init_db(conn)
    try:
        return time_invest(conn)
    finally:
        conn.close()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_insights_api.py -v`
Expected: 1 passed

- [ ] **Step 5: 提交**

```bash
git add app/api.py tests/test_insights_api.py
git commit -m "feat: 洞察 API 路由"
```

---

### Task 5: 前端「洞察」页

**Files:**
- Modify: `web/js/app.js`
- Modify: `web/css/style.css`

**Interfaces:**
- Consumes: `/api/insights/interest`、`/api/insights/cross?dim=`、`/api/insights/invest`

- [ ] **Step 1: 新增 `Insights` 组件**

在 `app.js` 的 `const Analysis = {...}` 组件定义之后（`const Overview` 之前）插入：

```javascript
const Insights = {
  template: `
    <h2>洞察</h2>
    <el-card style="margin-bottom:16px">
      <template #header>兴趣漂移（近 12 个月主题标签）</template>
      <div v-if="!interest.series.length" class="empty-tip">还没有主题数据，请先到「内容分析」页点「分析未分析视频」</div>
      <div v-else data-interest class="chart"></div>
    </el-card>
    <el-card style="margin-bottom:16px">
      <template #header>
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span>时段 × 内容</span>
          <el-radio-group v-model="crossDim" size="small" @change="loadCross">
            <el-radio-button value="tname">分区</el-radio-button>
            <el-radio-button value="category">用途</el-radio-button>
          </el-radio-group>
        </div>
      </template>
      <div data-cross class="chart"></div>
    </el-card>
    <el-card>
      <template #header>时间投资榜（实际观看时长 TOP）</template>
      <el-row :gutter="12">
        <el-col :span="8"><el-card shadow="never"><div data-invest-cat class="chart"></div></el-card></el-col>
        <el-col :span="8"><el-card shadow="never"><div data-invest-tag class="chart"></div></el-card></el-col>
        <el-col :span="8"><el-card shadow="never"><div data-invest-up class="chart"></div></el-card></el-col>
      </el-row>
    </el-card>
  `,
  setup() {
    const interest = ref({ months: [], series: [] });
    const crossDim = ref('tname');
    function mk(sel, option) {
      const el = document.querySelector(sel);
      if (el) echarts.init(el, 'dark').setOption(option);
    }
    async function loadInterest() {
      interest.value = await api('/insights/interest?months=12').catch(() => ({ months: [], series: [] }));
      nextTick(() => {
        mk('[data-interest]', {
          title: { text: '兴趣漂移', textStyle: { fontSize: 14 } },
          tooltip: { trigger: 'axis', confine: true },
          legend: { type: 'scroll', textStyle: { color: '#999', fontSize: 10 }, top: 0 },
          xAxis: { type: 'category', data: interest.value.months },
          yAxis: { type: 'value' },
          series: interest.value.series.map(s => ({ name: s.tag, type: 'line', stack: 'all', smooth: true, data: s.data })),
        });
      });
    }
    async function loadCross() {
      const d = await api(`/insights/cross?dim=${crossDim.value}`).catch(() => ({ buckets: [], categories: [], matrix: [] }));
      nextTick(() => {
        mk('[data-cross]', {
          title: { text: crossDim.value === 'tname' ? '时段 × 分区' : '时段 × 用途', textStyle: { fontSize: 14 } },
          tooltip: { position: 'top' },
          grid: { left: 90, right: 30, top: 40 },
          xAxis: { type: 'category', data: d.buckets, splitArea: { show: true } },
          yAxis: { type: 'category', data: d.categories, splitArea: { show: true } },
          visualMap: { min: 0, max: Math.max(1, ...d.matrix.flat()), inRange: { color: ['#2a2a2a', '#fb7299'] } },
          series: [{ type: 'heatmap',
                     data: d.buckets.flatMap((b, bi) => d.categories.map((c, ci) => [bi, ci, d.matrix[bi]?.[ci] || 0])) }],
        });
      });
    }
    async function loadInvest() {
      const d = await api('/insights/invest').catch(() => ({ by_category: [], by_tag: [], by_up: [] }));
      const barOpt = (title, list) => ({
        title: { text: title, textStyle: { fontSize: 13 } },
        tooltip: { trigger: 'axis', confine: true, formatter: p => `${p[0].name}<br/>${(p[0].value / 3600).toFixed(1)} 小时` },
        grid: { left: 90, right: 30, top: 30 },
        xAxis: { type: 'value' },
        yAxis: { type: 'category', data: list.slice(0, 10).map(x => x.name).reverse(), axisLabel: { fontSize: 10 } },
        series: [{ type: 'bar', data: list.slice(0, 10).map(x => x.seconds).reverse(),
                   itemStyle: { color: '#7ecbf2' }, barMaxWidth: 12 }],
      });
      nextTick(() => {
        mk('[data-invest-cat]', barOpt('按用途', d.by_category));
        mk('[data-invest-tag]', barOpt('按主题', d.by_tag));
        mk('[data-invest-up]', barOpt('按UP主', d.by_up));
      });
    }
    onMounted(() => { loadInterest(); loadCross(); loadInvest(); });
    return { interest, crossDim, loadCross };
  },
};
```

- [ ] **Step 2: 注册到 App + 菜单**

`app.js` App 组件：
1. `components: { Overview, ContentBrowser, Monitor, Analysis, Downloads, SearchResult, Chat, Settings }` → 加入 `Insights`
2. 菜单：`<el-menu-item index="analysis">...` 之后加：
   ```html
   <el-menu-item index="insights"><el-icon><TrendCharts/></el-icon>洞察</el-menu-item>
   ```
3. `el-main`：`<Analysis v-else-if="route === 'analysis'"/>` 之后加：
   ```html
   <Insights v-else-if="route === 'insights'"/>
   ```

- [ ] **Step 3: 启动服务人工验证**

Run: `python run.py`（或 `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`）
Expected: 侧边栏出现「洞察」；页面上兴趣漂移堆叠面积图、时段×内容热力图（分区/用途可切换）、时间投资三个条形图正常渲染；无内容分析数据时兴趣漂移显示空态提示。

- [ ] **Step 4: 提交**

```bash
git add web/js/app.js
git commit -m "feat: 洞察前端页面"
```

---

### Task 6: 集成测试 + README + 推送

**Files:**
- Modify: `tests/test_integration.py`
- Modify: `README.md`

- [ ] **Step 1: 追加集成测试**

`tests/test_integration.py` 追加：
```python
def test_insights_chain(tmp_path):
    database.set_db_path(tmp_path / "t.db")
    database.init_db()
    conn = database.get_conn()
    conn.execute("INSERT INTO videos (bvid, title, tname, duration) VALUES ('BV1', 'A', '科技', 100)")
    conn.execute("INSERT INTO history (bvid, view_at, progress) VALUES ('BV1', ?, 100)", (int(time.time()),))
    conn.execute("INSERT INTO video_analysis (bvid, tags_json, summary, category) VALUES ('BV1', '[\"科技\"]', 's', '学习提升')")
    conn.commit()
    conn.close()

    invest = client.get("/api/insights/invest").json()
    assert invest["by_category"][0]["name"] == "学习提升"
    assert invest["by_up"][0]["seconds"] == 100
    cross = client.get("/api/insights/cross").json()
    assert cross["categories"] == ["科技"]
    interest = client.get("/api/insights/interest").json()
    assert any(s["tag"] == "科技" for s in interest["series"])
```

> 注：`test_integration.py` 顶部已有 `client = TestClient(app)`，直接复用；若该文件无 `from app import database`，需补 import。

- [ ] **Step 2: 运行全部测试**

Run: `python -m pytest tests/ -v`
Expected: 全部通过（既有 + 新增 insights 测试）

- [ ] **Step 3: 更新 README**

「📈 分析」部分追加一行：
```markdown
- 洞察页：兴趣漂移（主题随时间变化）、时段×内容交叉、时间投资榜（实际观看时长）
```

- [ ] **Step 4: 提交 + 推送**

```bash
git add tests/test_integration.py README.md
git commit -m "feat: 洞察集成测试与 README 更新"
git push origin main
```

---

## 收尾

M1 行为洞察完成后汇总交付结果。
