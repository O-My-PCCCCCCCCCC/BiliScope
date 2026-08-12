---
name: biliscope-dev
description: Use when developing, debugging, or extending the BiliScope B站 personal-data dashboard project. Covers the milestone-based workflow, architecture map, B站 API gotchas, and run/test/build commands.
---

# BiliScope 开发工作流

BiliScope 是读取自己 B 站账号数据（观看历史/收藏/关注/动态/硬币）并做分析、监测、AI 助手、批量下载的本地工具（FastAPI + SQLite + Vue3 单页）。

## 工作流（新增功能时遵循）

1. **先想清楚再动手**：brainstorming → 写进 `docs/superpowers/specs/` → 用户确认
2. **写计划**：`docs/superpowers/plans/YYYY-MM-DD-<feature>.md`，任务级拆分
3. **TDD 执行**：每个任务「先写失败测试 → 跑红 → 写实现 → 跑绿 → commit」
4. **里程碑提交**：任务级 commit，每个里程碑完成推一次 GitHub
5. **不要**：跳过测试、commit 时测试还是红的、在 main 上未经确认直接大改

## 架构地图

| 模块 | 职责 |
|---|---|
| `app/bilibili/` | B 站 API 客户端（client.py）+ 扫码登录 + 各数据采集（history/favorite/relation/wbi）|
| `app/sync.py` | 同步编排：历史/收藏/关注/简介/合集/动态/账号信息 |
| `app/database.py` | SQLite 建表 + 迁移（`_migrate` 加列）|
| `app/llm/` | 可插拔 LLM 层：anthropic / openai（DeepSeek 等）/ ollama，工厂 `get_llm_client` |
| `app/chat.py` | AI 聊天 + 工具调用循环（收藏夹管理/分析/下载工具）|
| `app/favtools.py` | 收藏夹管理 + 视频分析工具（供 AI 调用）|
| `app/downloader.py` | yt-dlp 批量下载（后台线程 + 进度）|
| `app/ollama_manager.py` | 本地模型安装/拉取（后台 + 进度）|
| `app/api.py` | 全部 REST 端点 |
| `web/` | Vue3 + Element Plus + ECharts 单页（CDN 资源已本地化到 web/vendor/）|

## B 站 API 关键坑（踩过）

- **观看历史** `/x/v2/history`：`data` **直接是数组**（不是 `{"list":...}`），UP 主在 `owner.mid/name`（不是 author_mid），分页用 `pn`（不是 max_id 游标）
- **收藏夹列表** `/x/v3/fav/folder/created/list-all`：**必须带 `up_mid` 参数**，否则 -400
- **删除收藏夹** `/x/v3/fav/folder/del`：参数是 **`media_ids`**（复数），不是 media_id
- **写操作**：表单里带 `csrf=bili_jct`（不是请求头），`BiliClient.post_json` 已封装
- **UP 主投稿** `/x/space/wbi/arc/search`：需要 **WBI 签名**（`app/bilibili/wbi.py`）
- **图片防盗链**：B 站 CDN 只放行 bilibili Referer → 必须走后端 `/api/img` 代理（带 Referer + 磁盘缓存 + 缩略图后缀 `@320w_200h_1c.webp`）
- **数据变更**：接口可能改版，报错先 `curl` 实测真实返回结构再改

## 命令

```bash
python run.py                    # 启动（localhost:8000）
python -m pytest tests/ -v       # 测试（全 mock，不请求 B 站）
python -m PyInstaller biliscope.spec --noconfirm   # 打包单文件 EXE → dist/
```

## 打包 EXE 注意

- `app/config.py` 的 `APP_DIR`（web 资源，冻结时在 _MEIPASS）/ `DATA_DIR`（可写数据，冻结时在 exe 同目录）已做冻结模式重定向
- 新加静态资源要确认 `APP_DIR`，新写文件要确认 `DATA_DIR`
- 冻结时 `sys.frozen` 为真，`reload` 必须关

## 测试习惯

- 测试不得真实请求 B 站 / LLM：一律 mock（httpx.MockTransport / fake client / monkeypatch）
- 加表字段用 `database._migrate`（PRAGMA 检查后 ALTER）
- 改采集器时同时更新对应 `tests/` 里的 mock 数据结构
