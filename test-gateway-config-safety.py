#!/usr/bin/env python3
"""Focused startup/configuration safety tests for the EVAVO loopback gateway."""

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


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_port(port: int, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                return
        except OSError:
            time.sleep(0.1)
    raise AssertionError(f"gateway port {port} did not become ready")


def stop_process(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def request_json(url: str, *, payload: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read()
            status = int(getattr(response, "status", 200))
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = exc.code
    parsed = json.loads(raw.decode("utf-8", errors="replace"))
    return status, parsed


class GatewayConfigurationSafetyTests(unittest.TestCase):
    def base_env(self, temp_root: Path) -> dict[str, str]:
        env = os.environ.copy()
        env["EVAVO_GATEWAY_HOST"] = "127.0.0.1"
        env["EVAVO_GATEWAY_STATE_DIR"] = str(temp_root / "state")
        env["EVAVO_TASK_HISTORY"] = str(temp_root / "history.json")
        env["COMFYUI_ENDPOINT"] = "http://127.0.0.1:65534"
        for name in (
            "EVAVO_GATEWAY_CORS_ORIGINS",
            "EVAVO_GATEWAY_ALLOW_REQUEST_WORKFLOW_PATHS",
            "EVAVO_GATEWAY_WORKFLOW_ROOT",
            "EVAVO_COMFYUI_WORKFLOW",
            "EVAVO_VIDEO_PROVIDER_ARGV",
            "EVAVO_AUDIO_PROVIDER_ARGV",
            "EVAVO_3D_AGENT_EXECUTION_TOKEN",
            "EVAVO_3D_AGENT_WORKSPACE_ROOT",
        ):
            env.pop(name, None)
        return env

    def run_gateway_once(self, env: dict[str, str], timeout: float = 10.0) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(ROOT / "EVAVO-GATEWAY.py")],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def test_invalid_numeric_configuration_has_stable_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            env = self.base_env(Path(temp))
            env["EVAVO_GATEWAY_PORT"] = "not-a-port"
            result = self.run_gateway_once(env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("GATEWAY_CONFIG_INVALID:EVAVO_GATEWAY_PORT", result.stderr + result.stdout)

    def test_nonfinite_timeout_configuration_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            env = self.base_env(Path(temp))
            env["EVAVO_GATEWAY_PORT"] = str(free_port())
            env["EVAVO_GATEWAY_IMAGE_TIMEOUT"] = "nan"
            result = self.run_gateway_once(env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("GATEWAY_CONFIG_INVALID:EVAVO_GATEWAY_IMAGE_TIMEOUT", result.stderr + result.stdout)
        self.assertIn("finite", result.stderr + result.stdout)

    def test_request_workflow_opt_in_requires_owner_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            env = self.base_env(Path(temp))
            env["EVAVO_GATEWAY_PORT"] = str(free_port())
            env["EVAVO_GATEWAY_ALLOW_REQUEST_WORKFLOW_PATHS"] = "1"
            result = self.run_gateway_once(env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("GATEWAY_CONFIG_INVALID:EVAVO_GATEWAY_WORKFLOW_ROOT", result.stderr + result.stdout)

    def test_request_workflow_path_is_confined_to_owner_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            workflow_root = base / "allowed-workflows"
            workflow_root.mkdir()
            inside = workflow_root / "inside.json"
            inside.write_text("{}\n", encoding="utf-8")
            outside = base / "outside.json"
            outside.write_text("{}\n", encoding="utf-8")
            port = free_port()
            env = self.base_env(base)
            env["EVAVO_GATEWAY_PORT"] = str(port)
            env["EVAVO_GATEWAY_ALLOW_REQUEST_WORKFLOW_PATHS"] = "1"
            env["EVAVO_GATEWAY_WORKFLOW_ROOT"] = str(workflow_root)
            process = subprocess.Popen(
                [sys.executable, str(ROOT / "EVAVO-GATEWAY.py")],
                cwd=str(ROOT),
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            try:
                wait_port(port)
                gateway = f"http://127.0.0.1:{port}"
                status, payload = request_json(
                    gateway + "/generate/image",
                    payload={"prompt": "outside workflow", "workflow_path": str(outside)},
                )
                self.assertEqual(status, 403, payload)
                self.assertIn("outside EVAVO_GATEWAY_WORKFLOW_ROOT", str(payload.get("detail", "")))

                status, payload = request_json(
                    gateway + "/generate/image",
                    payload={"prompt": "missing workflow", "workflow_path": str(workflow_root / "missing.json")},
                )
                self.assertEqual(status, 422, payload)

                status, payload = request_json(
                    gateway + "/generate/image",
                    payload={"prompt": "inside workflow", "workflow_path": str(inside)},
                )
                self.assertEqual(status, 202, payload)
                self.assertTrue(str(payload.get("task_id", "")).startswith("img_"), payload)
            finally:
                stop_process(process)

    def test_loopback_cors_origin_with_invalid_port_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            env = self.base_env(Path(temp))
            env["EVAVO_GATEWAY_PORT"] = str(free_port())
            env["EVAVO_GATEWAY_CORS_ORIGINS"] = "http://localhost:99999"
            result = self.run_gateway_once(env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("EVAVO_GATEWAY_CORS_ORIGINS", result.stderr + result.stdout)
        self.assertIn("invalid", (result.stderr + result.stdout).lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
