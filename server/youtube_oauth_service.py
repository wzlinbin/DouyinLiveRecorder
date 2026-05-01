from __future__ import annotations

import secrets
import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from src.youtube_uploader import YOUTUBE_UPLOAD_SCOPE

YOUTUBE_READONLY_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
YOUTUBE_OAUTH_SCOPES = [*YOUTUBE_UPLOAD_SCOPE, YOUTUBE_READONLY_SCOPE]

from .db import PROJECT_ROOT
from .path_service import resolve_path
from .repository import Repository


class YouTubeOAuthService:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def status(self) -> dict[str, Any]:
        client_secret_path, token_path = self._configured_paths()
        token_status = self._token_status(token_path)
        return {
            "client_secret_path": str(client_secret_path),
            "token_path": str(token_path),
            "client_secret_exists": client_secret_path.is_file(),
            "token_exists": token_path.is_file(),
            **token_status,
        }

    def start(self, redirect_uri: str) -> dict[str, str]:
        client_secret_path, _ = self._configured_paths()
        if not client_secret_path.is_file():
            raise FileNotFoundError(f"YouTube client secret file not found: {client_secret_path}")
        state = secrets.token_urlsafe(24)
        flow = InstalledAppFlow.from_client_secrets_file(
            str(client_secret_path),
            YOUTUBE_OAUTH_SCOPES,
            redirect_uri=redirect_uri,
        )
        auth_url, returned_state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
            state=state,
        )
        self.repository.upsert_setting(
            "admin.youtube_oauth",
            {"state": returned_state or state, "redirect_uri": redirect_uri},
            "admin",
        )
        self.repository.add_event("youtube_oauth_started", "已生成 YouTube OAuth 授权链接")
        return {"auth_url": auth_url, "redirect_uri": redirect_uri}

    def complete(self, code_or_url: str, state: str | None = None) -> dict[str, Any]:
        code, parsed_state = self._extract_code_and_state(code_or_url)
        expected = self.repository.get_setting("admin.youtube_oauth", {})
        expected_state = expected.get("state") if isinstance(expected, dict) else None
        redirect_uri = expected.get("redirect_uri") if isinstance(expected, dict) else None
        if not redirect_uri:
            raise RuntimeError("请先生成授权链接")
        incoming_state = state or parsed_state
        if expected_state and incoming_state and incoming_state != expected_state:
            raise ValueError("授权状态不匹配，请重新生成授权链接")
        client_secret_path, token_path = self._configured_paths()
        if not client_secret_path.is_file():
            raise FileNotFoundError(f"YouTube client secret file not found: {client_secret_path}")
        flow = InstalledAppFlow.from_client_secrets_file(
            str(client_secret_path),
            YOUTUBE_OAUTH_SCOPES,
            redirect_uri=redirect_uri,
        )
        flow.fetch_token(code=code)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(flow.credentials.to_json(), encoding="utf-8")
        self.repository.upsert_setting("admin.youtube_oauth", {"state": "", "redirect_uri": redirect_uri}, "admin")
        self.repository.add_event("youtube_oauth_completed", "已保存 YouTube OAuth Token")
        return {
            "saved": True,
            "token_path": str(token_path),
            "token_exists": token_path.is_file(),
            "token_valid": self._token_status(token_path)["token_valid"],
        }

    def check_data_api_access(self) -> dict[str, Any]:
        _, token_path = self._configured_paths()
        if not token_path.is_file():
            return {
                "ok": False,
                "status": "missing_token",
                "message": "尚未生成 Google 令牌，请先完成 YouTube 授权。",
                "detail": "",
            }
        missing_scopes = self._missing_required_scopes_from_token_file(token_path)
        if missing_scopes:
            return {
                "ok": False,
                "status": "reauthorization_required",
                "message": "当前 Google 令牌缺少 YouTube Data API v3 检测权限，请重新生成授权链接并完成授权。",
                "detail": "缺少权限：" + "、".join(missing_scopes),
            }
        try:
            credentials = Credentials.from_authorized_user_file(str(token_path), YOUTUBE_OAUTH_SCOPES)
        except Exception as error:
            return {
                "ok": False,
                "status": "invalid_token",
                "message": "Google 令牌文件无法读取，请重新授权。",
                "detail": str(error),
            }

        missing_scopes = self._missing_required_scopes(credentials)
        if missing_scopes:
            return {
                "ok": False,
                "status": "reauthorization_required",
                "message": "当前 Google 令牌缺少 YouTube Data API v3 检测权限，请重新生成授权链接并完成授权。",
                "detail": "缺少权限：" + "、".join(missing_scopes),
            }

        try:
            if credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
                token_path.write_text(credentials.to_json(), encoding="utf-8")
            if not credentials.valid:
                return {
                    "ok": False,
                    "status": "invalid_token",
                    "message": "Google 令牌已失效，请重新授权。",
                    "detail": "",
                }
            youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)
            response = youtube.channels().list(part="id,snippet", mine=True, maxResults=1).execute()
        except HttpError as error:
            return self._data_api_http_error(error)
        except Exception as error:
            return {
                "ok": False,
                "status": "request_failed",
                "message": "无法完成 YouTube Data API v3 检测，请检查网络或代理设置。",
                "detail": str(error),
            }

        channel_title = ""
        items = response.get("items", [])
        if items:
            channel_title = items[0].get("snippet", {}).get("title", "")
        return {
            "ok": True,
            "status": "enabled",
            "message": "当前 Google 账号可以访问 YouTube Data API v3。",
            "detail": channel_title,
        }

    def _configured_paths(self) -> tuple[Path, Path]:
        settings = self.repository.get_setting("ini.YouTube上传", {})
        client_secret = self._setting_path(
            settings,
            ("YouTube客户端密钥文件路径", "youtube客户端密钥文件路径"),
            "config/youtube_client_secret.json",
        )
        token_file = self._setting_path(
            settings,
            ("YouTube令牌文件路径", "youtube令牌文件路径"),
            "config/youtube_token.json",
        )
        return client_secret, token_file

    @staticmethod
    def _setting(settings: dict[str, Any], keys: tuple[str, ...], default: str) -> Any:
        if not isinstance(settings, dict):
            return default
        for key in keys:
            if key in settings:
                return settings[key]
        lower_map = {str(key).lower(): value for key, value in settings.items()}
        for key in keys:
            lowered = key.lower()
            if lowered in lower_map:
                return lower_map[lowered]
        return default

    def _setting_path(self, settings: dict[str, Any], keys: tuple[str, ...], default: str) -> Path:
        raw = self._setting(settings, keys, default)
        if isinstance(raw, dict):
            raw = default
        return resolve_path(str(raw), PROJECT_ROOT)

    @staticmethod
    def _extract_code_and_state(code_or_url: str) -> tuple[str, str | None]:
        value = code_or_url.strip()
        if not value:
            raise ValueError("请输入授权回跳地址或 code")
        parsed = urlparse(value)
        if parsed.query:
            query = parse_qs(parsed.query)
            error = query.get("error", [""])[0]
            if error:
                raise ValueError(f"Google 授权失败：{error}")
            code = query.get("code", [""])[0]
            state = query.get("state", [""])[0] or None
            if code:
                return code, state
        return value, None

    @staticmethod
    def _token_status(token_path: Path) -> dict[str, Any]:
        if not token_path.is_file():
            return {"token_valid": False, "token_error": "", "data_api_scope_valid": False}
        missing_scopes = YouTubeOAuthService._missing_required_scopes_from_token_file(token_path)
        try:
            credentials = Credentials.from_authorized_user_file(str(token_path), YOUTUBE_OAUTH_SCOPES)
        except Exception as error:
            return {"token_valid": False, "token_error": str(error), "data_api_scope_valid": False}
        return {
            "token_valid": bool(credentials.valid or credentials.refresh_token),
            "token_error": "",
            "data_api_scope_valid": not missing_scopes and not YouTubeOAuthService._missing_required_scopes(credentials),
        }

    @staticmethod
    def _missing_required_scopes(credentials: Credentials) -> list[str]:
        granted = set(credentials.granted_scopes or credentials.scopes or [])
        if not granted:
            return []
        return [scope for scope in YOUTUBE_OAUTH_SCOPES if scope not in granted]

    @staticmethod
    def _missing_required_scopes_from_token_file(token_path: Path) -> list[str]:
        try:
            payload = json.loads(token_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        scopes = payload.get("scopes")
        if not scopes:
            return []
        granted = set(scopes)
        return [scope for scope in YOUTUBE_OAUTH_SCOPES if scope not in granted]

    @staticmethod
    def _data_api_http_error(error: HttpError) -> dict[str, Any]:
        detail = error.content.decode("utf-8", errors="ignore") if error.content else ""
        reason = ""
        message = detail
        try:
            payload = json.loads(detail)
            message = payload.get("error", {}).get("message", detail)
            errors = payload.get("error", {}).get("errors", [])
            if errors:
                reason = errors[0].get("reason", "")
        except Exception:
            pass
        status = getattr(error.resp, "status", None)
        if reason in {"accessNotConfigured", "serviceDisabled"}:
            return {
                "ok": False,
                "status": "api_not_enabled",
                "message": "当前 Google Cloud 项目尚未开启 YouTube Data API v3，请先在控制台启用。",
                "detail": message,
            }
        if reason in {"insufficientPermissions", "forbidden"}:
            return {
                "ok": False,
                "status": "reauthorization_required",
                "message": "当前 Google 令牌权限不足，请重新生成授权链接并允许 YouTube 权限。",
                "detail": message,
            }
        if reason in {"quotaExceeded", "dailyLimitExceeded"}:
            return {
                "ok": False,
                "status": "quota_exceeded",
                "message": "YouTube Data API v3 已开启，但当前项目配额不足。",
                "detail": message,
            }
        return {
            "ok": False,
            "status": f"http_{status or 'error'}",
            "message": "YouTube Data API v3 检测失败。",
            "detail": message,
        }
