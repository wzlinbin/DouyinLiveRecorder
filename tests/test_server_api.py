from __future__ import annotations

import os
import signal
import tempfile
import unittest
from uuid import uuid4
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from server.app import (
    app,
    command_worker_service,
    config_service,
    db,
    download_watch_service,
    recorder_process_service,
    repository,
    upload_service,
)
from server.recorder_process_service import PROJECT_ROOT


class FakeProcess:
    pid = 54321

    def __init__(self) -> None:
        self.stopped = False

    def poll(self):
        return None if not self.stopped else 0

    def send_signal(self, _signal) -> None:
        self.stopped = True

    def terminate(self) -> None:
        self.stopped = True

    def wait(self, timeout=None):
        self.stopped = True
        return 0

    def kill(self) -> None:
        self.stopped = True


class FailedProcess:
    pid = 98765

    def poll(self):
        return 1


class ServerApiTest(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["ADMIN_API_TOKEN"] = "test-token"
        self.temp_db_dir = tempfile.TemporaryDirectory()
        self.original_db_path = db.db_path
        self.original_runtime_root = recorder_process_service.runtime_root
        self.original_output_root = recorder_process_service.output_root
        db.db_path = Path(self.temp_db_dir.name) / "admin.db"
        recorder_process_service.runtime_root = Path(self.temp_db_dir.name) / "admin_runtime"
        recorder_process_service.output_root = Path(self.temp_db_dir.name) / "admin_jobs"
        recorder_process_service.processes.clear()
        db.initialize()
        config_service.import_ini()
        upload_service._uploader = None
        self.upload_loop_patch = patch.object(upload_service, "enqueue_pending_uploads", return_value=0)
        self.upload_loop_patch.start()

    def tearDown(self) -> None:
        self.upload_loop_patch.stop()
        upload_service._uploader = None
        for state in recorder_process_service.processes.values():
            log_file = state.get("log_file")
            if log_file and not log_file.closed:
                log_file.close()
        recorder_process_service.processes.clear()
        recorder_process_service.runtime_root = self.original_runtime_root
        recorder_process_service.output_root = self.original_output_root
        db.db_path = self.original_db_path
        self.temp_db_dir.cleanup()

    def test_admin_mutations_require_token(self) -> None:
        with TestClient(app) as client:
            response = client.patch("/api/config/Test", json={"values": {"a": "b"}})
        self.assertEqual(response.status_code, 401)

    def test_config_update_masks_sensitive_values(self) -> None:
        with TestClient(app) as client:
            response = client.patch(
                "/api/config/TestMask",
                headers={"X-Admin-Token": "test-token"},
                json={"values": {"normal": "value", "token": "secret"}},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["normal"], "value")
        self.assertEqual(response.json()["token"], {"configured": True})

    def test_config_import_keeps_youtube_secret_and_token_paths(self) -> None:
        settings = config_service.get_section("YouTube上传")
        self.assertEqual(settings["youtube客户端密钥文件路径"], "config/youtube_client_secret.json")
        self.assertEqual(settings["youtube令牌文件路径"], "config/youtube_token.json")
        self.assertNotIsInstance(settings["youtube客户端密钥文件路径"], dict)
        self.assertNotIsInstance(settings["youtube令牌文件路径"], dict)

    def test_upload_service_reads_youtube_paths_from_real_ini_import(self) -> None:
        captured = {}

        def fake_uploader(config):
            captured["config"] = config
            return object()

        upload_service._uploader = None
        with patch("server.upload_service.create_youtube_uploader", side_effect=fake_uploader):
            self.assertIsNotNone(upload_service._get_uploader())

        config = captured["config"]
        self.assertTrue(config.client_secret_file.endswith("config\\youtube_client_secret.json"))
        self.assertTrue(config.token_file.endswith("config\\youtube_token.json"))
        self.assertTrue(config.state_file.endswith("config\\youtube_upload_state.json"))
        self.assertEqual(config.privacy_status, "public")
        self.assertEqual(config.category_id, "22")

    def test_youtube_oauth_status_reads_configured_paths(self) -> None:
        client_secret = Path(self.temp_db_dir.name) / "youtube_client_secret.json"
        token_file = Path(self.temp_db_dir.name) / "youtube_token.json"
        client_secret.write_text("{}", encoding="utf-8")
        repository.upsert_setting(
            "ini.YouTube上传",
            {
                "youtube客户端密钥文件路径": str(client_secret),
                "youtube令牌文件路径": str(token_file),
            },
            "ini",
        )
        with TestClient(app) as client:
            response = client.get("/api/youtube/oauth/status")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["client_secret_exists"])
        self.assertFalse(payload["token_exists"])
        self.assertEqual(Path(payload["token_path"]), token_file.resolve())

    def test_youtube_oauth_start_requires_client_secret(self) -> None:
        missing_secret = Path(self.temp_db_dir.name) / "missing_client_secret.json"
        repository.upsert_setting(
            "ini.YouTube上传",
            {
                "youtube客户端密钥文件路径": str(missing_secret),
                "youtube令牌文件路径": str(Path(self.temp_db_dir.name) / "youtube_token.json"),
            },
            "ini",
        )
        with TestClient(app) as client:
            response = client.post(
                "/api/youtube/oauth/start",
                headers={"X-Admin-Token": "test-token"},
                json={"redirect_uri": "http://localhost"},
            )
        self.assertEqual(response.status_code, 404)

    def test_youtube_oauth_complete_writes_token_file(self) -> None:
        client_secret = Path(self.temp_db_dir.name) / "youtube_client_secret.json"
        token_file = Path(self.temp_db_dir.name) / "youtube_token.json"
        client_secret.write_text("{}", encoding="utf-8")
        repository.upsert_setting(
            "ini.YouTube上传",
            {
                "youtube客户端密钥文件路径": str(client_secret),
                "youtube令牌文件路径": str(token_file),
            },
            "ini",
        )

        class FakeCredentials:
            def to_json(self):
                return (
                    '{"token":"access-token","refresh_token":"refresh-token",'
                    '"token_uri":"https://oauth2.googleapis.com/token",'
                    '"client_id":"client-id","client_secret":"client-secret",'
                    '"scopes":["https://www.googleapis.com/auth/youtube.upload"]}'
                )

        class FakeFlow:
            fetched_code = ""
            completed_code_verifier = ""

            def __init__(self, code_verifier: str | None = None) -> None:
                self.credentials = FakeCredentials()
                self.code_verifier = code_verifier or "test-code-verifier"

            @classmethod
            def from_client_secrets_file(cls, client_secrets_file, scopes, redirect_uri=None, code_verifier=None):
                return cls(code_verifier)

            def authorization_url(self, access_type=None, include_granted_scopes=None, prompt=None, state=None):
                return f"https://accounts.google.com/o/oauth2/auth?state={state}", state

            def fetch_token(self, code):
                FakeFlow.fetched_code = code
                FakeFlow.completed_code_verifier = self.code_verifier

        with patch("server.youtube_oauth_service.InstalledAppFlow", FakeFlow):
            with TestClient(app) as client:
                start = client.post(
                    "/api/youtube/oauth/start",
                    headers={"X-Admin-Token": "test-token"},
                    json={"redirect_uri": "http://localhost"},
                )
                state = repository.get_setting("admin.youtube_oauth", {})["state"]
                response = client.post(
                    "/api/youtube/oauth/complete",
                    headers={"X-Admin-Token": "test-token"},
                    json={"code": f"http://localhost/?state={state}&code=test-code"},
                )
        self.assertEqual(start.status_code, 200)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["saved"])
        self.assertTrue(token_file.exists())
        self.assertEqual(FakeFlow.fetched_code, "test-code")
        self.assertEqual(FakeFlow.completed_code_verifier, "test-code-verifier")

    def test_youtube_data_api_check_requires_reauthorization_for_old_scope_token(self) -> None:
        client_secret = Path(self.temp_db_dir.name) / "youtube_client_secret.json"
        token_file = Path(self.temp_db_dir.name) / "youtube_token.json"
        client_secret.write_text("{}", encoding="utf-8")
        token_file.write_text(
            (
                '{"token":"access-token","refresh_token":"refresh-token",'
                '"token_uri":"https://oauth2.googleapis.com/token",'
                '"client_id":"client-id","client_secret":"client-secret",'
                '"scopes":["https://www.googleapis.com/auth/youtube.upload"]}'
            ),
            encoding="utf-8",
        )
        repository.upsert_setting(
            "ini.YouTube上传",
            {
                "youtube客户端密钥文件路径": str(client_secret),
                "youtube令牌文件路径": str(token_file),
            },
            "ini",
        )
        with TestClient(app) as client:
            response = client.post(
                "/api/youtube/data-api/check",
                headers={"X-Admin-Token": "test-token"},
            )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "reauthorization_required")

    def test_recording_worker_registers_output_file(self) -> None:
        room_slug = f"unittest-worker-{uuid4().hex}"
        with patch("server.recorder_process_service.subprocess.Popen", return_value=FakeProcess()):
            with TestClient(app) as client:
                room = client.post(
                    "/api/rooms",
                    headers={"X-Admin-Token": "test-token"},
                    json={"url": f"https://live.douyin.com/{room_slug}", "name": room_slug},
                ).json()
                job = client.post(f"/api/rooms/{room['id']}/start", headers={"X-Admin-Token": "test-token"}).json()
                command_worker_service.process_pending_commands()
                output_dir = recorder_process_service.output_root / f"job_{job['id']}"
                output_dir.mkdir(parents=True, exist_ok=True)
                (output_dir / "fake_record.mp4").write_bytes(b"fake-video")
                client.post(f"/api/rooms/{room['id']}/stop", headers={"X-Admin-Token": "test-token"})
                command_worker_service.process_pending_commands()
                stopped_job = client.get("/api/jobs", params={"status": "completed"}).json()["data"]
                files = client.get("/api/files", params={"job_id": job["id"]}).json()["data"]
                uploads = client.get("/api/uploads").json()["data"]
        self.assertTrue(files)
        self.assertEqual(files[0]["job_id"], job["id"])
        self.assertEqual(files[0]["room_id"], room["id"])
        self.assertTrue(any(item["id"] == job["id"] for item in stopped_job))
        self.assertTrue(any(item.get("recorded_file_id") == files[0]["id"] for item in uploads))

    def test_manual_stop_without_output_stays_interrupted(self) -> None:
        room_slug = f"unittest-stop-empty-{uuid4().hex}"
        with patch("server.recorder_process_service.subprocess.Popen", return_value=FakeProcess()):
            with TestClient(app) as client:
                room = client.post(
                    "/api/rooms",
                    headers={"X-Admin-Token": "test-token"},
                    json={"url": f"https://live.douyin.com/{room_slug}", "name": room_slug},
                ).json()
                job = client.post(f"/api/rooms/{room['id']}/start", headers={"X-Admin-Token": "test-token"}).json()
                command_worker_service.process_pending_commands()
                client.post(f"/api/rooms/{room['id']}/stop", headers={"X-Admin-Token": "test-token"})
                command_worker_service.process_pending_commands()
        stopped_job = repository.get_row("recording_jobs", job["id"])
        self.assertEqual(stopped_job["status"], "interrupted")
        self.assertIn("尚未登记任何输出文件", stopped_job["error_message"])

    def test_linux_stop_sends_sigint_to_process_group(self) -> None:
        process = FakeProcess()
        with patch("server.recorder_process_service.os.name", "posix"):
            with patch("server.recorder_process_service.os.killpg", create=True) as killpg:
                recorder_process_service._terminate(process)

        killpg.assert_called_once_with(process.pid, signal.SIGINT)
        self.assertTrue(process.stopped)

    def test_recording_job_delete_removes_finished_job_only(self) -> None:
        room = repository.create_room(
            f"https://live.douyin.com/unittest-delete-job-{uuid4().hex}",
            name="delete-job",
            platform="douyin",
        )
        with repository.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO recording_jobs(room_id, status, config_snapshot, started_at, ended_at)
                VALUES(?, 'completed', '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (room["id"],),
            )
            job_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        with TestClient(app) as client:
            response = client.delete(
                f"/api/jobs/{job_id}",
                headers={"X-Admin-Token": "test-token"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(repository.get_row("recording_jobs", job_id))

    def test_recording_job_delete_rejects_active_job(self) -> None:
        room = repository.create_room(
            f"https://live.douyin.com/unittest-delete-active-job-{uuid4().hex}",
            name="delete-active-job",
            platform="douyin",
        )
        with repository.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO recording_jobs(room_id, status, config_snapshot, started_at)
                VALUES(?, 'recording', '{}', CURRENT_TIMESTAMP)
                """,
                (room["id"],),
            )
            job_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        with TestClient(app) as client:
            response = client.delete(
                f"/api/jobs/{job_id}",
                headers={"X-Admin-Token": "test-token"},
            )
        self.assertEqual(response.status_code, 409)
        self.assertIsNotNone(repository.get_row("recording_jobs", job_id))

    def test_recording_failure_stores_log_tail(self) -> None:
        room = repository.create_room(
            f"https://live.douyin.com/unittest-failed-{uuid4().hex}",
            name="failed-room",
            platform="douyin",
        )
        job = repository.create_recording_job(room)
        log_path = PROJECT_ROOT / "config" / "admin_runtime" / f"job_{job['id']}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("first line\nfatal failure\n", encoding="utf-8")
        try:
            recorder_state = {
                "process": FailedProcess(),
                "room_id": room["id"],
                "output_dir": recorder_process_service.output_root / f"job_{job['id']}",
                "log_path": log_path,
            }
            recorder_process_service.processes[job["id"]] = recorder_state
            recorder_process_service.reap_finished()
            updated = repository.get_row("recording_jobs", job["id"])
        finally:
            recorder_process_service.processes.pop(job["id"], None)
            log_path.unlink(missing_ok=True)
        self.assertEqual(updated["status"], "failed")
        self.assertIn("录制进程退出，退出码", updated["error_message"])
        self.assertIn("fatal failure", updated["error_message"])

    def test_recording_job_config_does_not_duplicate_youtube_options(self) -> None:
        from server.app import recorder_process_service

        config_path = recorder_process_service._write_job_config(
            999001,
            recorder_process_service.output_root / "job_999001",
        )
        try:
            text = config_path.read_text(encoding="utf-8-sig")
        finally:
            config_path.unlink(missing_ok=True)
        self.assertEqual(text.lower().count("是否启用youtube上传(是/否)"), 1)
        self.assertEqual(text.count("是否启用下载目录实时监控(是/否)"), 1)

    def test_metrics_refresh_empty(self) -> None:
        with TestClient(app) as client:
            response = client.post("/api/metrics/videos/refresh", headers={"X-Admin-Token": "test-token"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["requested"], 0)

    def test_dashboard_contains_summary_and_rooms(self) -> None:
        room_url = f"https://live.douyin.com/unittest-dashboard-{uuid4().hex}"
        with TestClient(app) as client:
            client.post(
                "/api/rooms",
                headers={"X-Admin-Token": "test-token"},
                json={"url": room_url, "name": "dashboard-room"},
            )
            response = client.get("/api/dashboard")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("summary", payload)
        self.assertIn("rooms", payload)
        self.assertIn("active_jobs", payload)
        self.assertIn("recent_events", payload)
        self.assertTrue(any(room["url"] == room_url for room in payload["rooms"]))

    def test_dashboard_room_summary_excludes_deleted_rooms(self) -> None:
        suffix = uuid4().hex
        baseline_total = repository.count_rows("rooms", where="deleted_at IS NULL")
        baseline_enabled = repository.count_rows("rooms", where="enabled = 1 AND deleted_at IS NULL")
        with TestClient(app) as client:
            first = client.post(
                "/api/rooms",
                headers={"X-Admin-Token": "test-token"},
                json={"url": f"https://live.douyin.com/unittest-summary-a-{suffix}", "name": "summary-a"},
            ).json()
            client.post(
                "/api/rooms",
                headers={"X-Admin-Token": "test-token"},
                json={"url": f"https://live.douyin.com/unittest-summary-b-{suffix}", "name": "summary-b", "enabled": False},
            )
            client.delete(f"/api/rooms/{first['id']}", headers={"X-Admin-Token": "test-token"})
            response = client.get("/api/dashboard")
        summary = response.json()["summary"]
        rooms = response.json()["rooms"]
        self.assertEqual(summary["rooms_total"], baseline_total + 1)
        self.assertEqual(summary["rooms_enabled"], baseline_enabled)
        self.assertEqual(len(rooms), baseline_total + 1)
        self.assertFalse(any(room["id"] == first["id"] for room in rooms))

    def test_index_page_contains_fallback_admin_sections_without_frontend_build(self) -> None:
        with patch("server.app.frontend_build_available", return_value=False):
            with TestClient(app) as client:
                response = client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("后台管理", response.text)
        self.assertIn("/api/dashboard", response.text)
        self.assertIn("直播间管理", response.text)
        self.assertIn('data-action="edit-room"', response.text)
        self.assertIn('data-action="retry-upload"', response.text)

    def test_frontend_build_served_for_root_and_routes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            frontend_index = Path(temp_dir) / "index.html"
            frontend_index.write_text(
                '<!doctype html><div id="root"></div><script type="module" src="/assets/index.js"></script>',
                encoding="utf-8",
            )
            with patch("server.app.frontend_build_available", return_value=True):
                with patch("server.app.FRONTEND_INDEX", frontend_index):
                    with TestClient(app) as client:
                        root_response = client.get("/")
                        route_response = client.get("/rooms")
                        api_response = client.get("/api/not-found")
        self.assertEqual(root_response.status_code, 200)
        self.assertIn('<div id="root"></div>', root_response.text)
        self.assertEqual(route_response.status_code, 200)
        self.assertIn('<script type="module"', route_response.text)
        self.assertEqual(api_response.status_code, 404)

    def test_room_patch_updates_name_and_quality(self) -> None:
        room_url = f"https://live.douyin.com/unittest-edit-{uuid4().hex}"
        with TestClient(app) as client:
            created = client.post(
                "/api/rooms",
                headers={"X-Admin-Token": "test-token"},
                json={"url": room_url, "name": "before", "quality": "高清"},
            ).json()
            response = client.patch(
                f"/api/rooms/{created['id']}",
                headers={"X-Admin-Token": "test-token"},
                json={"name": "after", "quality": "蓝光"},
            )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["name"], "after")
        self.assertEqual(payload["quality"], "蓝光")
        self.assertEqual(payload["url"], room_url)

    def test_room_patch_duplicate_url_returns_conflict(self) -> None:
        suffix = uuid4().hex
        first_url = f"https://live.douyin.com/unittest-duplicate-a-{suffix}"
        second_url = f"https://live.douyin.com/unittest-duplicate-b-{suffix}"
        with TestClient(app) as client:
            first = client.post(
                "/api/rooms",
                headers={"X-Admin-Token": "test-token"},
                json={"url": first_url, "name": "first"},
            ).json()
            client.post(
                "/api/rooms",
                headers={"X-Admin-Token": "test-token"},
                json={"url": second_url, "name": "second"},
            )
            response = client.patch(
                f"/api/rooms/{first['id']}",
                headers={"X-Admin-Token": "test-token"},
                json={"url": second_url},
            )
        self.assertEqual(response.status_code, 409)
        self.assertIn("已存在", response.json()["detail"])

    def test_room_delete_hides_room_from_list(self) -> None:
        room_url = f"https://live.douyin.com/unittest-delete-room-{uuid4().hex}"
        with TestClient(app) as client:
            created = client.post(
                "/api/rooms",
                headers={"X-Admin-Token": "test-token"},
                json={"url": room_url, "name": "delete-room"},
            ).json()
            response = client.delete(
                f"/api/rooms/{created['id']}",
                headers={"X-Admin-Token": "test-token"},
            )
            rooms = client.get("/api/rooms").json()["data"]
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["deleted"])
        self.assertFalse(any(room["id"] == created["id"] for room in rooms))

    def test_retry_failed_upload_marks_pending(self) -> None:
        video_path = PROJECT_ROOT / "downloads" / "unittest-retry.mp4"
        video_path.parent.mkdir(parents=True, exist_ok=True)
        video_path.write_bytes(b"fake-video")
        try:
            recorded = repository.register_file(video_path, source="unittest")
            upload = next(
                item
                for item in repository.list_rows("upload_records")
                if item.get("recorded_file_id") == recorded["id"]
            )
            repository.mark_upload_failed(upload["id"], "temporary failure")
            with TestClient(app) as client:
                response = client.post(
                    f"/api/uploads/{upload['id']}/retry",
                    headers={"X-Admin-Token": "test-token"},
                )
                marked = client.get("/api/uploads", params={"status": "pending"}).json()["data"]
        finally:
            video_path.unlink(missing_ok=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "pending")
        self.assertTrue(any(item["id"] == upload["id"] for item in marked))

    def test_recorded_file_rename_updates_metadata(self) -> None:
        video_path = PROJECT_ROOT / "downloads" / "unittest-rename-before.mp4"
        renamed_path = video_path.with_name("unittest-rename-after.mp4")
        video_path.parent.mkdir(parents=True, exist_ok=True)
        video_path.write_bytes(b"fake-video")
        renamed_path.unlink(missing_ok=True)
        try:
            recorded = repository.register_file(video_path, source="unittest")
            with TestClient(app) as client:
                response = client.patch(
                    f"/api/files/{recorded['id']}/rename",
                    headers={"X-Admin-Token": "test-token"},
                    json={"filename": renamed_path.name},
                )
            self.assertEqual(response.status_code, 200)
            self.assertFalse(video_path.exists())
            self.assertTrue(renamed_path.exists())
            self.assertEqual(Path(response.json()["local_path"]).name, renamed_path.name)
        finally:
            video_path.unlink(missing_ok=True)
            renamed_path.unlink(missing_ok=True)

    def test_recorded_file_delete_removes_file_and_row(self) -> None:
        video_path = PROJECT_ROOT / "downloads" / "unittest-delete.mp4"
        video_path.parent.mkdir(parents=True, exist_ok=True)
        video_path.write_bytes(b"fake-video")
        recorded = repository.register_file(video_path, source="unittest")
        with TestClient(app) as client:
            response = client.delete(
                f"/api/files/{recorded['id']}",
                headers={"X-Admin-Token": "test-token"},
            )
            files = client.get("/api/files").json()["data"]
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["deleted"])
        self.assertFalse(video_path.exists())
        self.assertFalse(any(item["id"] == recorded["id"] for item in files))

    def test_recorded_file_delete_clears_upload_command_references(self) -> None:
        video_path = PROJECT_ROOT / "downloads" / "unittest-delete-upload-command.mp4"
        video_path.parent.mkdir(parents=True, exist_ok=True)
        video_path.write_bytes(b"fake-video")
        recorded = repository.register_file(video_path, source="unittest")
        upload = next(
            item
            for item in repository.list_rows("upload_records")
            if item.get("recorded_file_id") == recorded["id"]
        )
        repository.retry_upload(upload["id"])
        try:
            with TestClient(app) as client:
                response = client.delete(
                    f"/api/files/{recorded['id']}",
                    headers={"X-Admin-Token": "test-token"},
                )
            self.assertEqual(response.status_code, 200)
            self.assertFalse(repository.get_row("recorded_files", recorded["id"]))
            commands = repository.list_rows("task_commands", where="id > 0")
            self.assertFalse(any(command.get("upload_id") == upload["id"] for command in commands))
        finally:
            video_path.unlink(missing_ok=True)

    def test_recorded_file_delete_in_use_returns_conflict(self) -> None:
        video_path = PROJECT_ROOT / "downloads" / "unittest-delete-locked.mp4"
        video_path.parent.mkdir(parents=True, exist_ok=True)
        video_path.write_bytes(b"fake-video")
        recorded = repository.register_file(video_path, source="unittest")
        try:
            with patch("pathlib.Path.unlink", side_effect=PermissionError("locked")):
                with TestClient(app) as client:
                    response = client.delete(
                        f"/api/files/{recorded['id']}",
                        headers={"X-Admin-Token": "test-token"},
                    )
            self.assertEqual(response.status_code, 409)
            self.assertIn("正在使用", response.json()["detail"])
            self.assertIsNotNone(repository.get_row("recorded_files", recorded["id"]))
        finally:
            video_path.unlink(missing_ok=True)

    def test_recorded_file_transcode_registers_target(self) -> None:
        source_path = PROJECT_ROOT / "downloads" / "unittest-transcode.flv"
        target_path = source_path.with_suffix(".mp4")
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_bytes(b"fake-video")
        target_path.unlink(missing_ok=True)
        recorded = repository.register_file(source_path, source="unittest", create_upload=False)

        def fake_transcode(_source_path, delete_origin=False, reencode_h264=False):
            target_path.write_bytes(b"fake-mp4")
            return target_path

        try:
            with patch("server.app.transcode_service.transcode_to_mp4", side_effect=fake_transcode):
                with TestClient(app) as client:
                    response = client.post(
                        f"/api/files/{recorded['id']}/transcode",
                        headers={"X-Admin-Token": "test-token"},
                        json={"delete_origin": False, "reencode_h264": False},
                    )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["format"], "mp4")
            self.assertEqual(Path(response.json()["local_path"]).name, target_path.name)
        finally:
            source_path.unlink(missing_ok=True)
            target_path.unlink(missing_ok=True)

    def test_config_export_to_temp_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.ini"
            url_path = Path(temp_dir) / "URL_config.ini"
            result = config_service.export_ini(config_path=config_path, url_config_path=url_path)
        self.assertIn("settings_sections", result)
        self.assertIn("room_lines", result)

    def test_download_watch_skips_admin_recording_jobs_dir(self) -> None:
        admin_jobs_root = PROJECT_ROOT / "downloads" / "admin_jobs"
        video_path = admin_jobs_root / "job_unittest_skip" / "record.mp4"
        video_path.parent.mkdir(parents=True, exist_ok=True)
        video_path.write_bytes(b"fake-video")
        repository.upsert_setting(
            "download_watch.settings",
            {
                "enabled": True,
                "directories": [str(admin_jobs_root.resolve())],
                "poll_interval_seconds": 10,
                "stable_checks": 1,
                "transcode_non_mp4": False,
                "delete_origin_after_transcode": False,
                "reencode_h264": False,
            },
            "download_watch",
        )
        try:
            result = download_watch_service.scan_once()
            rows = repository.list_rows("download_watch_records", where="local_path = ?", params=(str(video_path.resolve()),))
        finally:
            video_path.unlink(missing_ok=True)
            video_path.parent.rmdir()
        self.assertEqual(result["candidates"], 0)
        self.assertFalse(rows)

    def test_delete_finished_douyin_task(self) -> None:
        with repository.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO douyin_collection_tasks(task_type, input_url, status, max_items)
                VALUES('single', 'https://v.douyin.com/unittest', 'completed', 1)
                """
            )
            task_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
            connection.execute(
                """
                INSERT INTO douyin_downloaded_items(task_id, aweme_id, status)
                VALUES(?, 'aweme-unittest', 'downloaded')
                """,
                (task_id,),
            )
        with TestClient(app) as client:
            response = client.delete(
                f"/api/douyin/tasks/{task_id}",
                headers={"X-Admin-Token": "test-token"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(repository.get_row("douyin_collection_tasks", task_id))
        self.assertFalse(repository.list_rows("douyin_downloaded_items", where="task_id = ?", params=(task_id,)))


if __name__ == "__main__":
    unittest.main()
