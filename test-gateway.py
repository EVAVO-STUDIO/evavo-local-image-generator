#!/usr/bin/env python3
"""Isolated integration tests for the optional EVAVO HTTP compatibility gateway."""

from __future__ import annotations

import http.client
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
from concurrent.futures import ThreadPoolExecutor
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


def wait_terminal(base: str, task_id: str, timeout: float = 20.0) -> Dict[str, Any]:
    deadline = time.monotonic() + timeout
    latest: Dict[str, Any] = {}
    while time.monotonic() < deadline:
        status, latest = request_json(base + f"/tasks/{task_id}/status")
        if status != 200:
            raise AssertionError((status, latest))
        if latest.get("status") in {"completed", "failed", "cancelled"}:
            return latest
        time.sleep(0.15)
    raise AssertionError(f"task {task_id} did not reach a terminal state: {latest}")


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
        env["EVAVO_GATEWAY_MAX_REQUEST_BYTES"] = "8192"
        env["EVAVO_GATEWAY_MAX_PROJECT_CHARS"] = "32"
        for name in (
            "EVAVO_GATEWAY_CORS_ORIGINS",
            "EVAVO_GATEWAY_ALLOW_REQUEST_WORKFLOW_PATHS",
            "EVAVO_COMFYUI_WORKFLOW",
            "EVAVO_VIDEO_PROVIDER_ARGV",
            "EVAVO_VIDEO_STUDIO_DIR",
            "EVAVO_VIDEO_PYTHON",
            "EVAVO_VIDEO_PROVIDER_TIMEOUT",
            "EVAVO_WAN21_MODEL_DIR",
            "EVAVO_WAN21_MODEL_MANIFEST_SHA256",
            "EVAVO_AUDIO_PROVIDER_ARGV",
            "EVAVO_AUDIO_PROVIDER_TIMEOUT",
            "EVAVO_3D_AGENT_EXECUTION_ENABLED",
            "EVAVO_3D_AGENT_EXECUTION_TOKEN",
            "EVAVO_3D_AGENT_WORKSPACE_ROOT",
            "EVAVO_3D_ENDPOINT",
            "EVAVO_3D_PROVIDER_TIMEOUT",
        ):
            env.pop(name, None)
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

    def test_services_and_capabilities_report_auxiliary_readiness_truthfully(self) -> None:
        status, services = request_json(self.base + "/services")
        self.assertEqual(status, 200)
        self.assertTrue(services["image"]["ready"])

        status, capabilities = request_json(self.base + "/capabilities")
        self.assertEqual(status, 200)
        self.assertTrue(capabilities["image"]["ready"])
        for kind in ("video", "audio", "3d"):
            self.assertIn(kind, services)
            self.assertIn(kind, capabilities)
            self.assertFalse(bool(capabilities[kind]["ready"]), (kind, capabilities[kind]))

    def test_unavailable_auxiliary_providers_fail_closed_after_queueing(self) -> None:
        prefixes = {"video": "vid_", "audio": "aud_", "3d": "3d_"}
        for kind, prefix in prefixes.items():
            status, queued = request_json(self.base + f"/generate/{kind}", method="POST", payload={"prompt": "test"})
            self.assertEqual(status, 202, (kind, queued))
            task_id = str(queued.get("task_id", ""))
            self.assertTrue(task_id.startswith(prefix), (kind, queued))
            terminal = wait_terminal(self.base, task_id)
            self.assertEqual(terminal.get("status"), "failed", (kind, terminal))
            self.assertFalse(terminal.get("result_ready"), (kind, terminal))
            self.assertTrue(str(terminal.get("error_code", "")).startswith("PROVIDER_"), (kind, terminal))

    def test_image_generation_completes_and_downloads(self) -> None:
        status, queued = request_json(
            self.base + "/generate/image",
            method="POST",
            payload={"prompt": "EVAVO gateway isolated native image test", "project_name": "gateway_test"},
        )
        self.assertEqual(status, 202)
        task_id = str(queued.get("task_id", ""))
        self.assertTrue(task_id.startswith("img_"), queued)

        latest = wait_terminal(self.base, task_id)
        self.assertEqual(latest.get("status"), "completed", latest)
        self.assertEqual(latest.get("progress"), 100, latest)
        self.assertTrue(latest.get("result_ready"), latest)

        request = urllib.request.Request(self.base + f"/results/{task_id}")
        with urllib.request.urlopen(request, timeout=10) as response:
            body = response.read()
            self.assertEqual(int(getattr(response, "status", 200)), 200)
        self.assertGreater(len(body), 0)

    def test_per_request_workflow_path_is_denied_by_default(self) -> None:
        status, payload = request_json(
            self.base + "/generate/image",
            method="POST",
            payload={"prompt": "workflow boundary", "workflow_path": "C:\\private\\workflow.json"},
        )
        self.assertEqual(status, 403, payload)
        self.assertIn("per-request workflow_path is disabled", str(payload.get("detail", "")))

    def test_project_name_is_bounded_before_task_persistence(self) -> None:
        project = "p" * 200
        status, queued = request_json(
            self.base + "/generate/audio",
            method="POST",
            payload={"prompt": "project bound", "project_name": project},
        )
        self.assertEqual(status, 202, queued)
        task_id = str(queued["task_id"])
        status, persisted = request_json(self.base + f"/tasks/{task_id}/status")
        self.assertEqual(status, 200)
        self.assertEqual(persisted.get("project_name"), "p" * 32)

    def test_declared_oversized_request_is_rejected_before_queueing(self) -> None:
        status, before = request_json(self.base + "/tasks")
        self.assertEqual(status, 200)
        before_ids = {str(item.get("task_id")) for item in before.get("tasks", [])}
        status, payload = request_json(
            self.base + "/generate/audio",
            method="POST",
            payload={"prompt": "oversized", "blob": "x" * 9000},
        )
        self.assertEqual(status, 413, payload)
        status, after = request_json(self.base + "/tasks")
        self.assertEqual(status, 200)
        after_ids = {str(item.get("task_id")) for item in after.get("tasks", [])}
        self.assertEqual(after_ids, before_ids)

    def test_chunked_oversized_request_is_rejected_before_parsing(self) -> None:
        connection = http.client.HTTPConnection("127.0.0.1", GATEWAY_PORT, timeout=10)
        chunks = [b'{"prompt":"chunked","blob":"', b"x" * 9000, b'"}']
        try:
            connection.request(
                "POST",
                "/generate/audio",
                body=iter(chunks),
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                encode_chunked=True,
            )
            response = connection.getresponse()
            raw = response.read()
            self.assertEqual(response.status, 413, raw)
            payload = json.loads(raw.decode("utf-8", errors="replace"))
            self.assertIn("request exceeds EVAVO gateway limit", str(payload.get("detail", "")))
        finally:
            connection.close()

    def test_cors_is_disabled_by_default(self) -> None:
        request = urllib.request.Request(self.base + "/health", headers={"Origin": "https://example.com"})
        with urllib.request.urlopen(request, timeout=10) as response:
            self.assertEqual(int(getattr(response, "status", 200)), 200)
            self.assertIsNone(response.headers.get("Access-Control-Allow-Origin"))

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

    def test_wildcard_cors_configuration_is_rejected(self) -> None:
        env = self.env.copy()
        env["EVAVO_GATEWAY_CORS_ORIGINS"] = "*"
        env["EVAVO_GATEWAY_PORT"] = "18213"
        result = subprocess.run(
            [sys.executable, str(ROOT / "EVAVO-GATEWAY.py")],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("accepts only explicit loopback", result.stderr + result.stdout)

    def test_persisted_task_suffix_prevents_restart_id_reuse(self) -> None:
        port = 18214
        state_dir = Path(self.temp.name) / "restart-id-state"
        state_dir.mkdir(parents=True, exist_ok=True)
        existing_id = "aud_9999999999"
        (state_dir / "tasks.json").write_text(
            json.dumps(
                {
                    "version": 2,
                    "tasks": {
                        existing_id: {
                            "task_id": existing_id,
                            "type": "audio",
                            "status": "failed",
                            "progress": 0,
                            "prompt": "old task",
                            "project_name": "restart-test",
                            "created_at": "2026-09-09T00:00:00+00:00",
                            "updated_at": "2026-09-09T00:00:00+00:00",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        env = self.env.copy()
        env["EVAVO_GATEWAY_PORT"] = str(port)
        env["EVAVO_GATEWAY_STATE_DIR"] = str(state_dir)
        env["EVAVO_TASK_HISTORY"] = str(Path(self.temp.name) / "restart-id-history.json")
        process = subprocess.Popen(
            [sys.executable, str(ROOT / "EVAVO-GATEWAY.py")],
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        try:
            wait_port(port)
            base = f"http://127.0.0.1:{port}"
            status, queued = request_json(base + "/generate/audio", method="POST", payload={"prompt": "new task"})
            self.assertEqual(status, 202, queued)
            new_id = str(queued.get("task_id", ""))
            self.assertTrue(new_id.startswith("aud_"), queued)
            self.assertGreater(int(new_id.split("_", 1)[1]), 9_999_999_999)
            status, old_task = request_json(base + f"/tasks/{existing_id}/status")
            self.assertEqual(status, 200)
            self.assertEqual(old_task.get("task_id"), existing_id)
        finally:
            stop_process(process)

    def test_shared_task_file_allocates_unique_ids_across_gateway_processes(self) -> None:
        ports = (18215, 18216)
        state_dir = Path(self.temp.name) / "shared-state"
        state_dir.mkdir(parents=True, exist_ok=True)
        processes: list[subprocess.Popen[Any]] = []
        bases: list[str] = []
        try:
            for index, port in enumerate(ports):
                env = self.env.copy()
                env["EVAVO_GATEWAY_PORT"] = str(port)
                env["EVAVO_GATEWAY_STATE_DIR"] = str(state_dir)
                env["EVAVO_TASK_HISTORY"] = str(Path(self.temp.name) / f"shared-history-{index}.json")
                process = subprocess.Popen(
                    [sys.executable, str(ROOT / "EVAVO-GATEWAY.py")],
                    cwd=str(ROOT),
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )
                processes.append(process)
                wait_port(port)
                bases.append(f"http://127.0.0.1:{port}")

            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [
                    pool.submit(request_json, base + "/generate/audio", method="POST", payload={"prompt": f"shared {index}"})
                    for index, base in enumerate(bases)
                ]
                results = [future.result(timeout=15) for future in futures]
            self.assertTrue(all(status == 202 for status, _ in results), results)
            ids = [str(payload.get("task_id", "")) for _, payload in results]
            self.assertEqual(len(set(ids)), 2, ids)
            self.assertTrue(all(task_id.startswith("aud_") for task_id in ids), ids)

            status, listing = request_json(bases[0] + "/tasks")
            self.assertEqual(status, 200)
            listed = {str(item.get("task_id")) for item in listing.get("tasks", [])}
            self.assertTrue(set(ids).issubset(listed), (ids, listed))
        finally:
            for process in processes:
                stop_process(process)

    def test_corrupt_task_state_fails_closed_without_overwrite(self) -> None:
        port = 18217
        state_dir = Path(self.temp.name) / "corrupt-state"
        state_dir.mkdir(parents=True, exist_ok=True)
        task_file = state_dir / "tasks.json"
        corrupt = "{this is not valid json\n"
        task_file.write_text(corrupt, encoding="utf-8")
        env = self.env.copy()
        env["EVAVO_GATEWAY_PORT"] = str(port)
        env["EVAVO_GATEWAY_STATE_DIR"] = str(state_dir)
        env["EVAVO_TASK_HISTORY"] = str(Path(self.temp.name) / "corrupt-history.json")
        process = subprocess.Popen(
            [sys.executable, str(ROOT / "EVAVO-GATEWAY.py")],
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            stdout, stderr = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            stop_process(process)
            self.fail("gateway unexpectedly stayed running with corrupt task state")
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("GATEWAY_TASK_STATE_CORRUPT", stdout + stderr)
        self.assertEqual(task_file.read_text(encoding="utf-8"), corrupt)


if __name__ == "__main__":
    unittest.main(verbosity=2)
