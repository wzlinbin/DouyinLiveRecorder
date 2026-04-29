from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from src.youtube_uploader import YouTubeUploadConfig, create_youtube_uploader

from .db import PROJECT_ROOT
from .path_service import resolve_path
from .repository import Repository


class UploadService:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository
        self._uploader = None
        self._running_uploads: set[int] = set()

    def retry(self, upload_id: int) -> dict:
        upload = self.repository.retry_upload(upload_id)
        if not upload:
            raise HTTPException(status_code=404, detail="Upload record not found")
        self.repository.add_event("upload_retry_requested", f"Retry requested for upload {upload_id}", upload_id=upload_id)
        return upload

    async def run_loop(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            try:
                self.enqueue_pending_uploads()
            except Exception as error:
                self.repository.add_event("upload_loop_error", str(error), level="error")
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=10)
            except asyncio.TimeoutError:
                pass

    def enqueue_pending_uploads(self) -> int:
        uploader = self._get_uploader()
        if not uploader:
            return 0
        rows = self.repository.list_rows(
            "upload_records",
            where="status IN ('pending','failed')",
            params=(),
            order_by="id ASC",
            limit=20,
        )
        enqueued = 0
        for row in rows:
            upload_id = int(row["id"])
            if upload_id in self._running_uploads:
                continue
            path = Path(row["local_path"])
            if not path.exists() or not path.is_file() or path.stat().st_size <= 0:
                self.repository.mark_upload_failed(upload_id, "File is missing or empty")
                continue
            if not uploader._is_eligible(path):
                self.repository.mark_upload_failed(upload_id, "File is not eligible for YouTube upload")
                continue
            self.repository.mark_upload_status(upload_id, "uploading")
            self._running_uploads.add(upload_id)
            uploader.enqueue_upload(str(path), row.get("title") or path.stem)
            asyncio.get_running_loop().create_task(self._sync_upload_result(upload_id, str(path)))
            enqueued += 1
        return enqueued

    async def _sync_upload_result(self, upload_id: int, path: str) -> None:
        try:
            await asyncio.to_thread(self._wait_for_uploader_state, upload_id, path)
        finally:
            self._running_uploads.discard(upload_id)

    def _wait_for_uploader_state(self, upload_id: int, path: str) -> None:
        uploader = self._get_uploader()
        if not uploader:
            return
        file_path = Path(path).resolve()
        last_status = "uploading"
        while True:
            key = uploader._file_key(file_path)
            with uploader.state_lock:
                item = dict(uploader.state.get(key, {}))
            status = item.get("status") or last_status
            if status == "uploaded":
                self.repository.mark_upload_status(upload_id, "uploaded", youtube_video_id=item.get("youtube_video_id", ""))
                self.repository.add_event("upload_completed", f"Upload {upload_id} completed", upload_id=upload_id)
                return
            if status == "failed":
                self.repository.mark_upload_failed(upload_id, item.get("last_error", "Upload failed"))
                return
            last_status = status
            time.sleep(1)

    def _get_uploader(self):
        if self._uploader is not None:
            return self._uploader
        settings = self.repository.get_setting("ini.YouTube上传", {})
        enabled = self._yes(settings.get("是否启用YouTube上传(是/否)", "否"))
        if not enabled:
            return None
        client_secret = self._setting_path(settings, "YouTube客户端密钥文件路径", "config/youtube_client_secret.json")
        token_file = self._setting_path(settings, "YouTube令牌文件路径", "config/youtube_token.json")
        state_file = self._setting_path(settings, "YouTube上传状态文件路径", "config/youtube_upload_state.json")
        if not client_secret.exists():
            self.repository.add_event("upload_disabled", "YouTube client secret file is missing", level="error")
            return None
        config = YouTubeUploadConfig(
            enabled=True,
            client_secret_file=str(client_secret),
            token_file=str(token_file),
            state_file=str(state_file),
            privacy_status=str(settings.get("视频隐私状态(public/private/unlisted)", "public")),
            title_template=str(settings.get("视频标题模板", "{record_name}")),
            description=str(settings.get("视频描述", "")),
            tags=self._tags(settings.get("视频标签(逗号分隔)", "")),
            category_id=str(settings.get("视频分类ID", "22")),
            allowed_extensions=self._extensions(settings.get("YouTube上传文件扩展名(逗号分隔)", "mp4,mkv,flv,ts")),
            max_attempts=int(settings.get("失败重试次数", 3) or 3),
        )
        self._uploader = create_youtube_uploader(config)
        return self._uploader

    @staticmethod
    def _yes(value: Any) -> bool:
        return str(value).strip().lower() in {"是", "true", "1", "yes", "y"}

    @staticmethod
    def _tags(value: Any) -> list[str]:
        return [item.strip() for item in str(value or "").split(",") if item.strip()]

    @staticmethod
    def _extensions(value: Any) -> set[str]:
        return {item.strip().lower().lstrip(".") for item in str(value or "").split(",") if item.strip()}

    @staticmethod
    def _setting_path(settings: dict, key: str, default: str) -> Path:
        raw = settings.get(key, default)
        if isinstance(raw, dict):
            raw = default
        return resolve_path(str(raw), PROJECT_ROOT)
