from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import HTTPException

from src.douyin_collection import DouyinCollectionError, download_work, fetch_user_works_from_url, fetch_work_from_url
from src.douyin_config import DOUYIN_MAX_BATCH_ITEMS

from .path_service import DEFAULT_DOWNLOAD_ROOT, resolve_download_dir
from .repository import Repository


class DouyinCollectionService:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def create_single_task(self, url: str, output_dir: str | None, proxy: str | None,
                           cookie: str | None, overwrite: bool) -> dict:
        return self._create_task("single", url, 1, output_dir, proxy, cookie, overwrite)

    def create_user_task(self, url: str, output_dir: str | None, proxy: str | None,
                         cookie: str | None, max_items: int, overwrite: bool) -> dict:
        if max_items < 1 or max_items > DOUYIN_MAX_BATCH_ITEMS:
            raise HTTPException(status_code=400, detail=f"max_items must be between 1 and {DOUYIN_MAX_BATCH_ITEMS}")
        return self._create_task("user_batch", url, max_items, output_dir, proxy, cookie, overwrite)

    def _create_task(self, task_type: str, url: str, max_items: int, output_dir: str | None,
                     proxy: str | None, cookie: str | None, overwrite: bool) -> dict:
        safe_output = resolve_download_dir(output_dir or "douyin")
        with self.repository.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO douyin_collection_tasks(task_type, input_url, max_items, status)
                VALUES(?, ?, ?, 'queued')
                """,
                (task_type, url, max_items),
            )
            row = connection.execute("SELECT * FROM douyin_collection_tasks WHERE id = last_insert_rowid()").fetchone()
            task = dict(row)
        self.repository.add_event("douyin_task_created", f"Douyin {task_type} task created", douyin_task_id=task["id"])
        asyncio.create_task(self._run_task(task["id"], task_type, url, safe_output, proxy, cookie, max_items, overwrite))
        return task

    async def _run_task(self, task_id: int, task_type: str, url: str, output_dir: Path,
                        proxy: str | None, cookie: str | None, max_items: int, overwrite: bool) -> None:
        try:
            self._update_task(task_id, status="running", started=True)
            if task_type == "single":
                work = await fetch_work_from_url(url, cookies=cookie, proxy=proxy)
                self._update_task(task_id, progress_total=1)
                await self._download_one(task_id, work, output_dir, proxy, cookie, overwrite, url)
            else:
                works = await fetch_user_works_from_url(url, max_items=max_items, cookies=cookie, proxy=proxy)
                self._update_task(task_id, progress_total=len(works))
                for work in works[:max_items]:
                    try:
                        await self._download_one(task_id, work, output_dir, proxy, cookie, overwrite, url)
                    except DouyinCollectionError as error:
                        self._add_item_error(task_id, getattr(work, "aweme_id", ""), str(error))
            task = self.repository.get_row("douyin_collection_tasks", task_id)
            status = "completed"
            if task and task["progress_total"] and task["progress_done"] < task["progress_total"]:
                status = "completed_with_errors"
            self._update_task(task_id, status=status, ended=True)
            self.repository.add_event("douyin_task_completed", f"Douyin task {task_id} {status}", douyin_task_id=task_id)
        except Exception as error:
            self._update_task(task_id, status="failed", error_message=str(error), ended=True)
            self.repository.add_event("douyin_task_failed", str(error), level="error", douyin_task_id=task_id)

    async def _download_one(self, task_id: int, work, output_dir: Path, proxy: str | None,
                            cookie: str | None, overwrite: bool, source_url: str) -> None:
        item_id = self._upsert_item(task_id, work.aweme_id, work.author_name, work.desc, source_url, "downloading")
        downloaded = await download_work(work, output_dir=str(output_dir), cookies=cookie, proxy=proxy, overwrite=overwrite)
        recorded = self.repository.register_file(downloaded.path, source="douyin", downloaded_item_id=item_id)
        with self.repository.database.transaction() as connection:
            connection.execute(
                """
                UPDATE douyin_downloaded_items SET local_path = ?, file_identity = ?, status = 'downloaded',
                    recorded_file_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?
                """,
                (downloaded.path, recorded["file_identity"], recorded["id"], item_id),
            )
            connection.execute(
                """
                UPDATE douyin_collection_tasks SET progress_done = progress_done + 1,
                    updated_at = CURRENT_TIMESTAMP WHERE id = ?
                """,
                (task_id,),
            )
        self.repository.add_event("douyin_item_downloaded", f"Downloaded Douyin item {work.aweme_id}",
                                  file_id=recorded["id"], douyin_task_id=task_id)

    def _upsert_item(self, task_id: int, aweme_id: str, author: str, description: str, source_url: str, status: str) -> int:
        with self.repository.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO douyin_downloaded_items(task_id, aweme_id, author, description, source_url, status)
                VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id, aweme_id) DO UPDATE SET status = excluded.status,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (task_id, aweme_id, author, description, source_url, status),
            )
            row = connection.execute(
                "SELECT id FROM douyin_downloaded_items WHERE task_id = ? AND aweme_id = ?",
                (task_id, aweme_id),
            ).fetchone()
            return int(row["id"])

    def _add_item_error(self, task_id: int, aweme_id: str, error: str) -> None:
        with self.repository.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO douyin_downloaded_items(task_id, aweme_id, status, error_message)
                VALUES(?, ?, 'failed', ?)
                ON CONFLICT(task_id, aweme_id) DO UPDATE SET status = 'failed', error_message = excluded.error_message,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (task_id, aweme_id or "unknown", error),
            )
            connection.execute(
                """
                UPDATE douyin_collection_tasks SET progress_done = progress_done + 1,
                    updated_at = CURRENT_TIMESTAMP WHERE id = ?
                """,
                (task_id,),
            )

    def _update_task(self, task_id: int, status: str | None = None, progress_total: int | None = None,
                     error_message: str | None = None, started: bool = False, ended: bool = False) -> None:
        fields = ["updated_at = CURRENT_TIMESTAMP"]
        values: list = []
        if status:
            fields.append("status = ?")
            values.append(status)
        if progress_total is not None:
            fields.append("progress_total = ?")
            values.append(progress_total)
        if error_message is not None:
            fields.append("error_message = ?")
            values.append(error_message)
        if started:
            fields.append("started_at = CURRENT_TIMESTAMP")
        if ended:
            fields.append("ended_at = CURRENT_TIMESTAMP")
        values.append(task_id)
        with self.repository.database.transaction() as connection:
            connection.execute(f"UPDATE douyin_collection_tasks SET {', '.join(fields)} WHERE id = ?", tuple(values))
