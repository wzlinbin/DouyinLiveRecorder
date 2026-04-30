from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .db import Database, row_to_dict
from .models import ACTIVE_JOB_STATES
from .path_service import file_identity, public_path


class Repository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list_rows(self, table: str, order_by: str = "id DESC", limit: int | None = None,
                  where: str = "", params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        sql = f"SELECT * FROM {table}"
        if where:
            sql += f" WHERE {where}"
        sql += f" ORDER BY {order_by}"
        if limit:
            sql += " LIMIT ?"
            params = (*params, limit)
        with self.database.connection() as connection:
            return [row_to_dict(row) for row in connection.execute(sql, params).fetchall()]

    def count_rows(self, table: str, where: str = "", params: tuple[Any, ...] = ()) -> int:
        sql = f"SELECT COUNT(*) AS total FROM {table}"
        if where:
            sql += f" WHERE {where}"
        with self.database.connection() as connection:
            row = connection.execute(sql, params).fetchone()
            return int(row["total"]) if row else 0

    def get_row(self, table: str, row_id: int) -> dict[str, Any] | None:
        with self.database.connection() as connection:
            row = connection.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,)).fetchone()
            return row_to_dict(row) if row else None

    def list_rooms(self, include_deleted: bool = False) -> list[dict[str, Any]]:
        where = "" if include_deleted else "deleted_at IS NULL"
        return self.list_rows("rooms", where=where, order_by="id ASC")

    def add_event(self, event_type: str, message: str, level: str = "info", **ids: int | None) -> None:
        allowed_ids = {key: value for key, value in ids.items() if key in {
            "job_id", "file_id", "upload_id", "douyin_task_id"
        }}
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO events(event_type, message, level, job_id, file_id, upload_id, douyin_task_id)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_type,
                    message,
                    level,
                    allowed_ids.get("job_id"),
                    allowed_ids.get("file_id"),
                    allowed_ids.get("upload_id"),
                    allowed_ids.get("douyin_task_id"),
                ),
            )

    def upsert_setting(self, key: str, value: Any, category: str = "general") -> None:
        encoded = json.dumps(value, ensure_ascii=False)
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO settings(key, value, category, updated_at)
                VALUES(?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                    category = excluded.category, updated_at = CURRENT_TIMESTAMP
                """,
                (key, encoded, category),
            )

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self.database.connection() as connection:
            row = connection.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if not row:
            return default
        try:
            return json.loads(row["value"])
        except json.JSONDecodeError:
            return default

    def create_room(self, url: str, name: str = "", platform: str = "unknown", quality: str = "原画",
                    enabled: bool = True, source: str = "api") -> dict[str, Any]:
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO rooms(url, name, platform, quality, enabled, source, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(url) DO UPDATE SET name = CASE WHEN excluded.name != '' THEN excluded.name ELSE rooms.name END,
                    platform = excluded.platform, quality = excluded.quality, enabled = excluded.enabled,
                    source = excluded.source, deleted_at = NULL, updated_at = CURRENT_TIMESTAMP
                """,
                (url, name, platform, quality, int(enabled), source),
            )
            row = connection.execute("SELECT * FROM rooms WHERE url = ?", (url,)).fetchone()
            return row_to_dict(row)

    def update_room(self, room_id: int, updates: dict[str, Any]) -> dict[str, Any] | None:
        fields = {key: value for key, value in updates.items() if key in {"url", "name", "platform", "quality", "enabled"}}
        if not fields:
            return self.get_row("rooms", room_id)
        if "url" in fields:
            fields["url"] = str(fields["url"]).strip()
            if not fields["url"]:
                raise ValueError("Room URL cannot be empty")
        if "enabled" in fields:
            fields["enabled"] = int(bool(fields["enabled"]))
        assignments = ", ".join(f"{key} = ?" for key in fields)
        values = tuple(fields.values())
        with self.database.transaction() as connection:
            if "url" in fields:
                existing = connection.execute(
                    "SELECT id FROM rooms WHERE url = ? AND id != ? AND deleted_at IS NULL",
                    (fields["url"], room_id),
                ).fetchone()
                if existing:
                    raise ValueError("Room URL already exists")
            connection.execute(
                f"UPDATE rooms SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND deleted_at IS NULL",
                (*values, room_id),
            )
            row = connection.execute("SELECT * FROM rooms WHERE id = ? AND deleted_at IS NULL", (room_id,)).fetchone()
            return row_to_dict(row) if row else None

    def delete_room(self, room_id: int) -> dict[str, Any] | None:
        with self.database.transaction() as connection:
            row = connection.execute("SELECT * FROM rooms WHERE id = ? AND deleted_at IS NULL", (room_id,)).fetchone()
            if not row:
                return None
            active = connection.execute(
                "SELECT id FROM recording_jobs WHERE room_id = ? AND status IN ('pending','probing','recording','stopping') LIMIT 1",
                (room_id,),
            ).fetchone()
            if active:
                raise RuntimeError("Room has an active recording job")
            deleted_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            archived_url = f"{row['url']}#deleted-{room_id}-{deleted_at}"
            connection.execute(
                """
                UPDATE rooms
                SET enabled = 0, url = ?, deleted_at = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (archived_url, deleted_at, room_id),
            )
            updated = connection.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
            return row_to_dict(updated) if updated else None

    def active_job_for_room(self, room_id: int) -> dict[str, Any] | None:
        placeholders = ",".join("?" for _ in ACTIVE_JOB_STATES)
        with self.database.connection() as connection:
            row = connection.execute(
                f"SELECT * FROM recording_jobs WHERE room_id = ? AND status IN ({placeholders}) ORDER BY id DESC LIMIT 1",
                (room_id, *ACTIVE_JOB_STATES),
            ).fetchone()
            return row_to_dict(row) if row else None

    def create_recording_job(self, room: dict[str, Any]) -> dict[str, Any]:
        snapshot = json.dumps({"room": room}, ensure_ascii=False)
        with self.database.transaction() as connection:
            existing = connection.execute(
                "SELECT * FROM recording_jobs WHERE room_id = ? AND status IN ('pending','probing','recording','stopping') ORDER BY id DESC LIMIT 1",
                (room["id"],),
            ).fetchone()
            if existing:
                return row_to_dict(existing)
            connection.execute(
                """
                INSERT INTO recording_jobs(room_id, status, config_snapshot, created_at, updated_at)
                VALUES(?, 'pending', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (room["id"], snapshot),
            )
            job = connection.execute("SELECT * FROM recording_jobs WHERE id = last_insert_rowid()").fetchone()
            connection.execute(
                "INSERT INTO task_commands(command_type, room_id, job_id, payload) VALUES('start', ?, ?, ?)",
                (room["id"], job["id"], snapshot),
            )
            return row_to_dict(job)

    def stop_recording_job(self, room_id: int) -> dict[str, Any] | None:
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM recording_jobs WHERE room_id = ? AND status IN ('pending','probing','recording','stopping') ORDER BY id DESC LIMIT 1",
                (room_id,),
            ).fetchone()
            if not row:
                return None
            if row["status"] != "stopping":
                connection.execute(
                    "UPDATE recording_jobs SET status = 'stopping', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (row["id"],),
                )
                connection.execute(
                    "INSERT INTO task_commands(command_type, room_id, job_id, payload) VALUES('stop', ?, ?, '{}')",
                    (room_id, row["id"]),
                )
            updated = connection.execute("SELECT * FROM recording_jobs WHERE id = ?", (row["id"],)).fetchone()
            return row_to_dict(updated)

    def register_file(self, path: str | Path, source: str = "download_watch", job_id: int | None = None,
                      room_id: int | None = None, downloaded_item_id: int | None = None,
                      create_upload: bool = True) -> dict[str, Any]:
        file_path = Path(path).resolve()
        identity = file_identity(file_path)
        stat = file_path.stat()
        suffix = file_path.suffix.lstrip(".").lower()
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO recorded_files(job_id, room_id, local_path, file_identity, size_bytes, format, source, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(file_identity) DO UPDATE SET size_bytes = excluded.size_bytes,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (job_id, room_id, public_path(file_path), identity, stat.st_size, suffix, source),
            )
            recorded = connection.execute(
                "SELECT * FROM recorded_files WHERE file_identity = ?", (identity,)
            ).fetchone()
            if downloaded_item_id:
                connection.execute(
                    "UPDATE douyin_downloaded_items SET recorded_file_id = ?, file_identity = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (recorded["id"], identity, downloaded_item_id),
                )
            if create_upload:
                connection.execute(
                    """
                    INSERT INTO upload_records(recorded_file_id, downloaded_item_id, file_identity, local_path, title)
                    VALUES(?, ?, ?, ?, ?)
                    ON CONFLICT(file_identity) DO NOTHING
                    """,
                    (recorded["id"], downloaded_item_id, identity, public_path(file_path), file_path.stem),
                )
            return row_to_dict(recorded)

    def update_recorded_file_path(self, file_id: int, path: str | Path) -> dict[str, Any] | None:
        file_path = Path(path).resolve()
        identity = file_identity(file_path)
        stat = file_path.stat()
        suffix = file_path.suffix.lstrip(".").lower()
        with self.database.transaction() as connection:
            existing = connection.execute(
                "SELECT id FROM recorded_files WHERE file_identity = ? AND id != ?",
                (identity, file_id),
            ).fetchone()
            if existing:
                raise ValueError("A recorded file with the same identity already exists")
            connection.execute(
                """
                UPDATE recorded_files
                SET local_path = ?, file_identity = ?, size_bytes = ?, format = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (public_path(file_path), identity, stat.st_size, suffix, file_id),
            )
            connection.execute(
                """
                UPDATE upload_records
                SET local_path = ?, file_identity = ?, title = ?, updated_at = CURRENT_TIMESTAMP
                WHERE recorded_file_id = ?
                """,
                (public_path(file_path), identity, file_path.stem, file_id),
            )
            connection.execute(
                """
                UPDATE douyin_downloaded_items
                SET local_path = CASE WHEN local_path != '' THEN ? ELSE local_path END,
                    file_identity = CASE WHEN file_identity != '' THEN ? ELSE file_identity END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE recorded_file_id = ?
                """,
                (public_path(file_path), identity, file_id),
            )
            row = connection.execute("SELECT * FROM recorded_files WHERE id = ?", (file_id,)).fetchone()
            return row_to_dict(row) if row else None

    def delete_recorded_file(self, file_id: int) -> bool:
        with self.database.transaction() as connection:
            row = connection.execute("SELECT id FROM recorded_files WHERE id = ?", (file_id,)).fetchone()
            if not row:
                return False
            connection.execute("DELETE FROM upload_records WHERE recorded_file_id = ?", (file_id,))
            connection.execute(
                """
                UPDATE douyin_downloaded_items
                SET recorded_file_id = NULL, file_identity = '', local_path = '', updated_at = CURRENT_TIMESTAMP
                WHERE recorded_file_id = ?
                """,
                (file_id,),
            )
            connection.execute("UPDATE download_watch_records SET recorded_file_id = NULL WHERE recorded_file_id = ?", (file_id,))
            connection.execute("DELETE FROM recorded_files WHERE id = ?", (file_id,))
            return True

    def retry_upload(self, upload_id: int) -> dict[str, Any] | None:
        with self.database.transaction() as connection:
            row = connection.execute("SELECT * FROM upload_records WHERE id = ?", (upload_id,)).fetchone()
            if not row:
                return None
            if row["status"] == "failed":
                connection.execute(
                    """
                    UPDATE upload_records SET status = 'pending', retry_count = retry_count + 1,
                        failure_reason = '', updated_at = CURRENT_TIMESTAMP WHERE id = ?
                    """,
                    (upload_id,),
                )
                connection.execute(
                    "INSERT INTO task_commands(command_type, upload_id, payload) VALUES('retry_upload', ?, '{}')",
                    (upload_id,),
                )
            updated = connection.execute("SELECT * FROM upload_records WHERE id = ?", (upload_id,)).fetchone()
            return row_to_dict(updated)

    def upsert_youtube_metric(self, youtube_video_id: str, metric_date: str, view_count: int,
                              like_count: int, comment_count: int) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO youtube_metrics(youtube_video_id, metric_date, view_count, like_count, comment_count, fetched_at)
                VALUES(?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(youtube_video_id, metric_date) DO UPDATE SET view_count = excluded.view_count,
                    like_count = excluded.like_count, comment_count = excluded.comment_count,
                    fetched_at = CURRENT_TIMESTAMP
                """,
                (youtube_video_id, metric_date, view_count, like_count, comment_count),
            )

    def mark_upload_status(self, upload_id: int, status: str, youtube_video_id: str = "") -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE upload_records SET status = ?, youtube_video_id = CASE WHEN ? != '' THEN ? ELSE youtube_video_id END,
                    failure_reason = '', updated_at = CURRENT_TIMESTAMP WHERE id = ?
                """,
                (status, youtube_video_id, youtube_video_id, upload_id),
            )

    def mark_upload_failed(self, upload_id: int, reason: str) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE upload_records SET status = 'failed', failure_reason = ?,
                    retry_count = retry_count + 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?
                """,
                (reason[:1000], upload_id),
            )

    def claim_pending_commands(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.database.transaction() as connection:
            rows = connection.execute(
                """
                SELECT * FROM task_commands WHERE status = 'pending'
                ORDER BY id ASC LIMIT ?
                """,
                (limit,),
            ).fetchall()
            ids = [row["id"] for row in rows]
            if ids:
                placeholders = ",".join("?" for _ in ids)
                connection.execute(
                    f"UPDATE task_commands SET status = 'processing' WHERE id IN ({placeholders})",
                    tuple(ids),
                )
            return [row_to_dict(row) for row in rows]

    def finish_command(self, command_id: int, status: str, message: str = "") -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE task_commands SET status = ?, result_message = ?, processed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (status, message[:1000], command_id),
            )

    def mark_recording_job_status(self, job_id: int, status: str, worker_id: str = "") -> None:
        fields = ["status = ?", "updated_at = CURRENT_TIMESTAMP"]
        values: list[Any] = [status]
        if status in {"probing", "recording"}:
            fields.append("started_at = COALESCE(started_at, CURRENT_TIMESTAMP)")
        if status in {"completed", "interrupted", "failed"}:
            fields.append("ended_at = COALESCE(ended_at, CURRENT_TIMESTAMP)")
        if worker_id:
            fields.append("worker_id = ?")
            values.append(worker_id)
        values.append(job_id)
        with self.database.transaction() as connection:
            connection.execute(f"UPDATE recording_jobs SET {', '.join(fields)} WHERE id = ?", tuple(values))
