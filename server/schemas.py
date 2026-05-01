from __future__ import annotations

from pydantic import BaseModel, Field

from src.douyin_config import DOUYIN_MAX_BATCH_ITEMS


class RoomCreate(BaseModel):
    url: str
    name: str = ""
    platform: str = "unknown"
    quality: str = "原画"
    enabled: bool = True


class RoomPatch(BaseModel):
    url: str | None = None
    name: str | None = None
    platform: str | None = None
    quality: str | None = None
    enabled: bool | None = None


class ConfigSectionPatch(BaseModel):
    values: dict


class YouTubeOAuthStartRequest(BaseModel):
    redirect_uri: str = "http://localhost"


class YouTubeOAuthCompleteRequest(BaseModel):
    code: str = Field(min_length=1)
    state: str | None = None


class DownloadWatchSettingsPatch(BaseModel):
    enabled: bool | None = None
    directories: list[str] | None = None
    poll_interval_seconds: int | None = Field(default=None, ge=2)
    stable_checks: int | None = Field(default=None, ge=1)
    transcode_non_mp4: bool | None = None
    delete_origin_after_transcode: bool | None = None
    reencode_h264: bool | None = None


class RecordedFileRenameRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)


class RecordedFileTranscodeRequest(BaseModel):
    delete_origin: bool = False
    reencode_h264: bool = False


class DouyinSingleRequest(BaseModel):
    url: str
    output_dir: str | None = None
    cookie: str | None = None
    cookies: str | None = None
    proxy: str | None = None
    overwrite: bool = False

    def request_cookie(self) -> str | None:
        return self.cookie or self.cookies


class DouyinUserRequest(DouyinSingleRequest):
    max_items: int = Field(default=10, ge=1, le=DOUYIN_MAX_BATCH_ITEMS)
