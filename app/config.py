"""配置管理：读写 config.json，存放 Cookie 等敏感信息。"""
from __future__ import annotations

import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_config_path: Path = ROOT / "config.json"

DEFAULT_CONFIG: dict = {
    "cookies": {},
    "uid": None,
    "login_at": None,
    "smtp": {"host": "", "port": 465, "user": "", "password": "", "to": ""},
    "task_interval": {"history": "03:00", "invalid": "04:00", "updates": 6},
}


def set_config_path(path: Path) -> None:
    """测试用：重定向配置文件路径。"""
    global _config_path
    _config_path = Path(path)


def load_config() -> dict:
    if not _config_path.exists():
        return {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULT_CONFIG.items()}
    data = json.loads(_config_path.read_text(encoding="utf-8"))
    merged = {**DEFAULT_CONFIG, **data}
    merged["cookies"] = {**DEFAULT_CONFIG["cookies"], **data.get("cookies", {})}
    return merged


def save_config(cfg: dict) -> None:
    _config_path.parent.mkdir(parents=True, exist_ok=True)
    _config_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def get_cookies() -> dict:
    return load_config().get("cookies", {})


def save_cookies(cookies: dict) -> None:
    cfg = load_config()
    cfg["cookies"] = cookies
    cfg["login_at"] = int(time.time())
    save_config(cfg)
