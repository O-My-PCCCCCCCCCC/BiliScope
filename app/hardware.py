"""硬件检测与本地模型推荐。"""
from __future__ import annotations

import os
import shutil


def detect_hardware() -> dict:
    try:
        import psutil
        ram_gb = round(psutil.virtual_memory().total / (1024 ** 3))
    except ImportError:
        ram_gb = 0
    cpu = os.cpu_count() or 0

    gpus = []
    try:
        from pynvml import (nvmlInit, nvmlDeviceGetCount, nvmlDeviceGetHandleByIndex,
                            nvmlDeviceGetMemoryInfo, nvmlShutdown)
        nvmlInit()
        for i in range(nvmlDeviceGetCount()):
            handle = nvmlDeviceGetHandleByIndex(i)
            mem = nvmlDeviceGetMemoryInfo(handle)
            gpus.append({"vram_gb": round(mem.total / (1024 ** 3))})
        nvmlShutdown()
    except Exception:
        if shutil.which("nvidia-smi"):
            import re
            import subprocess
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True,
            ).stdout
            for line in out.strip().splitlines():
                m = re.search(r"(\d+)", line)
                if m:
                    gpus.append({"vram_gb": round(int(m.group(1)) / 1024)})
    return {"cpu": cpu, "ram_gb": ram_gb, "gpu": gpus}


def recommend_ollama_model(hw: dict) -> str:
    gpus = hw.get("gpu") or []
    if gpus:
        vram = max(g["vram_gb"] for g in gpus)
        if vram >= 16:
            return "qwen2.5:32b"
        if vram >= 8:
            return "qwen2.5:14b"
        if vram >= 4:
            return "qwen2.5:7b"
        return "qwen2.5:1.5b"
    ram = hw.get("ram_gb") or 0
    if ram >= 16:
        return "qwen2.5:7b"
    if ram >= 8:
        return "qwen2.5:3b"
    if ram >= 4:
        return "qwen2.5:1.5b"
    return "qwen2.5:0.5b"
