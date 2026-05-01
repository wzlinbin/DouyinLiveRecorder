from __future__ import annotations

import asyncio

from .recorder_process_service import RecorderProcessService
from .repository import Repository


class CommandWorkerService:
    def __init__(self, repository: Repository, recorder_process_service: RecorderProcessService) -> None:
        self.repository = repository
        self.recorder_process_service = recorder_process_service

    async def run_loop(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            try:
                await asyncio.to_thread(self.recorder_process_service.reap_finished)
                await asyncio.to_thread(self.process_pending_commands)
            except Exception as error:
                self.repository.add_event("command_worker_error", str(error), level="error")
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=2)
            except asyncio.TimeoutError:
                pass

    def process_pending_commands(self) -> int:
        commands = self.repository.claim_pending_commands(limit=20)
        processed = 0
        for command in commands:
            try:
                self._process_command(command)
            except Exception as error:
                self.repository.finish_command(command["id"], "failed", str(error))
                job_id = command.get("job_id")
                if job_id:
                    self.repository.mark_recording_job_status(job_id, "failed", error_message=str(error))
            processed += 1
        return processed

    def _process_command(self, command: dict) -> None:
        command_type = command["command_type"]
        if command_type == "start":
            self._process_start(command)
            return
        if command_type == "stop":
            self._process_stop(command)
            return
        if command_type == "retry_upload":
            self.repository.finish_command(command["id"], "completed", "Upload retry queued")
            return
        self.repository.finish_command(command["id"], "failed", f"Unknown command: {command_type}")

    def _process_start(self, command: dict) -> None:
        job_id = command.get("job_id")
        room_id = command.get("room_id")
        if not job_id or not room_id:
            self.repository.finish_command(command["id"], "failed", "Missing room_id or job_id")
            return
        self.repository.mark_recording_job_status(job_id, "probing", worker_id="admin-command-worker")
        self.recorder_process_service.start_job(job_id, room_id)
        self.repository.finish_command(command["id"], "completed", "Recording process started")

    def _process_stop(self, command: dict) -> None:
        job_id = command.get("job_id")
        if not job_id:
            self.repository.finish_command(command["id"], "failed", "Missing job_id")
            return
        self.recorder_process_service.stop_job(job_id)
        self.repository.finish_command(command["id"], "completed", "Recording process stopped")
