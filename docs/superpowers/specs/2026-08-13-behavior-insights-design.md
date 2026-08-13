# BiliScope — 行为洞察（里程碑 1）设计

- 日期：2026-08-13
- 状态：已确认（用户「干活吧」确认）
- 仓库：https://github.com/O-My-PCCCCCCCCCC/BiliScope

## 1. 背景与目标

用户目标是**分析自己的账号数据**。既有分析（概览 KPI、月度趋势、时段、常看 UP 主、完整度、热门小众、吃灰收藏、LLM 内容标签/用途分类）已覆盖「是什么」，本里程碑补「为什么 / 怎么变的」三个洞察维度：

1. **兴趣漂移**：我的兴趣主题随时间怎么变（哪个月开始迷上某领域、热度何时消退）
2. **时段×内容交叉**：什么时间在看什么内容
3. **时间投资**：时间真正花在哪（按用途 / 主题 / UP 主累计实际观看时长）

**设计原则（用户强调）：**
- **模块化**：每个功能独立模块 + 独立测试文件，出问题好定位好修
- 全部用**现有本地数据**聚合，不新增采集、不新增依赖
- 离线可测（mock），不真实请求 B 站 / LLM

## 2. 里程碑划分

- **里程碑 1「行为洞察」（本 spec）**：兴趣漂移 + 时段×内容 + 时间投资 → 新增「洞察」页
- **里程碑 2「报告」**（后续 spec）：年度报告 + AI 观看人格画像

## 3. 整体架构

```
app/insights/                 # 行为洞察后端包
├── __init__.py               # 汇总导出
├── interest.py               # ① 兴趣漂移
├── cross_time.py             # ② 时段×内容交叉
└── time_invest.py            # ③ 时间投资榜
```

- `app/api.py` 只加**薄路由**转发到 `app.insights`，不在 api.py 堆聚合逻辑
- 前端：新增「洞察」菜单项 + `Insights` 组件（三个图表区），风格沿用现有 ECharts dark
- 测试：`tests/test_insights_interest.py` / `tests/test_insights_cross.py` / `tests/test_insights_invest.py`

## 4. ① 兴趣漂移 `interest.py`

**接口：** `GET /api/insights/interest?months=12`

**逻辑：**
- 数据：`video_analysis.tags_json`（LLM 标签）JOIN `history.view_at`（同一 bvid 多次观看取最早一条）
- 聚合：Python 里展开 `tags_json`，按（标签 × 月份）计数
- 取出现次数 TOP 10 标签，其余归「其他」（`_top_tags` 辅助函数）
- 月份范围：近 N 个月（默认 12）

**返回：**
```json
{
  "months": ["2026-01", "2026-02", ...],
  "series": [{"tag": "AI", "data": [3, 5, ...]}, ...]
}
```

**边界：** 依赖 `video_analysis` 数据；无分析数据时返回空列表，前端提示「先去做内容分析」。

**SQL 要点：** 用 `SELECT va.bvid, va.tags_json, MIN(h.view_at) AS t FROM video_analysis va JOIN history h ON va.bvid = h.bvid GROUP BY va.bvid` 拿每个已分析视频的观看时间，Python 展开标签聚合。

## 5. ② 时段×内容交叉 `cross_time.py`

**接口：** `GET /api/insights/cross?dim=category|tname`

**逻辑：**
- 数据：`history` JOIN `videos`（tname）LEFT JOIN `video_analysis`（category）
- 时段桶（复用现有逻辑）：凌晨(0-6) / 上午(6-12) / 下午(12-18) / 晚上(18-24)
- 维度切换：`tname`（分区，全量视频可用）↔ `category`（用途分类，依赖 LLM）
- 行列：X = 时段桶（4），Y = TOP 分区/分类（默认前 10，其余忽略）

**返回：**
```json
{
  "buckets": ["凌晨(0-6)", ...],
  "categories": ["科技", "游戏", ...],
  "matrix": [[0, 3, ...], ...]   // [bucket][category] 计数
}
```

**SQL 要点：** 时段 CASE 与现有 `time_buckets` 一致；`GROUP BY hour_bucket, dim` 后用 Python 铺成矩阵。

## 6. ③ 时间投资榜 `time_invest.py`

**接口：** `GET /api/insights/invest`

**逻辑：** 实际观看时长 = `history.progress`（秒），无 progress 时用 `videos.duration` 兜底（`COALESCE(NULLIF(h.progress,0), v.duration)`）。三个维度 TOP 15：

- `by_category`：按 `video_analysis.category` 累计（含「其他」）
- `by_tag`：按 `video_analysis.tags_json` 展开累计
- `by_up`：按 `videos.up_name` 累计（每视频取最早观看，避免同视频多刷重复计全片长）

**返回：**
```json
{
  "by_category": [{"name": "学习提升", "seconds": 36000}],
  "by_tag": [{"name": "AI", "seconds": 25000}],
  "by_up": [{"name": "某UP", "seconds": 48000}]
}
```

**注意：** 与现有「UP主深度榜」（用 `SUM(duration)`）不同，时间投资用**实际观看 progress**，更真实。

## 7. 前端「洞察」页

`Insights` 组件，三个图表区（沿用 `pieOption`/`mk` 图表辅助模式）：

1. **兴趣漂移**：堆叠面积图（X=月份，Y=观看数，每标签一条线，TOP 10 + 其他）
2. **时段×内容**：热力图矩阵（X=时段，Y=分区/分类），顶部一个维度切换 radio（分区 / 用途）
3. **时间投资**：三个横向条形图（用途 / 主题 / UP 主），加表格显示小时数

空态：兴趣漂移 / 用途维度的图表在无 `video_analysis` 数据时显示提示文案，其余照常。

## 8. 错误 / 边界处理

- 各接口独立，单接口异常不影响其他；接口内部 catch 后返回空列表
- 空数据返回空列表，前端空态提示
- 无登录限制（本地数据聚合，无需 Cookie）——与现有 `/api/analysis/*` 一致

## 9. 测试策略

全部离线，mock SQLite 数据：

- `interest`: 造 video_analysis + history，验证标签展开、TOP10 截断、「其他」归并、月份排序
- `cross_time`: 造 history + videos，验证时段桶划分、矩阵行列、dim 切换
- `time_invest`: 造 history + videos + video_analysis，验证 progress 优先 / duration 兜底、三维度求和

## 10. 非目标（本里程碑不做）

- 不新增数据库表/字段（全部现表查询）
- 不做年度报告 / AI 人格画像（里程碑 2）
- 不做任何 B 站写操作 / 采集
