# BiliScope — 设计文档

- 日期：2026-08-12
- 状态：已确认（待用户审阅）
- 仓库：https://github.com/O-My-PCCCCCCCCCC/BiliScope

## 1. 背景与目标

BiliScope 是一个**读取并分析自己 B 站账号数据**的本地工具。目标是把散落在 B 站内部的个人数据（观看历史、收藏、关注等）沉淀到本地数据库，提供 Web 仪表盘做可视化分析，并自动监测视频失效、UP 主更新，定期生成观看报告。

**核心用途（用户确认）：**
1. 数据分析/可视化 —— 常看 UP 主、观看时段规律、类型分布等
2. 自动监测/提醒 —— 视频失效检测、UP 主更新提醒、观看数据报告
3. 筛选/整理内容 —— 找出失效收藏并清理、按条件筛选历史

**设计原则：**
- 本地运行、数据本地可控，不上传任何数据
- 单机 Python 应用，避免过度设计（不用 Django/Celery）
- 一切 B 站数据通过**网页端同一套内部 API** 获取（扫码登录拿到 Cookie 后程序化调用）

## 2. 需求清单

| 类别 | 需求 |
|---|---|
| 数据 | 观看历史、收藏夹（含失效检测）、关注列表、点赞/投币（尽力而为） |
| 登录 | 主方案扫码登录，密码登录备选 |
| 形态 | 定时任务 + SQLite + Web 仪表盘 |
| 监测 | 视频失效、UP 主更新、观看周/月报 |
| 通知 | Web 页内提醒 + 邮件（SMTP） |
| 技术栈 | Python + FastAPI + SQLite + APScheduler + Vue3/Element Plus + ECharts |

## 3. 平台限制说明

- B 站**没有公开的「我赞过的视频」和「投币历史」列表接口**。点赞/投币记录只能做到「尽力而为」（能拿到多少存多少），页面上会明确标注此限制。
- 观看历史接口上限约 **2000 条**（分页拉取，`max_id` 游标翻页）。
- 关注列表接口上限约 5000 条。

## 4. 整体架构

```
BiliScope (Python 单机应用)
├── FastAPI Web 服务 (localhost:8000)
│   ├── 静态页面 (Vue3 + Element Plus + ECharts)
│   ├── REST API（数据查询 / 配置 / 手动触发同步）
│   └── APScheduler 定时任务（随 Web 服务启动注册）
├── 数据采集层：B 站 API 客户端（扫码登录 Cookie + 分页拉取）
├── 监测层：失效检测 / UP 主更新 / 报告生成
├── 通知层：邮件 SMTP + Web 内提醒
└── SQLite 数据库 (data/bili.db)
```

## 5. 项目目录结构

```
BiliScope/
├── app/
│   ├── main.py            # FastAPI 入口，托管静态页 + REST API + 注册调度器
│   ├── config.py          # 配置读写（Cookie、SMTP、任务间隔）
│   ├── database.py        # SQLite 连接与建表
│   ├── bilibili/
│   │   ├── client.py      # B 站 API 客户端：请求封装、节流、风控处理
│   │   ├── login.py       # 扫码登录 / 密码登录
│   │   ├── history.py     # 观看历史采集
│   │   ├── favorite.py    # 收藏夹采集
│   │   └── relation.py    # 关注列表 / UP 主投稿
│   ├── scheduler.py       # APScheduler 任务定义
│   ├── monitor.py         # 失效检测、UP 主更新检测
│   ├── report.py          # 周报/月报生成
│   ├── notify.py          # 邮件通知 + Web 提醒入库
│   ├── analyze.py         # 统计聚合逻辑（图表数据源）
│   └── llm/               # 可插拔 LLM 提供层（M4）
│       ├── base.py        # LLMClient 抽象接口 + VideoTags 输出模型
│       ├── anthropic_provider.py
│       ├── openai_provider.py   # OpenAI 兼容（DeepSeek 等）
│       └── ollama_provider.py   # 本地 Ollama
├── web/                   # 前端静态资源（Vue3 CDN 单页应用）
│   ├── index.html
│   ├── css/
│   └── js/
├── data/                  # SQLite 数据库文件（不入库）
├── tests/                 # pytest 离线测试
├── config.json            # 运行时配置（Cookie 等，不入库）
├── requirements.txt
├── run.py                 # 一键启动
└── README.md
```

