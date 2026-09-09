#!/usr/bin/env python3
"""Integration and unit tests for workflow-aware strict agent readiness."""

from __future__ import annotations

import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
NATIVE_PORT = 18196
MCP_WARNING_PORT = 18197
AGENT_DOCTOR = ROOT / "agent-doctor.py"


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
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def load_agent_doctor():
    spec = importlib.util.spec_from_file_location("evavo_agent_doctor", AGENT_DOCTOR)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load agent-doctor.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WorkflowAwareDoctorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.native = subprocess.Popen(
            [
                sys.executable,
                str(ROOT / "mock-comfyui-server.py"),
                "--port",
                str(NATIVE_PORT),
                "--native-only",
                "--no-checkpoint-loader",
            ],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        wait_port(NATIVE_PORT)

    @classmethod
    def tearDownClass(cls) -> None:
        stop_process(cls.native)

    def _run_doctor(self, workflow_model: str) -> tuple[subprocess.CompletedProcess[str], dict]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            comfy = root / "ComfyUI"
            comfy.mkdir()
            (comfy / "main.py").write_text("# discovery fixture\n", encoding="utf-8")
            workflow = root / "workflow.json"
            workflow.write_text(
                json.dumps({"1": {"class_type": "UNETLoader", "inputs": {"unet_name": workflow_model}}}),
                encoding="utf-8",
            )
            appdata = root / "AppData" / "Roaming"
            output = root / "outputs"
            appdata.mkdir(parents=True)

            env = os.environ.copy()
            for name in (
                "EVAVO_CHECKPOINT_FILE",
                "EVAVO_CHECKPOINT_URL",
                "EVAVO_CHECKPOINT_SHA256",
                "EVAVO_CHECKPOINT_NAME",
                "EVAVO_COMFYUI_CHECKPOINT",
                "EVAVO_SHARED_MODEL_ROOTS",
                "EVAVO_COMFYUI_MODEL_ROOTS",
            ):
                env.pop(name, None)
            env["EVAVO_COMFYUI_HOME"] = str(comfy)
            env["EVAVO_COMFYUI_ENDPOINT"] = f"http://127.0.0.1:{NATIVE_PORT}"
            env["EVAVO_COMFYUI_WORKFLOW"] = str(workflow)
            env["EVAVO_GENERATION_OUTPUT_DIR"] = str(output)
            env["APPDATA"] = str(appdata)

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "agent-doctor.py"),
                    "--repair",
                    "--skip-tests",
                    "--json",
                    "--endpoint",
                    f"http://127.0.0.1:{NATIVE_PORT}",
                    "--mcp-port",
                    str(MCP_WARNING_PORT),
                ],
                cwd=str(ROOT),
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            payload = json.loads(result.stdout)
            return result, payload

    def test_valid_custom_unet_workflow_passes_strict_readiness_without_checkpoint_loader(self) -> None:
        result, payload = self._run_doctor("evavo-test-unet.safetensors")
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["generation_contract"], "custom_workflow")

        checks = {item["name"]: item for item in payload["checks"]}
        self.assertTrue(checks["native_comfyui"]["ok"], checks["native_comfyui"])
        self.assertTrue(checks["custom_workflow"]["ok"], checks["custom_workflow"])
        self.assertTrue(checks["checkpoints"]["ok"], checks["checkpoints"])
        self.assertIn("non-blocking", checks["checkpoints"]["detail"])
        self.assertIn("UNETLoader", checks["custom_workflow"]["detail"])

    def test_missing_custom_unet_model_fails_strict_readiness(self) -> None:
        result, payload = self._run_doctor("missing-unet.safetensors")
        self.assertEqual(result.returncode, 2, result.stderr or result.stdout)
        self.assertFalse(payload["ok"], payload)
        self.assertEqual(payload["status"], "needs_attention")
        self.assertEqual(payload["generation_contract"], "custom_workflow")

        checks = {item["name"]: item for item in payload["checks"]}
        self.assertFalse(checks["custom_workflow"]["ok"], checks["custom_workflow"])
        self.assertEqual(checks["custom_workflow"]["severity"], "error")
        self.assertIn("missing-unet.safetensors", checks["custom_workflow"]["detail"])
        self.assertTrue(checks["checkpoints"]["ok"], checks["checkpoints"])

    def test_healthy_non_discoverable_external_comfyui_is_reused_without_provisioning(self) -> None:
        module = load_agent_doctor()

        class ExternalBackend:
            def __init__(self, endpoint: str):
                self.endpoint = endpoint

            def checkpoints(self):
                return ["external-model.safetensors"]

            def model_inventory(self, limit: int):
                return {
                    "available_categories": 1,
                    "total_categories": 1,
                    "categories": {
                        "checkpoints": {"available": True, "count": 1, "items": ["external-model.safetensors"]}
                    },
                }

        env = os.environ.copy()
        for name in (
            "EVAVO_COMFYUI_WORKFLOW",
            "EVAVO_SHARED_MODEL_ROOTS",
            "EVAVO_COMFYUI_MODEL_ROOTS",
            "EVAVO_CHECKPOINT_FILE",
            "EVAVO_CHECKPOINT_URL",
        ):
            env.pop(name, None)

        healthy = {"healthy": True, "status": "ready", "mode": "native-comfyui"}
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(module, "native_health", return_value=healthy),
            patch.object(module, "discover_comfyui", return_value=[]),
            patch.object(module, "_provision_comfyui") as provision,
            patch.object(module, "ComfyUIBackend", ExternalBackend),
            patch.object(module, "_output_writable", return_value=(True, "/tmp/evavo-test")),
            patch.object(module, "_check_claude_config", return_value=(False, "not installed")),
            patch.object(module, "_port_open", return_value=False),
        ):
            payload = module.run(
                repair=True,
                provision=True,
                endpoint="http://127.0.0.1:18198",
                mcp_host="127.0.0.1",
                mcp_port=18199,
                run_tests=False,
            )

        provision.assert_not_called()
        self.assertTrue(payload["ok"], payload)
        checks = {item["name"]: item for item in payload["checks"]}
        self.assertTrue(checks["comfyui_install"]["ok"], checks["comfyui_install"])
        self.assertEqual(checks["comfyui_install"]["severity"], "info")
        self.assertIn("reuse it without cloning another runtime", checks["comfyui_install"]["detail"])
        self.assertTrue(checks["native_comfyui"]["ok"], checks["native_comfyui"])
        self.assertTrue(checks["checkpoints"]["ok"], checks["checkpoints"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
