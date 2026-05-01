from __future__ import annotations

import asyncio
from pathlib import Path

from .models import TEMP_SUFFIXES, VIDEO_SUFFIXES
from .path_service import DEFAULT_DOWNLOAD_ROOT, ensure_allowed_path, file_identity, is_relative_to, public_path
from .repository import Repository
from .transcode_service import TranscodeService


class DownloadWatchService:
    def __init__(self, repository: Repository, transcode_service: TranscodeService) -> None:
        self.repository = repository
        self.transcode_service = transcode_service

    def get_settings(self) -> dict:
        return self.repository.get_setting("download_watch.settings", {
            "enabled": True,
            "directories": [str(DEFAULT_DOWNLOAD_ROOT.resolve())],
            "poll_interval_seconds": 10,
            "stable_checks": 2,
            "transcode_non_mp4": False,
            "delete_origin_after_transcode": False,
            "reencode_h264": False,
        })

    def update_settings(self, data: dict) -> dict:
        current = self.get_settings()
        updated = {**current, **{key: value for key, value in data.items() if value is not None}}
        directories = []
        for directory in updated.get("directories") or []:
            directories.append(public_path(ensure_allowed_path(directory, [DEFAULT_DOWNLOAD_ROOT])))
        updated["directories"] = directories or [str(DEFAULT_DOWNLOAD_ROOT.resolve())]
        updated["poll_interval_seconds"] = max(2, int(updated.get("poll_interval_seconds", 10)))
        updated["stable_checks"] = max(1, int(updated.get("stable_checks", 2)))
        updated["enabled"] = bool(updated.get("enabled", True))
        updated["transcode_non_mp4"] = bool(updated.get("transcode_non_mp4", False))
        updated["delete_origin_after_transcode"] = bool(updated.get("delete_origin_after_transcode", False))
        updated["reencode_h264"] = bool(updated.get("reencode_h264", False))
        self.repository.upsert_setting("download_watch.settings", updated, "download_watch")
        self.repository.add_event("download_watch_settings", "下载监控设置已更新")
        return updated

    def scan_once(self) -> dict[str, int]:
        settings = self.get_settings()
        if not settings.get("enabled", True):
            return {"candidates": 0, "registered": 0}
        candidates = 0
        registered = 0
        stable_target = int(settings.get("stable_checks", 2))
        for directory in settings.get("directories") or []:
            root = ensure_allowed_path(directory, [DEFAULT_DOWNLOAD_ROOT])
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if self._is_admin_recording_path(path):
                    continue
                if not path.is_file() or path.suffix.lower() in TEMP_SUFFIXES:
                    continue
                if path.suffix.lower() not in VIDEO_SUFFIXES:
                    continue
                candidates += 1
                if self._observe_file(root, path, stable_target, settings):
                    registered += 1
        return {"candidates": candidates, "registered": registered}

    @staticmethod
    def _is_admin_recording_path(path: Path) -> bool:
        admin_jobs_root = (DEFAULT_DOWNLOAD_ROOT / "admin_jobs").resolve()
        return is_relative_to(path.resolve(), admin_jobs_root)

    def _observe_file(self, root: Path, path: Path, stable_target: int, settings: dict) -> bool:
        identity = file_identity(path)
        stat = path.stat()
        with self.repository.database.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM download_watch_records WHERE file_identity = ?", (identity,)
            ).fetchone()
            stable_count = 1
            status = "candidate"
            if row:
                if row["status"] == "registered":
                    return False
                if row["observed_size"] == stat.st_size and int(row["observed_mtime"]) == int(stat.st_mtime):
                    stable_count = row["stable_count"] + 1
                else:
                    stable_count = 1
                status = row["status"]
            if stable_count >= stable_target and stat.st_size > 0:
                status = "stable"
            connection.execute(
                """
                INSERT INTO download_watch_records(source_dir, local_path, file_identity, observed_size,
                    observed_mtime, stable_count, status, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(file_identity) DO UPDATE SET observed_size = excluded.observed_size,
                    observed_mtime = excluded.observed_mtime, stable_count = excluded.stable_count,
                    status = excluded.status, updated_at = CURRENT_TIMESTAMP
                """,
                (public_path(root), public_path(path), identity, stat.st_size, stat.st_mtime, stable_count, status),
            )
        if status != "stable":
            return False
        final_path = path
        if settings.get("transcode_non_mp4") and path.suffix.lower() != ".mp4":
            final_path = self.transcode_service.transcode_to_mp4(
                path,
                delete_origin=bool(settings.get("delete_origin_after_transcode", False)),
                reencode_h264=bool(settings.get("reencode_h264", False)),
            )
        recorded = self.repository.register_file(final_path, source="download_watch")
        with self.repository.database.transaction() as connection:
            connection.execute(
                """
                UPDATE download_watch_records SET status = 'registered', recorded_file_id = ?,
                    registered_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE file_identity = ?
                """,
                (recorded["id"], identity),
            )
        self.repository.add_event("download_watch_registered", f"下载监控已登记文件：{final_path.name}", file_id=recorded["id"])
        return True

    async def run_loop(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            try:
                await asyncio.to_thread(self.scan_once)
            except Exception as error:
                self.repository.add_event("download_watch_error", str(error), level="error")
            settings = self.get_settings()
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=int(settings.get("poll_interval_seconds", 10)))
            except asyncio.TimeoutError:
                pass
