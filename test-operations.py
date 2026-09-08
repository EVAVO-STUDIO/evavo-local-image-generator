#!/usr/bin/env python3
"""End-to-end validation for EVAVO mock and native-ComfyUI operation."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEST_PORT = 18188
ENDPOINT = f"http://127.0.0.1:{TEST_PORT}"
CONTROLLER_PORT = 18190
CONTROLLER_ENDPOINT = f"http://127.0.0.1:{CONTROLLER_PORT}"
NATIVE_PORT = 18191
NATIVE_ENDPOINT = f"http://127.0.0.1:{NATIVE_PORT}"
STATE_FILE = ROOT / ".evavo" / "operations-service.json"


def run_python(script: str, *args: str, timeout: int = 20, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(ROOT / script), *args], cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=timeout)


def wait_json(url: str, expected_key: str, timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if expected_key in payload:
                return
        except Exception:
            time.sleep(0.1)
    raise RuntimeError(f"endpoint did not become ready: {url}")


class OperationsIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = subprocess.Popen([sys.executable, str(ROOT / "mock-comfyui-server.py"), "--port", str(TEST_PORT)], cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.native_server = subprocess.Popen([sys.executable, str(ROOT / "mock-comfyui-server.py"), "--port", str(NATIVE_PORT), "--native-only"], cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            wait_json(f"{ENDPOINT}/system", "status")
            wait_json(f"{NATIVE_ENDPOINT}/system_stats", "system")
        except Exception:
            cls.server.terminate()
            cls.native_server.terminate()
            raise

    @classmethod
    def tearDownClass(cls) -> None:
        for process in (cls.server, cls.native_server):
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if STATE_FILE.exists():
            run_python("evavo.py", "stop", timeout=10)

    def test_wrapper_health_mock(self) -> None:
        result = run_python("evavo-wrapper.py", "health_check", "{}", "--endpoint", ENDPOINT, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["mode"], "mock")

    def test_wrapper_generation_mock_returns_task_id(self) -> None:
        request = json.dumps({"prompt": "integration test image", "project_name": "tests"})
        result = run_python("evavo-wrapper.py", "generate_image", request, "--endpoint", ENDPOINT, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "queued")
        self.assertTrue(payload["task_id"].startswith("evavo_"))

    def test_native_comfyui_health_detected(self) -> None:
        result = run_python("evavo-wrapper.py", "health_check", "{}", "--endpoint", NATIVE_ENDPOINT, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["backend"], "native-comfyui")
        self.assertEqual(payload["mode"], "native-comfyui")
        self.assertEqual(payload["comfyui_version"], "test-native-1.0")

    def test_native_comfyui_generation_and_outputs(self) -> None:
        request = json.dumps({"prompt": "native generation test", "project_name": "native_tests", "width": 512, "height": 512, "steps": 2})
        queued = run_python("evavo-wrapper.py", "generate_image", request, "--endpoint", NATIVE_ENDPOINT, timeout=10)
        self.assertEqual(queued.returncode, 0, queued.stderr or queued.stdout)
        queued_payload = json.loads(queued.stdout)
        self.assertEqual(queued_payload["status"], "queued")
        self.assertEqual(queued_payload["backend_mode"], "native-comfyui")
        self.assertEqual(queued_payload["checkpoint"], "evavo-test-model.safetensors")
        task_id = queued_payload["task_id"]

        status = run_python("evavo-wrapper.py", "task_status", json.dumps({"task_id": task_id}), "--endpoint", NATIVE_ENDPOINT, timeout=10)
        self.assertEqual(status.returncode, 0, status.stderr or status.stdout)
        status_payload = json.loads(status.stdout)
        self.assertEqual(status_payload["status"], "completed")
        self.assertEqual(len(status_payload["outputs"]), 1)
        self.assertTrue(status_payload["outputs"][0]["filename"].endswith(".png"))

    def test_monitor_reports_operational_for_both_backends(self) -> None:
        for endpoint in (ENDPOINT, NATIVE_ENDPOINT):
            result = run_python("monitor-evavo.py", "--endpoint", endpoint, "--json", timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["healthy"])
            self.assertEqual(payload["status"], "operational")

    def test_batch_is_tracked_mock(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            history = Path(directory) / "task_history.json"
            env = os.environ.copy()
            env["EVAVO_TASK_HISTORY"] = str(history)
            result = run_python("generate-batch.py", "--prompts", "first test image", "second test image", "--project", "integration", "--endpoint", ENDPOINT, "--concurrency", "2", "--json", timeout=20, env=env)
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["queued"], 2)
            stored = json.loads(history.read_text(encoding="utf-8"))
            self.assertEqual(len(stored), 2)

    def test_batch_is_tracked_native(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            history = Path(directory) / "task_history.json"
            env = os.environ.copy()
            env["EVAVO_TASK_HISTORY"] = str(history)
            result = run_python("generate-batch.py", "--prompts", "native one", "native two", "--project", "native_batch", "--endpoint", NATIVE_ENDPOINT, "--concurrency", "2", "--json", timeout=20, env=env)
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["queued"], 2)
            self.assertTrue(all(item.get("backend_mode") == "native-comfyui" for item in payload["results"]))

    def test_offline_monitor_returns_nonzero(self) -> None:
        result = run_python("monitor-evavo.py", "--endpoint", "http://127.0.0.1:18189", "--json", timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(json.loads(result.stdout)["healthy"])

    def test_doctor_accepts_native_backend(self) -> None:
        result = run_python("evavo.py", "doctor", "--endpoint", NATIVE_ENDPOINT, "--json", timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        payload = json.loads(result.stdout)
        service_check = next(item for item in payload["checks"] if item["name"] == "service")
        self.assertTrue(service_check["ok"])
        self.assertIn("native-comfyui", service_check["detail"])

    def test_start_prefers_existing_native_comfyui(self) -> None:
        run_python("evavo.py", "stop", timeout=10)
        result = run_python("evavo.py", "start", "--endpoint", NATIVE_ENDPOINT, "--wait", "5", timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "already_running")
        self.assertEqual(payload["health"]["mode"], "native-comfyui")
        self.assertFalse(STATE_FILE.exists())

    def test_controller_mock_start_status_stop(self) -> None:
        run_python("evavo.py", "stop", timeout=10)
        start = run_python("evavo.py", "start", "--endpoint", CONTROLLER_ENDPOINT, "--wait", "10", timeout=15)
        try:
            self.assertEqual(start.returncode, 0, start.stderr or start.stdout)
            status = run_python("evavo.py", "status", "--endpoint", CONTROLLER_ENDPOINT, timeout=10)
            self.assertEqual(status.returncode, 0, status.stderr or status.stdout)
            self.assertEqual(json.loads(status.stdout)["status"], "operational")
        finally:
            stop = run_python("evavo.py", "stop", timeout=10)
            self.assertEqual(stop.returncode, 0, stop.stderr or stop.stdout)
            self.assertFalse(STATE_FILE.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
