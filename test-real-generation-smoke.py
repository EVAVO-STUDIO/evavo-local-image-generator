#!/usr/bin/env python3
"""Offline integration tests for the real-generation setup proof command."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NATIVE_PORT = 18294


def wait_port(port: int, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"port {port} did not become ready")


def stop_process(process: subprocess.Popen[bytes] | subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


class RealGenerationSmokeTests(unittest.TestCase):
    def test_native_only_simulator_produces_valid_download_and_history(self) -> None:
        native = subprocess.Popen(
            [
                sys.executable,
                str(ROOT / "mock-comfyui-server.py"),
                "--port",
                str(NATIVE_PORT),
                "--native-only",
            ],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        try:
            wait_port(NATIVE_PORT)
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                output = root / "outputs"
                history = root / "history.json"
                env = os.environ.copy()
                for name in (
                    "EVAVO_COMFYUI_WORKFLOW",
                    "EVAVO_COMFYUI_CHECKPOINT",
                    "EVAVO_CHECKPOINT_FILE",
                    "EVAVO_CHECKPOINT_URL",
                    "EVAVO_SHARED_MODEL_ROOTS",
                    "EVAVO_COMFYUI_MODEL_ROOTS",
                ):
                    env.pop(name, None)
                env.update(
                    {
                        "PYTHONPATH": str(ROOT),
                        "COMFYUI_ENDPOINT": f"http://127.0.0.1:{NATIVE_PORT}",
                        "EVAVO_SMOKE_OUTPUT_DIR": str(output),
                        "EVAVO_TASK_HISTORY": str(history),
                    }
                )
                result = subprocess.run(
                    [sys.executable, str(ROOT / "real-generation-smoke.py"), "--json", "--timeout", "30"],
                    cwd=str(ROOT),
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=45,
                )
                self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
                payload = json.loads(result.stdout)
                self.assertTrue(payload["ok"], payload)
                self.assertEqual(payload["status"], "completed")
                self.assertTrue(payload["task_id"])
                self.assertEqual(payload["endpoint"], f"http://127.0.0.1:{NATIVE_PORT}")
                files = payload.get("downloaded_files")
                self.assertIsInstance(files, list)
                self.assertTrue(files)
                image = Path(files[0])
                self.assertTrue(image.is_file())
                self.assertFalse(image.is_symlink())
                self.assertTrue(image.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))

                rows = json.loads(history.read_text(encoding="utf-8"))
                record = next(item for item in rows if item.get("task_id") == payload["task_id"])
                self.assertEqual(record["status"], "completed")
                self.assertEqual(record["project_name"], "setup-smoke")
                self.assertTrue(record.get("output_uris"))
        finally:
            stop_process(native)

    def test_offline_endpoint_fails_without_claiming_generation_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            env = os.environ.copy()
            env.update(
                {
                    "PYTHONPATH": str(ROOT),
                    "COMFYUI_ENDPOINT": "http://127.0.0.1:18295",
                    "EVAVO_SMOKE_OUTPUT_DIR": str(root / "outputs"),
                    "EVAVO_TASK_HISTORY": str(root / "history.json"),
                }
            )
            result = subprocess.run(
                [sys.executable, str(ROOT / "real-generation-smoke.py"), "--json", "--timeout", "10"],
                cwd=str(ROOT),
                env=env,
                capture_output=True,
                text=True,
                timeout=20,
            )
            self.assertEqual(result.returncode, 2, result.stderr or result.stdout)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["error_code"], "NATIVE_COMFYUI_NOT_READY")
            self.assertNotEqual(payload.get("status"), "completed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
