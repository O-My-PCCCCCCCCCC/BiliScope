from __future__ import annotations

from app.hardware import est_model_ram_gb, recommend_models
from app.ollama_manager import _parse_percent


def test_recommend_models_sorted_and_capped():
    hw = {"cpu": 8, "ram_gb": 16, "gpu": []}
    models = recommend_models(hw, max_ram_ratio=0.85, limit=5)
    # 16G * 0.85 = 13.6G 预算，32b(27G) 被排除，最大是 14b(12.8G)
    names = [m["name"] for m in models]
    assert "qwen2.5:32b" not in names
    assert names[0] == "qwen2.5:14b"
    # 按占用降序
    ram_list = [m["est_ram_gb"] for m in models]
    assert ram_list == sorted(ram_list, reverse=True)
    assert len(models) <= 5


def test_recommend_all_fit_on_big_machine():
    hw = {"cpu": 80, "ram_gb": 64, "gpu": []}
    models = recommend_models(hw, max_ram_ratio=0.85, limit=5)
    assert models[0]["name"] == "qwen2.5:32b"
    assert all(m["est_ram_gb"] <= 64 * 0.85 for m in models)


def test_est_model_ram():
    assert est_model_ram_gb(7.6) > 6


def test_parse_percent():
    assert _parse_percent("pulling 45%") == 45
    assert _parse_percent("pulling manifest") is None
