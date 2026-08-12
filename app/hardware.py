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


# 候选模型目录：name / 参数量(B) / 磁盘占用(GB)
MODEL_CATALOG = [
    {"name": "qwen2.5:32b", "params_b": 32.8, "disk_gb": 20},
    {"name": "qwen2.5:14b", "params_b": 14.8, "disk_gb": 9},
    {"name": "qwen2.5:7b", "params_b": 7.6, "disk_gb": 4.7},
    {"name": "qwen2.5:3b", "params_b": 3.0, "disk_gb": 2},
    {"name": "qwen2.5:1.5b", "params_b": 1.5, "disk_gb": 1},
    {"name": "qwen2.5:0.5b", "params_b": 0.5, "disk_gb": 0.4},
]


def est_model_ram_gb(params_b: float) -> float:
    """估算模型运行内存占用：量化约 0.8GB/十亿参数 + 1GB 上下文开销。"""
    return params_b * 0.8 + 1


def recommend_models(hw: dict, max_ram_ratio: float = 0.85, limit: int = 5) -> list[dict]:
    """在 85% 内存预算内，按资源占用从高到低推荐模型（最多 limit 个）。"""
    budget = (hw.get("ram_gb") or 0) * max_ram_ratio
    fits = []
    for m in MODEL_CATALOG:
        est_ram = est_model_ram_gb(m["params_b"])
        if est_ram <= budget:
            fits.append({**m, "est_ram_gb": round(est_ram, 1)})
    fits.sort(key=lambda x: x["est_ram_gb"], reverse=True)
    return fits[:limit]
