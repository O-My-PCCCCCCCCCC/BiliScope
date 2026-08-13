"""yt-dlp 批量下载管理器（视频 MP4 / 音频 MP3/m4a），后台任务 + 进度。"""
from __future__ import annotations

import re
import shutil
import threading
from pathlib import Path

from app.config import DATA_DIR, load_config
from app.ffmpeg_setup import ensure_ffmpeg

try:
    import yt_dlp
except Exception:  # 未安装时 _run 会报错，由状态提示
    yt_dlp = None

_download_status: dict = {"state": "idle", "tasks": [], "current": "",
                          "progress": 0, "message": ""}
_thread: threading.Thread | None = None


def out_dir() -> Path:
    """当前下载目录：config 的 download_dir（空则用默认 DATA_DIR/data/downloads）。"""
    custom = load_config().get("download_dir") or ""
    base = Path(custom) if custom else DATA_DIR / "data" / "downloads"
    base.mkdir(parents=True, exist_ok=True)
    return base


def download_status() -> dict:
    s = dict(_download_status)
    s["out_dir"] = str(out_dir())
    return s


def list_downloads() -> list[str]:
    d = out_dir()
    if not d.exists():
        return []
    return sorted(
        [p.name for p in d.iterdir() if p.is_file() and p.suffix in (".mp4", ".mp3", ".m4a", ".webm")],
        reverse=True,
    )


def _write_cookies() -> str:
    from app.config import get_cookies
    cookies = get_cookies()
    path = DATA_DIR / "data" / "cookies.txt"
    lines = ["# Netscape HTTP Cookie File"]
    for k, v in cookies.items():
        lines.append(f".bilibili.com\tTRUE\t/\tFALSE\t0\t{k}\t{v}")
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


_BV_RE = re.compile(r"(BV[0-9A-Za-z]{10})")


def normalize_urls(urls: list[str]) -> list[str]:
    """把裸 BV 号补全为完整链接，其余原样返回。"""
    out = []
    for u in urls:
        u = (u or "").strip()
        if not u:
            continue
        if not u.startswith(("http://", "https://")):
            m = _BV_RE.search(u)
            if m:
                out.append(f"https://www.bilibili.com/video/{m.group(1)}")
                continue
        out.append(u)
    return out


def start_download(urls: list[str], fmt: str = "mp4") -> dict:
    global _thread
    if _thread and _thread.is_alive():
        return {"error": "已有下载任务进行中"}
    urls = normalize_urls(urls)
    if not urls:
        return {"error": "没有要下载的链接"}
    _download_status.update({
        "state": "running",
        "tasks": [{"url": u, "fmt": fmt} for u in urls],
        "current": "", "progress": 0, "message": "准备开始...",
    })
    _thread = threading.Thread(target=_run, args=(list(urls), fmt), daemon=True)
    _thread.start()
    return {"ok": True, "out_dir": str(out_dir())}


def _hook(d: dict) -> None:
    if d.get("status") == "downloading":
        total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
        done = d.get("downloaded_bytes", 0)
        if total:
            _download_status["progress"] = min(int(done * 100 / total), 99)
        _download_status["message"] = f"下载中 {done // 1024 // 1024}MB / {total // 1024 // 1024}MB"
    elif d.get("status") == "finished":
        _download_status["message"] = "下载完成，转码中..."


def _run(urls: list[str], fmt: str) -> None:
    d = out_dir()
    d.mkdir(parents=True, exist_ok=True)
    try:
        cookies = _write_cookies()
        opts = {
            "outtmpl": f"{d}/%(title)s.%(ext)s",
            "quiet": True, "no_warnings": True, "noplaylist": False,
            "progress_hooks": [_hook], "cookiefile": cookies, "retries": 3,
        }
        ffmpeg = ensure_ffmpeg()
        if ffmpeg:
            opts["ffmpeg_location"] = ffmpeg
        if fmt == "audio":
            opts["format"] = "bestaudio/best"
            if ffmpeg:
                opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}]
            else:
                opts["postprocessors"] = []  # 无 ffmpeg 则直接下 m4a
        else:
            opts["format"] = "bv*+ba/b"
        with yt_dlp.YoutubeDL(opts) as ydl:
            for url in urls:
                _download_status["current"] = url
                ydl.download([url])
        _download_status.update({"state": "done", "progress": 100, "message": "全部下载完成"})
    except Exception as e:
        _download_status.update({"state": "error", "message": str(e)})
