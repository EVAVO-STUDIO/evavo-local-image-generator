#!/usr/bin/env python3
"""End-to-end validation for the EVAVO operational control plane.

Uses only the standard library so it can validate a clean Python 3.10+
installation before optional repository dependencies are installed.
"""

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


class OperationsIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = subprocess.Popen(
            [sys.executable, str(ROOT / "mock-comfyui-server.py"), "--port", str(TEST_PORT)],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.time() + 10
        while time.time() < deadline:
            if cls.server.poll() is not None:
                raise RuntimeError("mock service exited before becoming ready")
            try:
                with urllib.request.urlopen(f"{ENDPOINT}/system", timeout=0.5) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                if payload.get("status") == "ready":
                    return
            except Exception:
                time.sleep(0.1)
        cls.server.terminate()
        raise RuntimeError("mock service did not become ready")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.terminate()
        try:
            cls.server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            cls.server.kill()
            cls.server.wait(timeout=5)

    def test_wrapper_health(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "evavo-wrapper.py"), "health_check", "{}", "--endpoint", ENDPOINT],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "ready")

    def test_wrapper_generation_returns_task_id(self) -> None:
        request = json.dumps({"prompt": "integration test image", "project_name": "tests"})
        result = subprocess.run(
            [sys.executable, str(ROOT / "evavo-wrapper.py"), "generate_image", request, "--endpoint", ENDPOINT],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "queued")
        self.assertTrue(payload["task_id"].startswith("evavo_"))

    def test_monitor_reports_operational(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "monitor-evavo.py"), "--endpoint", ENDPOINT, "--json"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["healthy"])
        self.assertEqual(payload["status"], "operational")

    def test_batch_is_tracked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            history = Path(directory) / "task_history.json"
            env = os.environ.copy()
            env["EVAVO_TASK_HISTORY"] = str(history)
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "generate-batch.py"),
                    "--prompts",
                    "first test image",
                    "second test image",
                    "--project",
                    "integration",
                    "--endpoint",
                    ENDPOINT,
                    "--concurrency",
                    "2",
                    "--json",
                ],
                cwd=str(ROOT),
                env=env,
                capture_output=True,
                text=True,
                timeout=20,
            )
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["queued"], 2)
            stored = json.loads(history.read_text(encoding="utf-8"))
            self.assertEqual(len(stored), 2)
            self.assertTrue(all(item["status"] == "queued" for item in stored))

    def test_offline_monitor_returns_nonzero(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "monitor-evavo.py"),
                "--endpoint",
                "http://127.0.0.1:18189",
                "--json",
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["healthy"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
