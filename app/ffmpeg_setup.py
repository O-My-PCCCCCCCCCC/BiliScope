"""ffmpeg 可用性保障：定位可用的 ffmpeg 可执行文件。"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

try:
    import imageio_ffmpeg
except Exception:  # 未安装时降级
    imageio_ffmpeg = None


def ensure_ffmpeg() -> str | None:
    """返回可用的 ffmpeg 路径；找不到返回 None。

    优先级：系统 PATH → 冻结打包目录 → imageio-ffmpeg 自带的静态 ffmpeg。
    """
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    if getattr(sys, "frozen", False):
        cand = Path(sys._MEIPASS) / "ffmpeg.exe"
        if cand.exists():
            return str(cand)
    if imageio_ffmpeg:
        return imageio_ffmpeg.get_ffmpeg_exe()
    return None
