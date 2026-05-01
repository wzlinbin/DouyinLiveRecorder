# -*- coding: utf-8 -*-

import json
import os
import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.logger import logger

YOUTUBE_UPLOAD_SCOPE = ["https://www.googleapis.com/auth/youtube.upload"]


@dataclass
class YouTubeUploadConfig:
    enabled: bool
    client_secret_file: str
    token_file: str
    state_file: str
    privacy_status: str = "public"
    title_template: str = "{record_name}"
    description: str = ""
    tags: list[str] | None = None
    category_id: str = "22"
    allowed_extensions: set[str] | None = None
    max_attempts: int = 3
    enqueue_retryable_on_start: bool = True


class YouTubeUploader:
    def __init__(self, config: YouTubeUploadConfig) -> None:
        self.config = config
        self.upload_queue: queue.Queue[tuple[str, str | None]] = queue.Queue()
        self.state_lock = threading.Lock()
        self.state = self._load_state()
        self.worker = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker.start()
        if self.config.enqueue_retryable_on_start:
            self._enqueue_retryable_items()

    def wait_for_uploads(self) -> None:
        self.upload_queue.join()

    def enqueue_upload(self, file_path: str, record_name: str | None = None) -> None:
        if not self.config.enabled:
            return

        path = Path(file_path).expanduser().resolve()
        if not self._is_eligible(path):
            return

        key = self._file_key(path)
        with self.state_lock:
            item = self.state.get(key)
            if item and item.get("status") in {"pending", "uploading", "uploaded"}:
                logger.debug(f"YouTube upload skipped, file already tracked: {path}")
                return
            self.state[key] = self._state_item(path, "pending", record_name=record_name)
            self._save_state_locked()

        self.upload_queue.put((str(path), record_name))
        logger.debug(f"YouTube upload enqueued: {path}")

    def _enqueue_retryable_items(self) -> None:
        for item in self.state.values():
            if item.get("status") not in {"pending", "uploading", "failed"}:
                continue
            if int(item.get("attempts", 0)) >= self.config.max_attempts:
                continue
            path = Path(item.get("path", ""))
            if self._is_eligible(path):
                self.upload_queue.put((str(path), item.get("record_name") or None))

    def _worker_loop(self) -> None:
        while True:
            file_path, record_name = self.upload_queue.get()
            try:
                self._upload_with_state(Path(file_path), record_name)
            except Exception as e:
                logger.error(f"YouTube upload worker error: {e}")
            finally:
                self.upload_queue.task_done()

    def _upload_with_state(self, path: Path, record_name: str | None) -> None:
        key = self._file_key(path)
        with self.state_lock:
            item = self.state.get(key, self._state_item(path, "pending", record_name=record_name))
            attempts = int(item.get("attempts", 0)) + 1
            if attempts > self.config.max_attempts:
                logger.error(f"YouTube upload skipped after too many attempts: {path}")
                return
            item.update({"status": "uploading", "attempts": attempts, "updated_at": self._now()})
            self.state[key] = item
            self._save_state_locked()

        try:
            video_id = self._upload(path, record_name)
        except Exception as e:
            with self.state_lock:
                item = self.state.get(key, self._state_item(path, "failed", record_name=record_name))
                item.update({"status": "failed", "last_error": str(e), "updated_at": self._now()})
                self.state[key] = item
                self._save_state_locked()
            logger.error(f"YouTube upload failed: {path}, {e}")
            return

        with self.state_lock:
            item = self.state.get(key, self._state_item(path, "uploaded", record_name=record_name))
            item.update({
                "status": "uploaded",
                "youtube_video_id": video_id,
                "last_error": "",
                "updated_at": self._now(),
            })
            self.state[key] = item
            self._save_state_locked()
        logger.debug(f"YouTube upload completed: {path}, video_id={video_id}")

    def _upload(self, path: Path, record_name: str | None) -> str:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        token_path = Path(self.config.token_file).expanduser()
        client_secret_path = Path(self.config.client_secret_file).expanduser()

        if not client_secret_path.exists():
            raise FileNotFoundError(f"YouTube client secret file not found: {client_secret_path}")

        credentials = None
        if token_path.exists():
            credentials = Credentials.from_authorized_user_file(str(token_path), YOUTUBE_UPLOAD_SCOPE)

        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), YOUTUBE_UPLOAD_SCOPE)
                auth_url, _ = flow.authorization_url(prompt="consent")
                print("\n请打开下面的 YouTube OAuth 授权链接完成登录授权：")
                print(auth_url)
                credentials = flow.run_local_server(port=0, open_browser=False)
            token_path.parent.mkdir(parents=True, exist_ok=True)
            token_path.write_text(credentials.to_json(), encoding="utf-8")

        youtube = build("youtube", "v3", credentials=credentials)
        title = self._format_title(path, record_name)
        body = {
            "snippet": {
                "title": title[:100],
                "description": self.config.description,
                "tags": self.config.tags or [],
                "categoryId": self.config.category_id,
            },
            "status": {
                "privacyStatus": self.config.privacy_status,
            },
        }
        media = MediaFileUpload(str(path), chunksize=8 * 1024 * 1024, resumable=True)
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                logger.debug(f"YouTube upload progress {path.name}: {int(status.progress() * 100)}%")

        video_id = response.get("id")
        if not video_id:
            raise RuntimeError("YouTube upload response did not include a video id")
        return video_id

    def _format_title(self, path: Path, record_name: str | None) -> str:
        values = {
            "record_name": record_name or path.stem,
            "file_name": path.name,
            "file_stem": path.stem,
            "date": time.strftime("%Y-%m-%d"),
            "time": time.strftime("%H:%M:%S"),
        }
        try:
            title = self.config.title_template.format(**values).strip()
        except Exception:
            title = record_name or path.stem
        return title or path.stem

    def _is_eligible(self, path: Path) -> bool:
        if not path.exists() or not path.is_file():
            logger.debug(f"YouTube upload skipped, file does not exist: {path}")
            return False
        if path.stat().st_size <= 0:
            logger.debug(f"YouTube upload skipped, empty file: {path}")
            return False
        suffix = path.suffix.lower().lstrip(".")
        allowed = self.config.allowed_extensions or {"mp4", "mkv", "flv", "ts"}
        if suffix not in allowed:
            logger.debug(f"YouTube upload skipped, unsupported extension: {path}")
            return False
        return True

    def _file_key(self, path: Path) -> str:
        stat = path.stat()
        return f"{os.path.normcase(str(path))}|{stat.st_size}|{int(stat.st_mtime)}"

    def _state_item(self, path: Path, status: str, record_name: str | None = None) -> dict[str, Any]:
        stat = path.stat()
        return {
            "path": str(path),
            "record_name": record_name or "",
            "size": stat.st_size,
            "mtime": int(stat.st_mtime),
            "status": status,
            "youtube_video_id": "",
            "attempts": 0,
            "last_error": "",
            "updated_at": self._now(),
        }

    def _load_state(self) -> dict[str, Any]:
        state_path = Path(self.config.state_file).expanduser()
        if not state_path.exists():
            return {}
        try:
            return json.loads(state_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"Failed to read YouTube upload state: {e}")
            return {}

    def _save_state_locked(self) -> None:
        state_path = Path(self.config.state_file).expanduser()
        state_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = state_path.with_suffix(state_path.suffix + ".tmp")
        temp_path.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp_path, state_path)

    @staticmethod
    def _now() -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S")


def create_youtube_uploader(config: YouTubeUploadConfig) -> YouTubeUploader | None:
    if not config.enabled:
        return None
    try:
        import googleapiclient  # noqa: F401
        import google_auth_oauthlib  # noqa: F401
    except ImportError as e:
        logger.error(f"YouTube upload enabled but dependencies are missing: {e}")
        return None
    return YouTubeUploader(config)
