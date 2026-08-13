"""配置管理：读写 config.json，存放 Cookie 等敏感信息。"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path


def _app_dir() -> Path:
    """应用资源目录（web 静态文件），PyInstaller 冻结时在 _MEIPASS。"""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent.parent


def _data_dir() -> Path:
    """可写数据目录（config.json / data 数据库 / 缓存），冻结时在 exe 同目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


APP_DIR = _app_dir()
DATA_DIR = _data_dir()
ROOT = APP_DIR  # 兼容旧引用

_config_path: Path = DATA_DIR / "config.json"

DEFAULT_CONFIG: dict = {
    "cookies": {},
    "uid": None,
    "login_at": None,
    "smtp": {"host": "", "port": 465, "user": "", "password": "", "to": ""},
    "llm": {"provider": "ollama", "api_key": "", "base_url": "", "model": ""},
    "task_interval": {"history": "03:00", "invalid": "04:00", "updates": 6},
    "download_dir": "",
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
