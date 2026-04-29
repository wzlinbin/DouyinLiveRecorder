from __future__ import annotations

from fastapi import HTTPException

from .repository import Repository


class RecordingService:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def start_room(self, room_id: int) -> dict:
        room = self.repository.get_row("rooms", room_id)
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        active_job = self.repository.active_job_for_room(room_id)
        if active_job:
            return active_job
        job = self.repository.create_recording_job(room)
        self.repository.add_event("recording_start_requested", f"Start requested for room {room_id}", job_id=job["id"])
        return job

    def stop_room(self, room_id: int) -> dict:
        room = self.repository.get_row("rooms", room_id)
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        job = self.repository.stop_recording_job(room_id)
        if job:
            self.repository.add_event("recording_stop_requested", f"Stop requested for room {room_id}", job_id=job["id"])
            return job
        return {"room_id": room_id, "status": "not_running"}
