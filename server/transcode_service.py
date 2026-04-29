from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from .path_service import public_path
from .repository import Repository


class TranscodeService:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def transcode_to_mp4(self, source_path: Path, delete_origin: bool = False, reencode_h264: bool = False) -> Path:
        target_path = source_path.with_suffix(".mp4")
        if target_path.exists() and target_path.stat().st_size > 0:
            return target_path
        command = self._build_command(source_path, target_path, reencode_h264)
        try:
            subprocess.check_output(command, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as error:
            message = error.output.decode("utf-8", errors="ignore") if error.output else str(error)
            self.repository.add_event("transcode_failed", message, level="error")
            raise RuntimeError(message) from error
        if not target_path.exists() or target_path.stat().st_size <= 0:
            raise RuntimeError(f"Transcode output was not created: {target_path}")
        if delete_origin and source_path.exists():
            time.sleep(1)
            os.remove(source_path)
        self.repository.add_event("transcode_completed", f"Transcoded {source_path.name} to MP4")
        return target_path

    @staticmethod
    def _build_command(source_path: Path, target_path: Path, reencode_h264: bool) -> list[str]:
        if reencode_h264:
            return [
                "ffmpeg", "-y", "-i", public_path(source_path),
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-vf", "format=yuv420p", "-c:a", "copy", "-f", "mp4", public_path(target_path),
            ]
        return [
            "ffmpeg", "-y", "-i", public_path(source_path),
            "-c:v", "copy", "-c:a", "copy", "-f", "mp4", public_path(target_path),
        ]
