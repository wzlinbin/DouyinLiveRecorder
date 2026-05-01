from __future__ import annotations

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException
from server.runtime_config import admin_token
from pydantic import BaseModel, Field

from src.douyin_collection import (
    DouyinCollectionError,
    fetch_user_works_from_url,
    fetch_work_from_url,
    download_work,
)
from src.douyin_config import DOUYIN_MAX_BATCH_ITEMS
from src.task_registry import registry

app = FastAPI(title="DouyinLiveRecorder API", version="1.0.0")


def require_admin_token(x_admin_token: str | None = Header(default=None)) -> None:
    expected = admin_token()
    if not expected:
        raise HTTPException(status_code=503, detail="后台管理 Token 未配置")
    if x_admin_token != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


class SingleDownloadRequest(BaseModel):
    url: str
    output_dir: str | None = None
    cookies: str | None = None
    proxy: str | None = None
    overwrite: bool = False


class UserBatchDownloadRequest(BaseModel):
    url: str
    output_dir: str | None = None
    cookies: str | None = None
    proxy: str | None = None
    max_items: int = Field(default=50, ge=1, le=DOUYIN_MAX_BATCH_ITEMS)
    overwrite: bool = False


def run_single_task(task_id: str, request: SingleDownloadRequest) -> None:
    registry.start(task_id)
    try:
        registry.set_total(task_id, 1)
        work = _run_async(fetch_work_from_url(request.url, cookies=request.cookies, proxy=request.proxy))
        downloaded = _run_async(download_work(
            work,
            output_dir=request.output_dir,
            cookies=request.cookies,
            proxy=request.proxy,
            overwrite=request.overwrite,
        ))
        registry.add_file(task_id, downloaded.path)
        registry.complete(task_id)
    except Exception as e:
        registry.fail(task_id, str(e))


def run_user_batch_task(task_id: str, request: UserBatchDownloadRequest) -> None:
    registry.start(task_id)
    try:
        works = _run_async(fetch_user_works_from_url(
            request.url,
            max_items=request.max_items,
            cookies=request.cookies,
            proxy=request.proxy,
        ))
        registry.set_total(task_id, len(works))
        for work in works:
            try:
                downloaded = _run_async(download_work(
                    work,
                    output_dir=request.output_dir,
                    cookies=request.cookies,
                    proxy=request.proxy,
                    overwrite=request.overwrite,
                ))
                registry.add_file(task_id, downloaded.path)
            except DouyinCollectionError as e:
                registry.add_error(task_id, str(e))
        registry.complete(task_id)
    except Exception as e:
        registry.fail(task_id, str(e))


def _run_async(awaitable):
    import asyncio

    return asyncio.run(awaitable)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/douyin/download", dependencies=[Depends(require_admin_token)])
def create_douyin_download(request: SingleDownloadRequest, background_tasks: BackgroundTasks) -> dict[str, str]:
    task = registry.create("single", request.url)
    background_tasks.add_task(run_single_task, task.task_id, request)
    return {"task_id": task.task_id, "status": task.status}


@app.post("/api/douyin/user-download", dependencies=[Depends(require_admin_token)])
def create_douyin_user_download(request: UserBatchDownloadRequest, background_tasks: BackgroundTasks) -> dict[str, str]:
    task = registry.create("user_batch", request.url)
    background_tasks.add_task(run_user_batch_task, task.task_id, request)
    return {"task_id": task.task_id, "status": task.status}


@app.get("/api/tasks")
def list_tasks() -> dict[str, list[dict]]:
    return {"data": [task.to_dict() for task in registry.list()]}


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str) -> dict:
    task = registry.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task.to_dict()


@app.get("/api/files/{task_id}")
def get_task_files(task_id: str) -> dict[str, list[str]]:
    task = registry.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"files": task.files}
