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
            raise RuntimeError(f"直播间不存在：{room_id}")
        output_dir = self.output_root / f"job_{job_id}"
        url_config = self._write_job_url_config(job_id, room)
        config_file = self._write_job_config(job_id, output_dir)
        log_path = self.runtime_root / f"job_{job_id}.log"
        log_file = log_path.open("ab")
        env = os.environ.copy()
        env["DOUYIN_RECORDER_CONFIG_FILE"] = str(config_file)
        env["DOUYIN_RECORDER_URL_CONFIG_FILE"] = str(url_config)
        env["DOUYIN_RECORDER_BACKUP_DIR"] = str(self.runtime_root / "backup" / f"job_{job_id}")
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        try:
            process = subprocess.Popen(
                [sys.executable, str(PROJECT_ROOT / "main.py")],
                cwd=str(PROJECT_ROOT),
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                creationflags=self._creationflags(),
                start_new_session=os.name != "nt",
            )
        except Exception:
            log_file.close()
            raise
        self.processes[job_id] = {
            "process": process,
            "room_id": room_id,
            "output_dir": output_dir,
            "log_path": log_path,
            "log_file": log_file,
        }
        self.repository.mark_recording_job_status(job_id, "recording", worker_id=f"pid:{process.pid}")
        self.repository.add_event(
            "recording_process_started",
            f"录制进程已启动，PID {process.pid}",
            job_id=job_id,
        )

    def stop_job(self, job_id: int) -> None:
        state = self.processes.pop(job_id, None)
        files_registered = 0
        if state:
            process = state["process"]
            if process.poll() is None:
                self._terminate(process)
                self.repository.add_event(
                    "recording_process_stopped",
                    f"录制任务 #{job_id} 的进程已停止",
                    job_id=job_id,
                )
            self._close_log_file(state)
            files_registered = self._register_output_files(job_id, state["room_id"], state["output_dir"])
        status = "completed" if files_registered > 0 else "interrupted"
        error_message = "" if files_registered > 0 else "手动停止录制时尚未登记任何输出文件"
        self.repository.mark_recording_job_status(job_id, status, error_message=error_message)

    def runtime_status(self) -> list[dict]:
        result = []
        for job_id, state in self.processes.items():
            process = state["process"]
            result.append({
                "job_id": job_id,
                "pid": process.pid,
                "return_code": process.poll(),
                "output_dir": str(state["output_dir"]),
                "log_path": str(state.get("log_path", "")),
            })
        return result

    def reap_finished(self) -> None:
        for job_id, state in list(self.processes.items()):
            process = state["process"]
            return_code = process.poll()
            if return_code is None:
                continue
            self._close_log_file(state)
            self._register_output_files(job_id, state["room_id"], state["output_dir"])
            status = "completed" if return_code == 0 else "failed"
            error_message = "" if return_code == 0 else self._failure_message(return_code, state.get("log_path"))
            self.repository.mark_recording_job_status(job_id, status, error_message=error_message)
            self.repository.add_event(
                "recording_process_finished",
                f"录制进程退出，退出码 {return_code}",
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
        self._set_option_case_insensitive(parser, "YouTube上传", "是否启用YouTube上传(是/否)", "否")
        self._set_option_case_insensitive(parser, "YouTube上传", "是否启用下载目录实时监控(是/否)", "否")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8-sig") as file:
            parser.write(file)
        return target

    def _register_output_files(self, job_id: int, room_id: int, output_dir: Path) -> int:
        if not output_dir.exists():
            return 0
        registered = 0
        for path in output_dir.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in VIDEO_SUFFIXES:
                continue
            if path.stat().st_size <= 0:
                continue
            self.repository.register_file(path, source="recording", job_id=job_id, room_id=room_id)
            registered += 1
        return registered

    @staticmethod
    def _close_log_file(state: dict) -> None:
        log_file = state.get("log_file")
        if log_file and not log_file.closed:
            log_file.close()

    @staticmethod
    def _set_option_case_insensitive(
        parser: configparser.RawConfigParser,
        section: str,
        option: str,
        value: str,
    ) -> None:
        normalized = option.lower()
        matching_options = [existing for existing in parser.options(section) if existing.lower() == normalized]
        target = matching_options[0] if matching_options else option
        for duplicate in matching_options[1:]:
            parser.remove_option(section, duplicate)
        parser.set(section, target, value)

    @staticmethod
    def _failure_message(return_code: int, log_path: Path | None) -> str:
        message = f"录制进程退出，退出码 {return_code}"
        if not log_path or not log_path.exists():
            return message
        try:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return message
        tail = "\n".join(line for line in lines[-20:] if line.strip())
        return f"{message}\nLog: {log_path}\n{tail}" if tail else f"{message}\nLog: {log_path}"

    @staticmethod
    def _creationflags() -> int:
        return subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0

    @staticmethod
    def _terminate(process: subprocess.Popen) -> None:
        if os.name == "nt":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(process.pid, signal.SIGINT)
        try:
            process.wait(timeout=60)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                process.kill()
            else:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)
