# BiliScope

> 读取并分析自己 B 站账号数据的本地工具。扫码登录 → 自动拉取观看历史、收藏、关注、动态、硬币 → SQLite 存储 → Web 仪表盘可视化 + AI 助手。

**隐私安全**：所有数据仅保存在本地，不上传任何内容。单文件 EXE，双击即用。

## ✨ 功能

### 📥 数据收集
- 扫码登录（Cookie 存本地 config.json）
- 观看历史 / 收藏夹 / 关注列表 / 我的动态 / 硬币明细 / 账号信息（硬币、等级、粉丝、追番追剧）
- 每个视频的播放量、弹幕数、简介

### 📈 分析
- 概览看板：核心 KPI、月度趋势、观看时段、常看 UP 主、完整度、热门小众、90 天热力图
- 深度洞察：吃灰收藏（收藏了没看）、UP 主深度榜、分区吃灰率
- AI 内容标签：让大模型理解你看了什么内容，主题分布
- **AI 周报**：一键生成本周观看评价（抽象有洞察）

### 🔔 监测
- 失效视频检测（可定向检测某个收藏夹或观看历史）
- UP 主新投稿提醒（WBI 签名接口）
- 定时任务 + Web 页内提醒 + 邮件通知

### 🤖 AI 助手
- 通用聊天，多模型接入（DeepSeek / Claude / Ollama）
- 工具调用：整理收藏夹（新建/移动/删除）、分析视频链接
- 批量下载视频（MP4）/ 音频（MP3/m4a），支持收藏夹勾选批量下载

## 🚀 快速开始

**发行版（推荐，无需 Python）**：
1. 从 [Releases](https://github.com/O-My-PCCCCCCCCCC/BiliScope/releases) 下载 `BiliScope.exe`
2. 双击运行，浏览器打开 http://localhost:8000
3. 设置页扫码登录 B 站 → 立即同步数据

> 数据（config.json、数据库、下载目录）自动生成在 exe 同目录。

**从源码运行**：
```bash
pip install -r requirements.txt
python run.py
```

## 🧠 AI 大模型接入（本地 + 云并存）

可插拔 LLM 层，设置页一键切换：

| 方案 | 说明 | 成本 |
|---|---|---|
| **Ollama 本地** | 设置页「按资源占比选择模型」自动检测硬件 → 后台安装 → 免费离线 | ¥0 |
| **OpenAI 兼容** | DeepSeek / 通义 / Kimi / 智谱 等，填 key + base_url + 模型名 | 按量，很便宜 |
| **Claude** | 官方 Anthropic SDK | 按量 |

```json
"llm": { "provider": "ollama | openai | anthropic", "api_key": "", "base_url": "", "model": "" }
```

- **省心** → DeepSeek：`base_url` = `https://api.deepseek.com/v1`，模型 `deepseek-chat`
- **免费离线** → Ollama：检测硬件自动推荐模型，后台拉取
- 两者可随时切换，互不影响

## 🛠️ 技术架构

- **后端**：Python + FastAPI + SQLite + APScheduler + httpx
- **前端**：Vue3 + Element Plus + ECharts（资源本地化，不依赖 CDN）
- **AI**：可插拔 LLM 层（anthropic / openai / ollama）+ 工具调用
- **下载**：yt-dlp（视频 MP4 / 音频提取）

```
app/
├── bilibili/   # B 站 API 客户端、扫码登录、采集器、WBI 签名
├── llm/        # 可插拔 LLM 层（Claude/OpenAI 兼容/Ollama）
├── sync.py     # 数据同步编排
├── chat.py     # AI 聊天 + 工具调用循环
├── downloader.py  # yt-dlp 批量下载
├── monitor.py  # 失效检测 / UP 主更新
├── report.py   # 周月报 / AI 周报
└── api.py      # REST 端点
web/            # Vue3 单页前端
```

## 💻 开发

```bash
python run.py                     # 本地启动
python -m pytest tests/ -v        # 测试（全部 mock，不请求 B 站）
python -m PyInstaller biliscope.spec --noconfirm   # 打包单文件 EXE → dist/
```

## 📌 路线图

- ✅ M1 核心：登录 + 采集 + 概览
- ✅ M2 监测：失效检测 + UP 主更新 + 定时 + 提醒
- ✅ M3 报告：周月报 + 邮件
- ✅ M4 内容分析：多 LLM + 硬件推荐
- ✅ M5 AI 助手：聊天 + 工具调用 + 收藏整理 + 批量下载
- ✅ M6 数据分析深度优化
- ✅ M7 收尾：EXE 发行 + 开发工作流 skill

## ☕ 支持 / 赞赏

如果 BiliScope 对你有帮助，欢迎请我喝杯咖啡：

![赞赏码](docs/psc.png)

## 📄 License

本项目仅供学习交流，请勿用于商业用途。B 站相关数据的使用请遵守 B 站用户协议与相关法律法规。