## 6. 数据模型（SQLite）

| 表 | 字段（要点） | 说明 |
|---|---|---|
| `videos` | bvid(主键), title, up_mid, up_name, pic, duration, tname, ctime | 视频主信息缓存，去重 |
| `history` | id, bvid, view_at, progress, duration | 观看历史；view_at 时间戳 |
| `fav_folders` | media_id(主键), name, created_at, count | 收藏夹列表 |
| `fav_items` | id, media_id, bvid, fav_time | 收藏内容；失效时 bvid 保留但 videos 无对应行 |
| `coins` | id, bvid, coin_time | 投币记录（尽力而为） |
| `followings` | mid(主键), name, uname, face | 关注列表 |
| `updates` | mid(主键), last_bvid, last_pubdate, checked_at | UP 主最新投稿监测状态 |
| `invalid_items` | id, bvid, source(history/fav), checked_at | 失效视频记录 |
| `reports` | id, period, type(weekly/monthly), content_json, created_at | 生成的报告 |
| `alerts` | id, type, title, content, created_at, read | Web 页内提醒 |

## 7. 登录模块

- **主方案：扫码登录**
  - `GET /x/passport-login/web/qrcode/generate` 生成二维码
  - 前端「设置」页展示二维码，用户用 B 站 App 扫码
  - 轮询 `GET /x/passport-login/web/qrcode/poll` 直到确认登录
  - 成功后保存 Cookie（SESSDATA / bili_jct / buvid3 / DedeUserID）到 `config.json`
- **备选：密码登录**（`bilibili-api` 支持，可能触发验证码，仅作兜底）
- **过期处理**：接口返回登录失效时，仪表盘弹出提示引导重新扫码

## 8. 采集模块

所有接口为 B 站网页内部 API，统一走客户端封装（自动带 Cookie、请求节流、失败重试、登录失效检测）：

| 数据 | 接口 | 说明 |
|---|---|---|
| 观看历史 | `GET /x/v2/history` | `max_id` 分页，每页约 100，上限约 2000 条 |
| 收藏夹列表 | `GET /x/v3/fav/folder/created/list-all` | 一次性拉取 |
| 收藏内容 | `GET /x/v3/fav/resource/list` | 按 `media_id` 分页 |
| 关注列表 | `GET /x/relation/followings` | `pn` 分页 |
| 视频信息 | `GET /x/web-interface/view?bvid=` | 详情 + **失效检测**（返回 -404 或空即失效） |
| UP 主最新投稿 | `GET /x/space/wbi/arc/search` | 取每个 UP 主最新稿件 |

**增量策略**：历史记录按 `max_id` 游标记住已同步位置，每次只拉新增部分。

## 9. 定时任务（APScheduler）

| 任务 | 频率 | 内容 |
|---|---|---|
| 同步历史+收藏 | 每天 03:00 | 增量拉取观看历史、收藏夹 |
| 失效检测 | 每天 04:00 | 检查历史+收藏中视频是否失效，写 `invalid_items` + 提醒 |
| UP 主更新 | 每 6 小时 | 拉关注列表（或缓存）中 UP 主最新投稿，有更新写提醒 |
| 报告生成 | 每周日 05:00 / 每月 1 日 05:00 | 生成周/月报，入库 + 可选邮件 |

手动触发：仪表盘「设置」页提供「立即同步」按钮。

## 10. 监测与通知

- **失效监测**：逐个视频调 `view` 接口，节流（间隔+随机延迟），失效视频记录来源（历史/收藏）并生成提醒。
- **UP 主更新**：对比 `updates.last_bvid`，有新投稿生成提醒。
- **报告**：聚合观看数、常看 UP 主 TOP N、观看时段分布、类型分布、失效统计等，存 `reports` 表。
- **通知渠道**：
  - Web 内提醒：`alerts` 表，仪表盘角标显示未读
  - 邮件：SMTP（QQ/163 邮箱，授权码），发送失效清单/更新/报告摘要

