#!/usr/bin/env python3
"""Production bootstrap must never be satisfied by the deterministic EVAVO mock."""

from __future__ import annotations

import json
import subprocess
import sys
import time
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NATIVE_PORT = 18210
MOCK_PORT = 18211
NATIVE_ENDPOINT = f"http://127.0.0.1:{NATIVE_PORT}"
MOCK_ENDPOINT = f"http://127.0.0.1:{MOCK_PORT}"


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


def run_bootstrap(endpoint: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "evavo.py"),
            "bootstrap",
            "--skip-pull",
            "--skip-verify",
            "--endpoint",
            endpoint,
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )


class ProductionBootstrapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.native = subprocess.Popen(
            [sys.executable, str(ROOT / "mock-comfyui-server.py"), "--port", str(NATIVE_PORT), "--native-only"],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        cls.mock = subprocess.Popen(
            [sys.executable, str(ROOT / "mock-comfyui-server.py"), "--port", str(MOCK_PORT)],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            wait_json(f"{NATIVE_ENDPOINT}/system_stats", "system")
            wait_json(f"{MOCK_ENDPOINT}/system", "status")
        except Exception:
            cls.native.terminate()
            cls.mock.terminate()
            raise

    @classmethod
    def tearDownClass(cls) -> None:
        for process in (cls.native, cls.mock):
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    def test_bootstrap_accepts_native_renderer(self) -> None:
        result = run_bootstrap(NATIVE_ENDPOINT)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertIn("completed successfully with a native renderer", result.stdout)
        self.assertIn("native-comfyui", result.stdout)

    def test_bootstrap_rejects_deterministic_mock(self) -> None:
        result = run_bootstrap(MOCK_ENDPOINT)
        self.assertNotEqual(result.returncode, 0, result.stderr or result.stdout)
        combined = (result.stdout + "\n" + result.stderr).lower()
        self.assertIn("native comfyui could not be started", combined)
        self.assertNotIn("completed successfully with a native renderer", combined)

    def test_bootstrap_command_is_statically_strict(self) -> None:
        source = (ROOT / "evavo.py").read_text(encoding="utf-8")
        self.assertIn('[sys.executable, controller, "start", "--endpoint", endpoint, "--no-mock"]', source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
