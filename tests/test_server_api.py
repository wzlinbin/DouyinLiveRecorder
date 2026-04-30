from __future__ import annotations

import os
import tempfile
import unittest
from uuid import uuid4
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from server.app import app, command_worker_service, config_service, repository
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


class ServerApiTest(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["ADMIN_API_TOKEN"] = "test-token"

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
                output_dir = PROJECT_ROOT / "downloads" / "admin_jobs" / f"job_{job['id']}"
                output_dir.mkdir(parents=True, exist_ok=True)
                (output_dir / "fake_record.mp4").write_bytes(b"fake-video")
                client.post(f"/api/rooms/{room['id']}/stop", headers={"X-Admin-Token": "test-token"})
                command_worker_service.process_pending_commands()
                files = client.get("/api/files", params={"job_id": job["id"]}).json()["data"]
                uploads = client.get("/api/uploads").json()["data"]
        self.assertTrue(files)
        self.assertEqual(files[0]["job_id"], job["id"])
        self.assertEqual(files[0]["room_id"], room["id"])
        self.assertTrue(any(item.get("recorded_file_id") == files[0]["id"] for item in uploads))

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

    def test_index_page_contains_admin_sections(self) -> None:
        with TestClient(app) as client:
            response = client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("后台管理", response.text)
        self.assertIn("/api/dashboard", response.text)
        self.assertIn("直播间管理", response.text)
        self.assertIn('data-action="edit-room"', response.text)
        self.assertIn('data-action="retry-upload"', response.text)

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
        self.assertIn("already exists", response.json()["detail"])

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


if __name__ == "__main__":
    unittest.main()
