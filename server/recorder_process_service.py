from __future__ import annotations

import configparser
import os
import signal
import subprocess
import sys
from pathlib import Path

from .db import PROJECT_ROOT
from .models import VIDEO_SUFFIXES
from .repository import Repository


class RecorderProcessService:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository
        self.processes: dict[int, dict] = {}
        self.runtime_root = PROJECT_ROOT / "config" / "admin_runtime"
        self.output_root = PROJECT_ROOT / "downloads" / "admin_jobs"

    def start_job(self, job_id: int, room_id: int) -> None:
        current = self.processes.get(job_id)
        if current and current["process"].poll() is None:
            return
        room = self.repository.get_row("rooms", room_id)
        if not room:
            raise RuntimeError(f"Room not found: {room_id}")
        output_dir = self.output_root / f"job_{job_id}"
        url_config = self._write_job_url_config(job_id, room)
        config_file = self._write_job_config(job_id, output_dir)
        env = os.environ.copy()
        env["DOUYIN_RECORDER_CONFIG_FILE"] = str(config_file)
        env["DOUYIN_RECORDER_URL_CONFIG_FILE"] = str(url_config)
        env["DOUYIN_RECORDER_BACKUP_DIR"] = str(self.runtime_root / "backup" / f"job_{job_id}")
        process = subprocess.Popen(
            [sys.executable, str(PROJECT_ROOT / "main.py")],
            cwd=str(PROJECT_ROOT),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=self._creationflags(),
        )
        self.processes[job_id] = {"process": process, "room_id": room_id, "output_dir": output_dir}
        self.repository.mark_recording_job_status(job_id, "recording", worker_id=f"pid:{process.pid}")
        self.repository.add_event(
            "recording_process_started",
            f"Recording process started with pid {process.pid}",
            job_id=job_id,
        )

    def stop_job(self, job_id: int) -> None:
        state = self.processes.pop(job_id, None)
        if state:
            process = state["process"]
            if process.poll() is None:
                self._terminate(process)
                self.repository.add_event(
                    "recording_process_stopped",
                    f"Recording process stopped for job {job_id}",
                    job_id=job_id,
                )
            self._register_output_files(job_id, state["room_id"], state["output_dir"])
        self.repository.mark_recording_job_status(job_id, "interrupted")

    def runtime_status(self) -> list[dict]:
        result = []
        for job_id, state in self.processes.items():
            process = state["process"]
            result.append({
                "job_id": job_id,
                "pid": process.pid,
                "return_code": process.poll(),
                "output_dir": str(state["output_dir"]),
            })
        return result

    def reap_finished(self) -> None:
        for job_id, state in list(self.processes.items()):
            process = state["process"]
            return_code = process.poll()
            if return_code is None:
                continue
            self._register_output_files(job_id, state["room_id"], state["output_dir"])
            status = "completed" if return_code == 0 else "failed"
            self.repository.mark_recording_job_status(job_id, status)
            self.repository.add_event(
                "recording_process_finished",
                f"Recording process exited with code {return_code}",
                job_id=job_id,
            )
            self.processes.pop(job_id, None)

    def _write_job_url_config(self, job_id: int, room: dict) -> Path:
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        name = str(room.get("name") or "").strip()
        quality = str(room.get("quality") or "原画").strip() or "原画"
        url = str(room["url"]).strip()
        line = f"{quality},{url}"
        if name:
            line += f",主播: {name}"
        path = self.runtime_root / f"job_{job_id}_URL_config.ini"
        path.write_text(line + "\n", encoding="utf-8-sig")
        return path

    def _write_job_config(self, job_id: int, output_dir: Path) -> Path:
        source = PROJECT_ROOT / "config" / "config.ini"
        target = self.runtime_root / f"job_{job_id}_config.ini"
        output_dir.mkdir(parents=True, exist_ok=True)
        parser = configparser.RawConfigParser()
        parser.optionxform = str
        if source.exists():
            parser.read(source, encoding="utf-8-sig")
        if not parser.has_section("录制设置"):
            parser.add_section("录制设置")
        parser.set("录制设置", "直播保存路径(不填则默认)", str(output_dir))
        if not parser.has_section("YouTube上传"):
            parser.add_section("YouTube上传")
        parser.set("YouTube上传", "是否启用YouTube上传(是/否)", "否")
        parser.set("YouTube上传", "是否启用下载目录实时监控(是/否)", "否")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8-sig") as file:
            parser.write(file)
        return target

    def _register_output_files(self, job_id: int, room_id: int, output_dir: Path) -> None:
        if not output_dir.exists():
            return
        for path in output_dir.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in VIDEO_SUFFIXES:
                continue
            if path.stat().st_size <= 0:
                continue
            self.repository.register_file(path, source="recording", job_id=job_id, room_id=room_id)

    @staticmethod
    def _creationflags() -> int:
        return subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0

    @staticmethod
    def _terminate(process: subprocess.Popen) -> None:
        if os.name == "nt":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            process.terminate()
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
