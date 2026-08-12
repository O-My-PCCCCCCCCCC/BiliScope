"""Ollama 本地模型管理：检测安装、自动下载安装 Ollama、后台拉取模型、进度上报。"""
from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import threading

import httpx

from app.config import ROOT

_install_status: dict = {"state": "idle", "phase": "", "model": "",
                         "progress": 0, "message": ""}
_thread: threading.Thread | None = None


def _binary() -> str | None:
    p = shutil.which("ollama")
    if p:
        return p
    candidates = [
        "C:/Program Files/Ollama/ollama.exe",
        os.path.expanduser("~/AppData/Local/Programs/Ollama/ollama.exe"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def ollama_installed() -> bool:
    return _binary() is not None


def install_status() -> dict:
    return dict(_install_status)


def _start_job(fn) -> dict:
    global _thread
    if _thread and _thread.is_alive():
        return {"error": f"已有任务进行中: {_install_status['message']}"}
    _thread = threading.Thread(target=fn, daemon=True)
    _thread.start()
    return {"ok": True}


def start_ollama_install() -> dict:
    """后台自动下载并安装 Ollama。"""
    if ollama_installed():
        return {"ok": True, "message": "已安装"}
    _install_status.update({"state": "running", "phase": "ollama", "model": "",
                            "progress": 0, "message": "准备下载 Ollama..."})
    return _start_job(_install_ollama)


def start_model_install(model: str) -> dict:
    """后台拉取模型。"""
    if not ollama_installed():
        return {"error": "Ollama 未安装，请先安装 Ollama"}
    _install_status.update({"state": "running", "phase": "model", "model": model,
                            "progress": 0, "message": "开始拉取..."})
    return _start_job(lambda: _pull(model))


def _set(msg: str, progress: int | None = None) -> None:
    _install_status["message"] = msg
    if progress is not None:
        _install_status["progress"] = progress


def _download(url: str, dest: str) -> None:
    with httpx.stream("GET", url, follow_redirects=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length") or 0)
        done = 0
        with open(dest, "wb") as f:
            for chunk in r.iter_bytes(1024 * 64):
                f.write(chunk)
                done += len(chunk)
                if total:
                    _install_status["progress"] = min(int(done * 100 / total), 99)


def _latest_ollama_version() -> str:
    try:
        r = httpx.get("https://api.github.com/repos/ollama/ollama/releases/latest",
                      timeout=15)
        return r.json().get("tag_name", "v0.32.9")
    except Exception:
        return "v0.32.9"


def _install_ollama() -> None:
    system = platform.system()
    try:
        if system != "Windows":
            _install_status.update({"state": "error",
                                    "message": f"{system} 系统请到 ollama.com/download 手动安装"})
            return
        dest = ROOT / "data" / "ollama_setup.exe"
        dest.parent.mkdir(parents=True, exist_ok=True)
        _set("下载 Ollama 安装包（约 700MB，请耐心等待）...", 0)
        urls = [
            "https://ollama.com/download/OllamaSetup.exe",
            f"https://github.com/ollama/ollama/releases/download/{_latest_ollama_version()}/OllamaSetup.exe",
        ]
        for url in urls:
            try:
                _download(url, str(dest))
                if dest.stat().st_size > 10 * 1024 * 1024:  # >10MB 视为下载成功
                    break
            except Exception:
                continue
        if dest.stat().st_size < 10 * 1024 * 1024:
            raise RuntimeError("下载失败，请检查网络或手动安装")
        _set("静默安装中，请稍候...", 99)
        subprocess.run([str(dest), "/S"], check=True, timeout=600)
        if not ollama_installed():
            raise RuntimeError("安装完成但未找到 ollama，请手动安装")
        _install_status.update({"state": "done", "progress": 100,
                                "message": "Ollama 安装完成，可以拉取模型了"})
    except Exception as e:
        _install_status.update({"state": "error", "message": str(e)})


def _pull(model: str) -> None:
    binary = _binary()
    try:
        assert binary is not None
        proc = subprocess.Popen(
            [binary, "pull", model],
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
