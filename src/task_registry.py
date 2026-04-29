from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock
from typing import Any


@dataclass
class TaskRecord:
    task_id: str
    kind: str
    input_url: str
    status: str = "queued"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    started_at: str | None = None
    finished_at: str | None = None
    progress_total: int = 0
    progress_done: int = 0
    files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "kind": self.kind,
            "input_url": self.input_url,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "progress_total": self.progress_total,
            "progress_done": self.progress_done,
            "files": self.files,
            "errors": self.errors,
        }


class TaskRegistry:
    def __init__(self) -> None:
        self._tasks: dict[str, TaskRecord] = {}
        self._lock = Lock()

    def create(self, kind: str, input_url: str) -> TaskRecord:
        task = TaskRecord(task_id=str(uuid.uuid4()), kind=kind, input_url=input_url)
        with self._lock:
            self._tasks[task.task_id] = task
        return task

    def get(self, task_id: str) -> TaskRecord | None:
        with self._lock:
            return self._tasks.get(task_id)

    def list(self) -> list[TaskRecord]:
        with self._lock:
            return list(self._tasks.values())

    def start(self, task_id: str) -> None:
        with self._lock:
            task = self._tasks[task_id]
            task.status = "running"
            task.started_at = datetime.now().isoformat(timespec="seconds")

    def complete(self, task_id: str) -> None:
        with self._lock:
            task = self._tasks[task_id]
            task.status = "completed"
            task.finished_at = datetime.now().isoformat(timespec="seconds")

    def fail(self, task_id: str, error: str) -> None:
        with self._lock:
            task = self._tasks[task_id]
            task.status = "failed"
            task.errors.append(error)
            task.finished_at = datetime.now().isoformat(timespec="seconds")

    def set_total(self, task_id: str, total: int) -> None:
        with self._lock:
            self._tasks[task_id].progress_total = total

    def add_file(self, task_id: str, file_path: str) -> None:
        with self._lock:
            task = self._tasks[task_id]
            task.files.append(file_path)
            task.progress_done += 1

    def add_error(self, task_id: str, error: str) -> None:
        with self._lock:
            self._tasks[task_id].errors.append(error)


registry = TaskRegistry()
