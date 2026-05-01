from __future__ import annotations

import configparser
import os
from pathlib import Path

from .db import PROJECT_ROOT

CONFIG_FILE = PROJECT_ROOT / "config" / "config.ini"
ADMIN_SECTION = "后台管理"


def get_runtime_setting(*keys: str, env: str | None = None, default: str = "", config_path: Path = CONFIG_FILE) -> str:
    parser = configparser.RawConfigParser()
    parser.optionxform = str
    if config_path.exists():
        parser.read(config_path, encoding="utf-8-sig")
        if parser.has_section(ADMIN_SECTION):
            lower_map = {option.lower(): value for option, value in parser.items(ADMIN_SECTION)}
            for key in keys:
                value = lower_map.get(key.lower(), "").strip()
                if value:
                    return value
    if env:
        return os.environ.get(env, default).strip()
    return default


def admin_token() -> str:
    return get_runtime_setting("ADMIN_API_TOKEN", "后台管理Token", "后台管理令牌", env="ADMIN_API_TOKEN")


def admin_host() -> str:
    return get_runtime_setting("ADMIN_HOST", "后台监听地址", env="ADMIN_HOST", default="127.0.0.1")


def admin_port() -> int:
    raw = get_runtime_setting("ADMIN_PORT", "后台监听端口", env="ADMIN_PORT", default="8000")
    return int(raw)
