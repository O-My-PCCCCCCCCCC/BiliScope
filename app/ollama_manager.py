"""Ollama 本地模型管理：检查安装、后台拉取模型、进度上报。"""
from __future__ import annotations

import re
import shutil
import subprocess
import threading

_install_status: dict = {"state": "idle", "model": "", "progress": 0, "message": ""}
_thread: threading.Thread | None = None


def ollama_installed() -> bool:
    return shutil.which("ollama") is not None


def install_status() -> dict:
    return dict(_install_status)


def start_model_install(model: str) -> dict:
    global _thread
    if not ollama_installed():
        return {"error": "Ollama 未安装，请先安装 Ollama"}
    if _thread and _thread.is_alive():
        return {"error": f"正在安装 {_install_status['model']}"}
    _install_status.update({"state": "running", "model": model,
                            "progress": 0, "message": "开始拉取..."})
    _thread = threading.Thread(target=_pull, args=(model,), daemon=True)
    _thread.start()
    return {"ok": True}


def _pull(model: str) -> None:
    try:
        proc = subprocess.Popen(
            ["ollama", "pull", model],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            pct = _parse_percent(line)
            if pct is not None:
                _install_status["progress"] = pct
            msg = line.strip().replace("\r", "")
            if msg:
                _install_status["message"] = msg
        proc.wait()
        _install_status["state"] = "done" if proc.returncode == 0 else "error"
        if proc.returncode == 0:
            _install_status["progress"] = 100
    except Exception as e:
        _install_status["state"] = "error"
        _install_status["message"] = str(e)


def _parse_percent(line: str) -> int | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", line)
    if m:
        try:
            return int(float(m.group(1)))
        except ValueError:
            return None
    return None
