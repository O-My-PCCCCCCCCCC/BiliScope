# BiliScope — AI 观看画像（里程碑 2a）设计

- 日期：2026-08-14
- 状态：设计已向用户简述，直接落盘推进（用户要求快速执行）
- 仓库：https://github.com/O-My-PCCCCCCCCCC/BiliScope

## 1. 背景与目标

里程碑 1「行为洞察」已完成（兴趣漂移/时段×内容/时间投资）。本里程碑新增一个 **AI 观看画像**：聚合用户的全部本地观看数据，让 LLM 生成一段有洞察力的「观看人格」描绘。**年度报告本轮不做**（用户明确暂缓）。

**设计原则（沿用）：**
- **模块化**：独立模块 + 独立测试文件，出问题好修
- 复用现有 LLM 层与 `app.analyze` 聚合函数，不新增采集/依赖/表
- 离线可测（mock LLM），不真实请求

## 2. 功能定义

- 洞察页顶部新增「AI 观看画像」卡片 + 「生成我的观看画像」按钮
- 点击后聚合观看数据 → 组装摘要 → LLM 生成 130-180 字中文人格画像 → 展示在卡片
- 无 LLM 配置时后端返回 400，前端提示去设置页配置
- 生成结果**不落库**（每次生成返回即可，类似 weekly-ai 但更轻量）

## 3. 后端设计

**接口：** `POST /api/insights/persona` → `{"persona": str, "summary": str}`

**新模块：** `app/insights/persona.py`

```python
def generate_persona(conn, llm_client) -> dict:
    # 1. 聚合：复用 app.analyze 的 watch_profile / category_distribution /
    #    up_depth / fav_tnames / time_buckets / watch_completion / popularity
    # 2. 组装 summary 字符串（含总量、时长、活跃、黄金时段、常看UP主TOP5、
    #    分区TOP5、用途占比、完整度、热门小众占比）
    # 3. prompt：要求描绘"观看人格画像"，不罗列数字，抽象概括风格/节奏/专注方向
    # 4. text = llm_client.chat([...]).text.strip()
    # 5. 返回 {"persona": text, "summary": summary}
```

**API 路由（`app/api.py` 加薄路由）：**
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

> 与 insights 其他端点一致**不要求登录**（纯本地数据 + 本地配置的 LLM）。

## 4. 前端

`web/js/app.js` 的 `Insights` 组件顶部加卡片：

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

`.weekly-report` CSS 类已存在（多行文本、pre-wrap），直接复用。

## 5. 测试

`tests/test_persona.py`：
- `generate_persona` 用 FakeLLM（`chat` 返回固定 `.text`）验证：
  - 返回结构 `{persona, summary}`
  - summary 包含聚合到的关键数据（总观看数、常看 UP 主名）
  - 空库不崩溃（返回空摘要，persona 仍生成）
- API 测试：未配置 LLM → 400；配置后 + monkeypatch `generate_persona` → 200

## 6. 非目标

- 不做年度报告（用户暂缓）
- 不落库画像结果
- 不做「画像分享卡片」
