from __future__ import annotations

import configparser
import re
from pathlib import Path
from urllib.parse import urlparse

from .db import PROJECT_ROOT
from .repository import Repository

CONFIG_FILE = PROJECT_ROOT / "config" / "config.ini"
URL_CONFIG_FILE = PROJECT_ROOT / "config" / "URL_config.ini"
SENSITIVE_WORDS = ("cookie", "token", "secret", "密钥", "令牌", "密码", "授权码")
QUALITY_VALUES = {"原画", "蓝光", "超清", "高清", "标清", "流畅"}


def guess_platform(url: str) -> str:
    host = urlparse(url if "://" in url else f"https://{url}").netloc.lower()
    if "douyin" in host:
        return "douyin"
    if "tiktok" in host:
        return "tiktok"
    if "youtube" in host or "youtu.be" in host:
        return "youtube"
    if "kuaishou" in host:
        return "kuaishou"
    if "bilibili" in host:
        return "bilibili"
    return host.split(":", 1)[0] or "unknown"


def sanitize_key(section: str, option: str) -> bool:
    lower = f"{section}.{option}".lower()
    return any(word.lower() in lower for word in SENSITIVE_WORDS)


def parse_url_line(line: str, default_quality: str = "原画") -> dict[str, str | bool] | None:
    stripped = line.strip()
    if not stripped or len(stripped) < 8:
        return None
    enabled = not stripped.startswith("#")
    if not enabled:
        stripped = stripped.lstrip("#").strip()
    parts = [part.strip() for part in re.split(r"[,，]", stripped) if part.strip()]
    if not parts:
        return None
    quality = default_quality
    url = parts[0]
    name = ""
    if parts[0] in QUALITY_VALUES and len(parts) >= 2:
        quality = parts[0]
        url = parts[1]
        name = parts[2] if len(parts) > 2 else ""
    elif len(parts) >= 2:
        url = parts[0]
        name = parts[1]
    if "主播:" in name:
        name = name.split("主播:", 1)[1].strip()
    if "主播：" in name:
        name = name.split("主播：", 1)[1].strip()
    if "://" not in url:
        url = f"https://{url}"
    parsed = urlparse(url)
    if not parsed.netloc:
        return None
    return {
        "url": url,
        "name": name,
        "quality": quality,
        "platform": guess_platform(url),
        "enabled": enabled,
    }


class ConfigService:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def list_settings(self) -> list[dict]:
        return self.repository.list_rows("settings", order_by="category ASC, key ASC")

    def get_section(self, section: str) -> dict:
        return self.repository.get_setting(f"ini.{section}", {})

    def update_section(self, section: str, values: dict) -> dict:
        current = self.get_section(section)
        updated = {**current, **self._sanitize_values(section, values)}
        self.repository.upsert_setting(f"ini.{section}", updated, "ini")
        self.repository.add_event("config_update", f"Updated ini section {section}")
        return updated

    def export_ini(self, config_path: Path = CONFIG_FILE, url_config_path: Path = URL_CONFIG_FILE) -> dict[str, int]:
        parser = configparser.RawConfigParser()
        parser.optionxform = str
        settings = self.list_settings()
        sections = 0
        for row in settings:
            key = row["key"]
            if not key.startswith("ini."):
                continue
            section = key[4:]
            values = self.repository.get_setting(key, {})
            if not parser.has_section(section):
                parser.add_section(section)
            for option, value in values.items():
                if isinstance(value, dict):
                    continue
                parser.set(section, option, str(value))
            sections += 1
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with config_path.open("w", encoding="utf-8-sig") as file:
            parser.write(file)
        rooms = self.repository.list_rows("rooms", order_by="id ASC")
        url_lines = []
        for room in rooms:
            prefix = "" if room.get("enabled") else "#"
            line = f"{prefix}{room['quality']},{room['url']}"
            if room.get("name"):
                line += f",主播: {room['name']}"
            url_lines.append(line)
        url_config_path.write_text("\n".join(url_lines) + ("\n" if url_lines else ""), encoding="utf-8-sig")
        self.repository.add_event("config_export", f"Exported {sections} sections and {len(url_lines)} rooms")
        return {"settings_sections": sections, "room_lines": len(url_lines)}

    def _sanitize_values(self, section: str, values: dict) -> dict:
        result = {}
        for option, value in values.items():
            if sanitize_key(section, option):
                result[option] = {"configured": bool(value)}
            else:
                result[option] = value
        return result

    def import_ini(self, config_path: Path = CONFIG_FILE, url_config_path: Path = URL_CONFIG_FILE) -> dict[str, int]:
        settings_count = 0
        rooms_count = 0
        default_quality = "原画"
        parser = configparser.RawConfigParser()
        parser.optionxform = str
        if config_path.exists():
            parser.read(config_path, encoding="utf-8-sig")
            for section in parser.sections():
                section_values = {}
                for option, value in parser.items(section):
                    if sanitize_key(section, option):
                        section_values[option] = {"configured": bool(value)}
                    else:
                        section_values[option] = value
                    if option == "原画|超清|高清|标清|流畅" and value:
                        default_quality = value
                self.repository.upsert_setting(f"ini.{section}", section_values, "ini")
                settings_count += 1
        if url_config_path.exists():
            for line in url_config_path.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
                parsed = parse_url_line(line, default_quality)
                if parsed:
                    self.repository.create_room(**parsed, source="ini")
                    rooms_count += 1
        self.repository.upsert_setting("admin.imported_from_ini", True, "admin")
        self.repository.add_event("config_import", f"Imported {settings_count} setting sections and {rooms_count} room lines")
        return {"settings_sections": settings_count, "room_lines": rooms_count}

    def import_once(self) -> dict[str, int] | None:
        if self.repository.get_setting("admin.imported_from_ini", False):
            return None
        return self.import_ini()
