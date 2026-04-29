from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from src.youtube_uploader import YOUTUBE_UPLOAD_SCOPE

from .db import PROJECT_ROOT
from .path_service import resolve_path
from .repository import Repository


class AnalyticsService:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def list_video_metrics(self) -> list[dict]:
        return self.repository.list_rows("youtube_metrics", order_by="metric_date DESC, youtube_video_id ASC")

    def refresh_video_metrics(self) -> dict[str, int]:
        video_ids = self._uploaded_video_ids()
        if not video_ids:
            return {"requested": 0, "updated": 0}
        youtube = self._build_client()
        updated = 0
        for chunk in self._chunks(video_ids, 50):
            response = youtube.videos().list(part="statistics", id=",".join(chunk)).execute()
            for item in response.get("items", []):
                stats = item.get("statistics", {})
                self.repository.upsert_youtube_metric(
                    item["id"],
                    metric_date=date.today().isoformat(),
                    view_count=int(stats.get("viewCount", 0)),
                    like_count=int(stats.get("likeCount", 0)),
                    comment_count=int(stats.get("commentCount", 0)),
                )
                updated += 1
        self.repository.add_event("youtube_metrics_refreshed", f"Refreshed metrics for {updated} videos")
        return {"requested": len(video_ids), "updated": updated}

    def _uploaded_video_ids(self) -> list[str]:
        rows = self.repository.list_rows(
            "upload_records",
            where="status = ? AND youtube_video_id != ''",
            params=("uploaded",),
            order_by="id ASC",
        )
        result = []
        for row in rows:
            video_id = row.get("youtube_video_id")
            if video_id and video_id not in result:
                result.append(video_id)
        return result

    def _build_client(self):
        token_path = self._token_path()
        if not token_path.exists():
            raise RuntimeError(f"YouTube token file not found: {token_path}")
        credentials = Credentials.from_authorized_user_file(str(token_path), YOUTUBE_UPLOAD_SCOPE)
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            token_path.write_text(credentials.to_json(), encoding="utf-8")
        if not credentials.valid:
            raise RuntimeError("YouTube credentials are not valid")
        return build("youtube", "v3", credentials=credentials)

    def _token_path(self) -> Path:
        settings = self.repository.get_setting("ini.YouTube上传", {})
        raw = settings.get("YouTube令牌文件路径", "config/youtube_token.json")
        if isinstance(raw, dict):
            raw = "config/youtube_token.json"
        return resolve_path(str(raw), PROJECT_ROOT)

    @staticmethod
    def _chunks(items: list[str], size: int):
        for index in range(0, len(items), size):
            yield items[index:index + size]
