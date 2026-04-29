from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse

from .analytics_service import AnalyticsService
from .command_worker_service import CommandWorkerService
from .config_service import ConfigService, guess_platform
from .db import db
from .douyin_collection_service import DouyinCollectionService
from .download_watch_service import DownloadWatchService
from .recorder_process_service import RecorderProcessService
from .recording_service import RecordingService
from .repository import Repository
from .schemas import ConfigSectionPatch, DouyinSingleRequest, DouyinUserRequest, DownloadWatchSettingsPatch, RoomCreate, RoomPatch
from .transcode_service import TranscodeService
from .upload_service import UploadService

repository = Repository(db)
config_service = ConfigService(repository)
recording_service = RecordingService(repository)
upload_service = UploadService(repository)
transcode_service = TranscodeService(repository)
download_watch_service = DownloadWatchService(repository, transcode_service)
douyin_service = DouyinCollectionService(repository)
analytics_service = AnalyticsService(repository)
recorder_process_service = RecorderProcessService(repository)
command_worker_service = CommandWorkerService(repository, recorder_process_service)


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.initialize()
    imported = config_service.import_once()
    if imported:
        repository.add_event("startup", "Initial ini import completed")
    stop_event = asyncio.Event()
    watch_task = asyncio.create_task(download_watch_service.run_loop(stop_event))
    upload_task = asyncio.create_task(upload_service.run_loop(stop_event))
    command_task = asyncio.create_task(command_worker_service.run_loop(stop_event))
    try:
        yield
    finally:
        stop_event.set()
        for task in (watch_task, upload_task, command_task):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


app = FastAPI(title="DouyinLiveRecorder Admin", version="0.1.0", lifespan=lifespan)


