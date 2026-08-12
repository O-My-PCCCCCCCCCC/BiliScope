from __future__ import annotations

from app.hardware import recommend_ollama_model


def test_recommend_by_gpu_vram():
    assert recommend_ollama_model({"gpu": [{"vram_gb": 6}]}) == "qwen2.5:7b"
    assert recommend_ollama_model({"gpu": [{"vram_gb": 10}]}) == "qwen2.5:14b"
    assert recommend_ollama_model({"gpu": [{"vram_gb": 18}]}) == "qwen2.5:32b"


def test_recommend_by_ram_no_gpu():
    assert recommend_ollama_model({"gpu": [], "ram_gb": 8}) == "qwen2.5:3b"
    assert recommend_ollama_model({"gpu": [], "ram_gb": 16}) == "qwen2.5:7b"
    assert recommend_ollama_model({"gpu": [], "ram_gb": 4}) == "qwen2.5:1.5b"