## 11. Web 仪表盘（参考 AstrBot WebUI 风格）

左侧边栏 + 现代深色管理面板，单页应用（Vue3 + Element Plus + ECharts，全部 CDN 引入，无 Node 构建链）。

| 页面 | 内容 |
|---|---|
| 概览 | 统计卡片（历史/收藏/关注/失效数）+ 近 30 天观看趋势 + 常看 UP 主 TOP10 + 时段/类型分布 |
| 观看历史 | 表格 + 搜索筛选 + 按周/月聚合视图 |
| 收藏夹 | 文件夹列表 + 视频列表，失效视频标红 |
| 监测中心 | 失效清单、UP 主更新动态、历史报告 |
| 数据分析 | 深度图表页（可切换时间范围） |
| 设置 | 扫码登录入口、Cookie 状态、SMTP 配置、任务间隔、立即同步 |

## 12. 测试策略

- 核心逻辑（API 响应解析、数据库写入、失效判定、报告聚合）用 **pytest + 离线 mock 数据**测试，测试时不真实请求 B 站。
- B 站 API 客户端通过可注入的 http session 抽象，便于 mock。

## 13. 运行方式

```
pip install -r requirements.txt
python run.py
# 浏览器打开 http://localhost:8000
```

- Windows 下可选：提供 `.bat` 一键启动脚本。
- 常驻方式（开机自启/系统服务）不在第一版范围。

## 14. 非目标（第一版不做，YAGNI）

- 手机推送（Server酱 等，留扩展点）
- 多账号支持
- 视频下载
- 播放页爬虫 / 弹幕评论抓取
- 移动端适配（桌面优先）

## 15. 里程碑划分

- **M1（核心可用）**：项目骨架 + 登录 + 历史/收藏/关注采集 + SQLite + 概览页（基本图表）✅
- **M2（监测）**：失效检测 + UP 主更新 + 定时任务 + Web 提醒 ✅
- **M3（报告与配置）**：周/月报 + 邮件通知 + 设置页完整化 ✅
- **M4（内容分析）**：Claude API 分析视频内容，按主题标签分类并报告分布
- **M5（AI 助手与批量下载）**：通用 AI 聊天 + 工具调用 + 批量下载视频/音频
- **M6（打磨）**：数据分析页完善、测试补全、首版发布

## 17. AI 助手与批量下载（2026-08-12 新增，已确认）

用户需求：一个**通用 AI 聊天助手**，能理解自然语言命令并调用工具执行操作（如批量下载视频/音频）。

**组件：**
- `app/chat.py`：聊天会话管理 + 工具调用循环（多轮对话，工具结果回填模型继续生成）
- `app/downloader.py`：yt-dlp 封装（B 站视频 MP4 / 音频 MP3 提取），下载放后台线程，进度可查询
- 工具集：`list_history` / `list_favorites` / `list_folders` / `download_videos` / `download_status` / `generate_report`
- 前端「AI 助手」聊天页
- 复用 M4 的 LLM 提供层（anthropic / openai / ollama），扩展出 chat 与工具调用能力

**工具调用循环：**
1. 用户消息 → LLM → 若请求工具 → 后端执行 → 结果回填 → LLM 继续，直到结束
2. 批量下载等耗时操作走后台线程，`download_status` 查询进度

**API：**
- `POST /api/chat`（发消息 → 返回回复，含工具执行）
- `GET /api/chat/history`、`POST /api/chat/reset`
- `GET /api/downloads`（下载列表/状态）、下载目录可配置

**技术要点：**
- 新增依赖：`yt-dlp`
- 下载输出目录默认 `data/downloads`，config 可配
- B 站 bvid → URL `https://www.bilibili.com/video/{bvid}`，带 Cookie 下载
- **不做第三方音乐聚合站抓取**（版权原因，用户已确认替代为 B 站音频提取）