def require_admin_token(x_admin_token: str | None = Header(default=None)) -> None:
    expected = os.environ.get("ADMIN_API_TOKEN")
    if not expected:
        raise HTTPException(status_code=503, detail="ADMIN_API_TOKEN is not configured")
    if x_admin_token != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DouyinLiveRecorder Admin</title>
  <style>
    body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;margin:24px;background:#f7f7fb;color:#1f2937}
    h1{margin-bottom:4px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px;margin:20px 0}
    .card{background:white;border:1px solid #e5e7eb;border-radius:12px;padding:16px;box-shadow:0 1px 2px #0001}
    button{border:0;border-radius:8px;background:#2563eb;color:white;padding:8px 12px;cursor:pointer}pre{white-space:pre-wrap;max-height:320px;overflow:auto;background:#111827;color:#e5e7eb;padding:12px;border-radius:10px}.muted{color:#6b7280}
  </style>
</head>
<body>
  <h1>DouyinLiveRecorder Admin</h1>
  <p class="muted">本机优先后台。启动命令：<code>python -m server</code>，默认监听 <code>127.0.0.1:8000</code>。</p>
  <div class="grid" id="cards"></div>
  <pre id="output">点击模块查看实时 JSON 摘要。</pre>
  <script>
    const endpoints = [
      ['健康检查', '/health'], ['配置', '/api/config'], ['直播间', '/api/rooms'], ['录制任务', '/api/jobs'],
      ['运行进程', '/api/recording-runtime'], ['任务命令', '/api/task-commands'], ['录制文件', '/api/files'],
      ['上传记录', '/api/uploads'], ['下载监控', '/api/download-watch'], ['Douyin任务', '/api/douyin/tasks'],
      ['YouTube指标', '/api/metrics/videos'], ['最近事件', '/api/events/recent']
    ];
    const cards = document.getElementById('cards');
    const output = document.getElementById('output');
    for (const [title, url] of endpoints) {
      const card = document.createElement('div');
      card.className = 'card';
      card.innerHTML = `<h3>${title}</h3><p class="muted">${url}</p><button>查看</button>`;
      card.querySelector('button').onclick = async () => {
        const response = await fetch(url);
        output.textContent = JSON.stringify(await response.json(), null, 2);
      };
      cards.appendChild(card);
    }
  </script>
</body>
</html>
"""


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok"}


@app.get("/api/config")
def list_config() -> dict[str, list[dict]]:
    return {"data": config_service.list_settings()}


@app.get("/api/config/{section}")
def get_config_section(section: str) -> dict:
    return config_service.get_section(section)


@app.patch("/api/config/{section}", dependencies=[Depends(require_admin_token)])
def update_config_section(section: str, request: ConfigSectionPatch) -> dict:
    return config_service.update_section(section, request.values)


@app.post("/api/config/import", dependencies=[Depends(require_admin_token)])
def import_config() -> dict[str, int]:
    return config_service.import_ini()


@app.post("/api/config/export", dependencies=[Depends(require_admin_token)])
def export_config() -> dict[str, int]:
    return config_service.export_ini()


@app.get("/api/rooms")
def list_rooms() -> dict[str, list[dict]]:
    return {"data": repository.list_rows("rooms", order_by="id ASC")}


@app.post("/api/rooms", dependencies=[Depends(require_admin_token)])
def create_room(request: RoomCreate) -> dict:
    platform = request.platform if request.platform != "unknown" else guess_platform(request.url)
    return repository.create_room(request.url, request.name, platform, request.quality, request.enabled)


@app.patch("/api/rooms/{room_id}", dependencies=[Depends(require_admin_token)])
def update_room(room_id: int, request: RoomPatch) -> dict:
    data = request.model_dump(exclude_unset=True)
    if data.get("url") and not data.get("platform"):
        data["platform"] = guess_platform(data["url"])
    room = repository.update_room(room_id, data)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    return room


@app.post("/api/rooms/{room_id}/start", dependencies=[Depends(require_admin_token)])
def start_room(room_id: int) -> dict:
    return recording_service.start_room(room_id)


@app.post("/api/rooms/{room_id}/stop", dependencies=[Depends(require_admin_token)])
def stop_room(room_id: int) -> dict:
    return recording_service.stop_room(room_id)


@app.get("/api/jobs")
def list_jobs(status: str | None = None) -> dict[str, list[dict]]:
    if status:
        return {"data": repository.list_rows("recording_jobs", where="status = ?", params=(status,))}
    return {"data": repository.list_rows("recording_jobs")}


@app.get("/api/task-commands")
def list_task_commands(status: str | None = None) -> dict[str, list[dict]]:
    if status:
        return {"data": repository.list_rows("task_commands", where="status = ?", params=(status,))}
    return {"data": repository.list_rows("task_commands")}


@app.get("/api/recording-runtime")
def recording_runtime() -> dict[str, list[dict]]:
    return {"data": recorder_process_service.runtime_status()}


@app.get("/api/files")
def list_files(
    room_id: int | None = None,
    job_id: int | None = None,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, list[dict]]:
    clauses = []
    params: list[Any] = []
    if room_id is not None:
        clauses.append("room_id = ?")
        params.append(room_id)
    if job_id is not None:
        clauses.append("job_id = ?")
        params.append(job_id)
    if status:
        clauses.append("status = ?")
        params.append(status)
    if date_from:
        clauses.append("created_at >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("created_at <= ?")
        params.append(date_to)
    return {"data": repository.list_rows("recorded_files", where=" AND ".join(clauses), params=tuple(params))}


@app.get("/api/uploads")
def list_uploads(status: str | None = None) -> dict[str, list[dict]]:
    if status:
        return {"data": repository.list_rows("upload_records", where="status = ?", params=(status,))}
    return {"data": repository.list_rows("upload_records")}


@app.post("/api/uploads/{upload_id}/retry", dependencies=[Depends(require_admin_token)])
def retry_upload(upload_id: int) -> dict:
    return upload_service.retry(upload_id)


@app.get("/api/download-watch")
def get_download_watch() -> dict[str, Any]:
    return {
        "settings": download_watch_service.get_settings(),
        "records": repository.list_rows("download_watch_records", limit=100),
    }


@app.post("/api/download-watch/scan", dependencies=[Depends(require_admin_token)])
def scan_download_watch() -> dict[str, int]:
    return download_watch_service.scan_once()


@app.patch("/api/download-watch/settings", dependencies=[Depends(require_admin_token)])
def update_download_watch_settings(request: DownloadWatchSettingsPatch) -> dict:
    return download_watch_service.update_settings(request.model_dump(exclude_unset=True))


@app.post("/api/douyin/download", dependencies=[Depends(require_admin_token)])
async def create_douyin_download(request: DouyinSingleRequest) -> dict:
    return douyin_service.create_single_task(
        request.url, request.output_dir, request.proxy, request.request_cookie(), request.overwrite
    )


@app.post("/api/douyin/user-download", dependencies=[Depends(require_admin_token)])
async def create_douyin_user_download(request: DouyinUserRequest) -> dict:
    return douyin_service.create_user_task(
        request.url, request.output_dir, request.proxy, request.request_cookie(), request.max_items, request.overwrite
    )


@app.get("/api/douyin/tasks")
def list_douyin_tasks() -> dict[str, list[dict]]:
    return {"data": repository.list_rows("douyin_collection_tasks")}


@app.get("/api/douyin/tasks/{task_id}")
def get_douyin_task(task_id: int) -> dict[str, Any]:
    task = repository.get_row("douyin_collection_tasks", task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Douyin task not found")
    items = repository.list_rows("douyin_downloaded_items", where="task_id = ?", params=(task_id,), order_by="id ASC")
    return {"task": task, "items": items}


@app.get("/api/metrics/videos")
def list_metrics() -> dict[str, list[dict]]:
    return {"data": analytics_service.list_video_metrics()}


@app.post("/api/metrics/videos/refresh", dependencies=[Depends(require_admin_token)])
def refresh_metrics() -> dict[str, int]:
    return analytics_service.refresh_video_metrics()


@app.get("/api/events/recent")
def recent_events(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, list[dict]]:
    return {"data": repository.list_rows("events", limit=limit)}
