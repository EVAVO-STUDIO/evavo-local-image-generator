#!/usr/bin/env python3
"""Isolated integration tests for the optional EVAVO HTTP compatibility gateway."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Tuple

ROOT = Path(__file__).resolve().parent
NATIVE_PORT = 18210
GATEWAY_PORT = 18211


def wait_port(port: int, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"port {port} did not become ready")


def stop_process(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def request_json(url: str, *, method: str = "GET", payload: Dict[str, Any] | None = None) -> Tuple[int, Dict[str, Any]]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read()
            status = int(getattr(response, "status", 200))
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = exc.code
    parsed = json.loads(raw.decode("utf-8", errors="replace"))
    if not isinstance(parsed, dict):
        raise AssertionError(f"expected JSON object from {url}")
    return status, parsed


class GatewayIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory()
        cls.state_dir = Path(cls.temp.name) / "gateway-state"
        cls.task_history = Path(cls.temp.name) / "task-history.json"

        cls.native = subprocess.Popen(
            [sys.executable, str(ROOT / "mock-comfyui-server.py"), "--port", str(NATIVE_PORT), "--native-only"],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        wait_port(NATIVE_PORT)

        env = os.environ.copy()
        env["COMFYUI_ENDPOINT"] = f"http://127.0.0.1:{NATIVE_PORT}"
        env["EVAVO_GATEWAY_HOST"] = "127.0.0.1"
        env["EVAVO_GATEWAY_PORT"] = str(GATEWAY_PORT)
        env["EVAVO_GATEWAY_STATE_DIR"] = str(cls.state_dir)
        env["EVAVO_TASK_HISTORY"] = str(cls.task_history)
        cls.env = env
        cls.gateway = subprocess.Popen(
            [sys.executable, str(ROOT / "EVAVO-GATEWAY.py")],
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        wait_port(GATEWAY_PORT)
        cls.base = f"http://127.0.0.1:{GATEWAY_PORT}"

    @classmethod
    def tearDownClass(cls) -> None:
        stop_process(cls.gateway)
        stop_process(cls.native)
        cls.temp.cleanup()

    def test_health_requires_native_comfyui(self) -> None:
        status, payload = request_json(self.base + "/health")
        self.assertEqual(status, 200)
        self.assertEqual(payload, {"status": "healthy", "gateway": "ok", "comfyui": "ok"})

    def test_capabilities_are_truthful(self) -> None:
        status, payload = request_json(self.base + "/capabilities")
        self.assertEqual(status, 200)
        self.assertTrue(payload["image"]["ready"])
        for kind in ("video", "audio", "3d"):
            self.assertFalse(payload[kind]["ready"])
            self.assertIn("not part of", payload[kind]["reason"])

    def test_unsupported_modalities_fail_before_queueing(self) -> None:
        for kind in ("video", "audio", "3d"):
            status, payload = request_json(self.base + f"/generate/{kind}", method="POST", payload={"prompt": "test"})
            self.assertEqual(status, 501, (kind, payload))

    def test_image_generation_completes_and_downloads(self) -> None:
        status, queued = request_json(
            self.base + "/generate/image",
            method="POST",
            payload={"prompt": "EVAVO gateway isolated native image test", "project_name": "gateway_test"},
        )
        self.assertEqual(status, 202)
        task_id = str(queued.get("task_id", ""))
        self.assertTrue(task_id.startswith("img_"), queued)

        deadline = time.monotonic() + 20
        latest: Dict[str, Any] = {}
        while time.monotonic() < deadline:
            status, latest = request_json(self.base + f"/tasks/{task_id}/status")
            self.assertEqual(status, 200)
            if latest.get("status") in {"completed", "failed"}:
                break
            time.sleep(0.15)
        self.assertEqual(latest.get("status"), "completed", latest)
        self.assertEqual(latest.get("progress"), 100, latest)
        self.assertTrue(latest.get("result_ready"), latest)

        request = urllib.request.Request(self.base + f"/results/{task_id}")
        with urllib.request.urlopen(request, timeout=10) as response:
            body = response.read()
            self.assertEqual(int(getattr(response, "status", 200)), 200)
        self.assertGreater(len(body), 0)

    def test_service_manager_reports_same_native_health(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "EVAVO-SERVICE-MANAGER.py"), "health"],
            cwd=str(ROOT),
            env=self.env,
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "healthy")
        self.assertEqual(payload["comfyui"]["mode"], "native-comfyui")

    def test_public_bind_is_rejected(self) -> None:
        env = self.env.copy()
        env["EVAVO_GATEWAY_HOST"] = "0.0.0.0"
        env["EVAVO_GATEWAY_PORT"] = "18212"
        result = subprocess.run(
            [sys.executable, str(ROOT / "EVAVO-GATEWAY.py")],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("restricted to loopback", result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
