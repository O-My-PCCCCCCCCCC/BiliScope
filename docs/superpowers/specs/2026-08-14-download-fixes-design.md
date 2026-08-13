# BiliScope — 下载修复（里程碑 3）设计

- 日期：2026-08-14
- 状态：用户已确认优先修复下载（按推荐顺序第 1 项）
- 仓库：https://github.com/O-My-PCCCCCCCCCC/BiliScope

## 1. 背景与问题

用户反馈下载不可用：
1. **下载不了视频**——根因：系统无 ffmpeg。yt-dlp 下载视频用 `bv*+ba`（视频+音频分离流）合并成 mp4 **必须 ffmpeg**，没有就失败
2. **音频格式不明**——没有 ffmpeg 时音频只能下 m4a（代码里 `preferredcodec: "mp3"` 仅在 ffmpeg 存在时生效），用户不知道格式
3. **不知道存哪、不能选位置**——下载目录固定死在 `DATA_DIR/data/downloads`，不可配置，UI 不显示路径
4. **AI 助手说不清下载位置**——chat 下载工具只返回 `{ok: true}`，没有路径，AI 只能瞎编「环境默认目录」

## 2. 方案

### 2.1 ffmpeg 保障（新模块 `app/ffmpeg_setup.py`）
`ensure_ffmpeg() -> str | None` 按顺序定位：
1. 系统 PATH 里的 `ffmpeg`
2. 冻结打包目录 `sys._MEIPASS/ffmpeg.exe`
3. **`imageio_ffmpeg.get_ffmpeg_exe()`**（pip 依赖自带静态 ffmpeg，约 25MB，最可靠，无需手动下载安装包）
4. 都没有 → None

`app/downloader.py` 的 `_run` 在下载前调用，拿到路径就设 `opts["ffmpeg_location"]`，这样视频能合并成 mp4、音频能转 mp3。

新增依赖：`imageio-ffmpeg`（写进 requirements.txt）。

### 2.2 可配置下载目录
- `app/config.py` DEFAULT_CONFIG 加 `"download_dir": ""`（空 = 默认 `DATA_DIR/data/downloads`）
- `app/downloader.py` 把模块级 `OUT_DIR` 改为函数 `out_dir()`，每次从 config 读（用户改完立即生效）
- `app/api.py`：ConfigPayload 加 `download_dir`，config_get/save 透传
- 前端 Settings 加「下载」卡片（输入路径 + 保存），Downloads 页顶部显示当前保存路径

### 2.3 路径与格式透明
- `download_status()` 返回里带 `out_dir`
- Downloads 页顶部显示：保存路径 + 格式说明（视频 → mp4；音频 → mp3（有 ffmpeg）/ m4a（无 ffmpeg））

### 2.4 AI 下载工具返回真实路径
- `app/chat.py` 的 `download_videos` / `download_audio` 工具返回 `{...start_download(...), "out_dir": str(out_dir())}`，AI 就能准确告诉用户文件存哪

## 3. 测试策略

全部离线：
- `tests/test_ffmpeg_setup.py`：`ensure_ffmpeg` 各来源（monkeypatch `shutil.which`、`sys.frozen`、`imageio_ffmpeg` import）
- `tests/test_downloader.py`（追加）：`out_dir()` 读 config 的 download_dir；`_run` 设 `ffmpeg_location`（monkeypatch yt_dlp.YoutubeDL 记录 opts）
- `tests/test_config_api.py`（追加）：config 保存/读取 download_dir
- chat 工具返回 out_dir（mock start_download）

## 4. 非目标

- 不做多任务队列管理
- 不做浏览器端选择文件夹对话框（用户手动粘贴路径即可）
- 不做下载历史记录