**版权说明：** 第三方「多站合一音乐下载站」多为侵权聚合源，不实现。B 站视频提取音频（`yt-dlp -x --audio-format mp3`）完全支持。

## 16. 内容分析（2026-08-12 新增，已确认）

用户新增需求：**不只统计分区，还要理解每个视频讲了什么内容，按内容主题归类，报告哪类占多数。**

**已确认方案：**
- 引擎：**可插拔 LLM 提供层**（`app/llm/`），统一接口，配置切换 provider：
  - **Anthropic Claude**：官方 `anthropic` SDK + 结构化输出（`messages.parse()` + Pydantic）
  - **OpenAI 兼容**（DeepSeek / 通义 / Kimi / 智谱 / 硅基流动…）：`openai` SDK + `base_url` 切换，`response_format=json_object`
  - **Ollama 本地**：`requests` 直连 `localhost:11434`，`format:"json"`，免费离线
- 输入：每个视频的 **标题 + 简介**
- 输出：每视频 3-5 个中文内容标签 + 一句话摘要

**数据流程：**
1. 补采简介：`/x/web-interface/view?bvid=` 返回 `desc`，写入 videos 表新增 `desc` 列（需迁移旧表）
2. 批量分析：对未分析视频（`video_analysis` 中无记录）调 Claude API，生成标签+摘要
3. 聚合：按标签统计主题分布
4. 展示：仪表盘新增「内容分析」页 + 融入周/月报

**新增表：**
```sql
CREATE TABLE IF NOT EXISTS video_analysis (
    bvid TEXT PRIMARY KEY,
    tags_json TEXT,
    summary TEXT,
    analyzed_at INTEGER,
    model TEXT
);
```
videos 表迁移：`ALTER TABLE videos ADD COLUMN desc TEXT`

**配置（config.json）：**
```json
"llm": {
  "provider": "anthropic | openai | ollama",
  "api_key": "",
  "base_url": "",
  "model": "claude-haiku-4-5 / deepseek-chat / llama3.2"
}
```
provider 与模型由用户在设置页选择；openai provider 的 base_url 填对应服务商地址（如 DeepSeek `https://api.deepseek.com/v1`）。

**技术要点：**
- `app/llm/base.py` 定义统一接口 `LLMClient.analyze_video(title, desc) -> VideoTags`（Pydantic 模型：tags + summary），各 provider 独立实现；`app/llm/__init__.py` 提供工厂函数按 config 选择
- 结构化输出保证标签稳定可解析：Anthropic 用 `messages.parse()` + Pydantic；OpenAI 兼容用 `response_format=json_object` + JSON 解析校验（兼容 DeepSeek 等不完整结构输出）；Ollama 用 `format:"json"`
- 新增依赖：`anthropic`、`openai`
- 已分析视频去重（`analyzed_at`），重跑不重复扣费
- 分析范围可配置（默认最近 N 条，避免一次性全量造成高额费用）
- Claude 默认 `claude-haiku-4-5`（此类短文本打标签足够、成本低），用户可按需切 `claude-opus-5`

### 本地模型自动推荐（2026-08-12 追加）

用户希望**根据本机硬件配置自动选择本地可跑动的 AI 模型**（Ollama 部署）。

- `app/hardware.py`：检测 CPU 核数、内存、GPU 及显存（NVIDIA 用 `nvidia-smi` / `pynvml`，其余尽力而为）
- 推荐算法：按「显存 → 内存 → CPU」优先级选 Ollama 模型
  - 无 GPU（纯 CPU 推理）：按内存选 `qwen2.5:0.5b / 1.5b / 3b / 7b`
  - 有 GPU：按显存选 `qwen2.5:1.5b(≤4G) / 7b(4-8G) / 14b(8-12G) / 32b(16G+)`
- 设置页「检测硬件并推荐」：展示硬件信息 + 推荐模型 → 一键 `ollama pull <model>` 拉取 → 设为默认 provider
- 依赖：`psutil`、`nvidia-ml-py`（可选，无 GPU 可不装）；前提用户本机装有 Ollama
