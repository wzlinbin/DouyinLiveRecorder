from __future__ import annotations

import hashlib
import os
from pathlib import Path

from fastapi import HTTPException

from .db import PROJECT_ROOT

DEFAULT_DOWNLOAD_ROOT = PROJECT_ROOT / "downloads"
CONFIG_ROOT = PROJECT_ROOT / "config"


def resolve_path(path: str | Path, base: Path | None = None) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = (base or PROJECT_ROOT) / candidate
    return candidate.resolve()


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return os.path.normcase(str(path)).startswith(os.path.normcase(str(root)) + os.sep)


def ensure_allowed_path(path: str | Path, roots: list[Path] | None = None) -> Path:
    resolved = resolve_path(path)
    allowed_roots = [root.resolve() for root in (roots or [DEFAULT_DOWNLOAD_ROOT, CONFIG_ROOT])]
    if not any(is_relative_to(resolved, root) for root in allowed_roots):
        raise HTTPException(status_code=400, detail="路径不在允许的目录范围内")
    return resolved


def resolve_download_dir(path: str | None = None) -> Path:
    if not path:
        return DEFAULT_DOWNLOAD_ROOT.resolve()
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return ensure_allowed_path(candidate, [DEFAULT_DOWNLOAD_ROOT])
    return ensure_allowed_path(DEFAULT_DOWNLOAD_ROOT / candidate, [DEFAULT_DOWNLOAD_ROOT])


def file_identity(path: Path) -> str:
    resolved = path.resolve()
    stat = resolved.stat()
    identity = f"{os.path.normcase(str(resolved))}|{stat.st_size}|{int(stat.st_mtime)}"
    return hashlib.sha256(identity.encode("utf-8", errors="ignore")).hexdigest()


def public_path(path: str | Path) -> str:
    return str(Path(path).resolve())
