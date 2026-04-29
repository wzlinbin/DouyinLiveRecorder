from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from server.app import app, config_service
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
        with patch("server.recorder_process_service.subprocess.Popen", return_value=FakeProcess()):
            with TestClient(app) as client:
                room = client.post(
                    "/api/rooms",
                    headers={"X-Admin-Token": "test-token"},
                    json={"url": "https://live.douyin.com/unittest-worker", "name": "unittest-worker"},
                ).json()
                job = client.post(f"/api/rooms/{room['id']}/start", headers={"X-Admin-Token": "test-token"}).json()
                time.sleep(3)
                output_dir = PROJECT_ROOT / "downloads" / "admin_jobs" / f"job_{job['id']}"
                output_dir.mkdir(parents=True, exist_ok=True)
                (output_dir / "fake_record.mp4").write_bytes(b"fake-video")
                client.post(f"/api/rooms/{room['id']}/stop", headers={"X-Admin-Token": "test-token"})
                time.sleep(3)
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

    def test_config_export_to_temp_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.ini"
            url_path = Path(temp_dir) / "URL_config.ini"
            result = config_service.export_ini(config_path=config_path, url_config_path=url_path)
        self.assertIn("settings_sections", result)
        self.assertIn("room_lines", result)


if __name__ == "__main__":
    unittest.main()
