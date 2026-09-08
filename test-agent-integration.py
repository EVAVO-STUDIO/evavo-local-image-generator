#!/usr/bin/env python3
"""Agent-facing integration tests for Claude/ChatGPT-compatible MCP operation."""

from __future__ import annotations

import importlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import anyio
from mcp import Client, StdioServerParameters

ROOT = Path(__file__).resolve().parent
HTTP_PORT = 18192
MOCK_PORT = 18193
NATIVE_MCP_PORT = 18195
EXPECTED_TOOLS = {
    "ensure_backend",
    "health_check",
    "discover_backends",
    "list_checkpoints",
    "generate_image",
    "generate_batch",
    "generation_status",
    "collect_generation",
    "task_history",
    "task_statistics",
    "stop_managed_backend",
}


def wait_port(port: int, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"port {port} did not become ready")


def tool_names(result: object) -> set[str]:
    tools = getattr(result, "tools", [])
    return {str(getattr(tool, "name", "")) for tool in tools}


def stop_process(process: subprocess.Popen[bytes] | subprocess.Popen[str]) -> None:
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


class AgentIntegrationTests(unittest.TestCase):
    def test_mcp_module_imports_and_inprocess_client_lists_tools(self) -> None:
        module = importlib.import_module("evavo_local_image_generator.mcp_server")
        self.assertTrue(hasattr(module, "mcp"))
        self.assertTrue(callable(module.main))

        async def exercise() -> None:
            async with Client(module.mcp) as client:
                names = tool_names(await client.list_tools())
                self.assertTrue(EXPECTED_TOOLS.issubset(names), names)

        anyio.run(exercise)

    def test_comfyui_source_install_discovery_from_environment(self) -> None:
        from evavo_local_image_generator import comfyui_runtime

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.py").write_text("# fake comfyui entry point\n", encoding="utf-8")
            previous = os.environ.get("EVAVO_COMFYUI_HOME")
            os.environ["EVAVO_COMFYUI_HOME"] = str(root)
            try:
                installs = comfyui_runtime.discover_comfyui()
            finally:
                if previous is None:
                    os.environ.pop("EVAVO_COMFYUI_HOME", None)
                else:
                    os.environ["EVAVO_COMFYUI_HOME"] = previous
            self.assertTrue(installs)
            self.assertEqual(installs[0].root, root.resolve())
            self.assertFalse(installs[0].portable)

    def test_runtime_rejects_evavo_mock_as_native_renderer(self) -> None:
        from evavo_local_image_generator.comfyui_runtime import native_health

        process = subprocess.Popen(
            [sys.executable, str(ROOT / "mock-comfyui-server.py"), "--port", str(MOCK_PORT)],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        try:
            wait_port(MOCK_PORT)
            self.assertIsNone(native_health(f"http://127.0.0.1:{MOCK_PORT}"))
        finally:
            stop_process(process)

    def test_agent_doctor_json_contract(self) -> None:
        with tempfile.TemporaryDirectory() as appdata:
            env = os.environ.copy()
            env["APPDATA"] = appdata
            result = subprocess.run(
                [sys.executable, str(ROOT / "agent-doctor.py"), "--skip-tests", "--json", "--mcp-port", "18194"],
                cwd=str(ROOT),
                env=env,
                capture_output=True,
                text=True,
                timeout=20,
            )
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])
            self.assertIn(payload["status"], {"operational", "degraded"})
            names = {item["name"] for item in payload["checks"]}
            self.assertIn("mcp_sdk", names)
            self.assertIn("output_directory", names)
            self.assertIn("claude_stdio", names)
            self.assertIn("mcp_http", names)

    def test_mcp_stdio_client_negotiates_and_lists_tools(self) -> None:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "evavo_local_image_generator.mcp_server", "--transport", "stdio"],
            env={"PYTHONPATH": str(ROOT), "PYTHONUNBUFFERED": "1"},
        )

        async def exercise() -> None:
            async with Client(params) as client:
                names = tool_names(await client.list_tools())
                self.assertTrue(EXPECTED_TOOLS.issubset(names), names)

        anyio.run(exercise)

    def test_mcp_streamable_http_generates_batch_and_persists_history(self) -> None:
        native_endpoint = f"http://127.0.0.1:{NATIVE_MCP_PORT}"
        native = subprocess.Popen(
            [sys.executable, str(ROOT / "mock-comfyui-server.py"), "--port", str(NATIVE_MCP_PORT), "--native-only"],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        wait_port(NATIVE_MCP_PORT)

        with tempfile.TemporaryDirectory() as state_directory, tempfile.TemporaryDirectory() as output_directory:
            history_file = Path(state_directory) / "agent-task-history.json"
            env = os.environ.copy()
            env["PYTHONPATH"] = str(ROOT)
            env["PYTHONUNBUFFERED"] = "1"
            env["EVAVO_COMFYUI_ENDPOINT"] = native_endpoint
            env["EVAVO_TASK_HISTORY"] = str(history_file)

            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "evavo_local_image_generator.mcp_server",
                    "--transport",
                    "streamable-http",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(HTTP_PORT),
                    "--path",
                    "/mcp",
                    "--json-response",
                ],
                cwd=str(ROOT),
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            try:
                wait_port(HTTP_PORT)
                self.assertIsNone(process.poll(), "HTTP MCP server exited unexpectedly")

                async def exercise() -> None:
                    async with Client(f"http://127.0.0.1:{HTTP_PORT}/mcp") as client:
                        names = tool_names(await client.list_tools())
                        self.assertTrue(EXPECTED_TOOLS.issubset(names), names)

                        single = await client.call_tool(
                            "generate_image",
                            {
                                "prompt": "EVAVO MCP end-to-end image test",
                                "project_name": "mcp_single",
                                "width": 512,
                                "height": 512,
                                "steps": 2,
                                "wait": True,
                                "auto_start": False,
                                "output_dir": output_directory,
                            },
                        )
                        single_payload = single.structured_content
                        self.assertIsInstance(single_payload, dict)
                        assert isinstance(single_payload, dict)
                        self.assertEqual(single_payload.get("status"), "completed")
                        self.assertTrue(single_payload.get("downloaded_files"))

                        batch = await client.call_tool(
                            "generate_batch",
                            {
                                "prompts": ["agent batch one", "agent batch two"],
                                "project_name": "mcp_batch_test",
                                "width": 512,
                                "height": 512,
                                "steps": 2,
                                "wait": True,
                                "auto_start": False,
                                "output_dir": output_directory,
                                "concurrency": 2,
                            },
                        )
                        batch_payload = batch.structured_content
                        self.assertIsInstance(batch_payload, dict)
                        assert isinstance(batch_payload, dict)
                        self.assertTrue(batch_payload.get("ok"), batch_payload)
                        self.assertEqual(batch_payload.get("successful"), 2)
                        self.assertEqual(batch_payload.get("failed"), 0)
                        for item in batch_payload.get("results", []):
                            self.assertEqual(item.get("status"), "completed")
                            for file_name in item.get("downloaded_files", []):
                                path = Path(str(file_name))
                                self.assertTrue(path.is_file(), path)
                                self.assertGreater(path.stat().st_size, 0)

                        history = await client.call_tool("task_history", {"limit": 10})
                        history_payload = history.structured_content
                        self.assertIsInstance(history_payload, list)
                        assert isinstance(history_payload, list)
                        self.assertGreaterEqual(len(history_payload), 3)
                        self.assertTrue(all(item.get("status") == "completed" for item in history_payload[-3:]))

                        stats = await client.call_tool("task_statistics", {})
                        stats_payload = stats.structured_content
                        self.assertIsInstance(stats_payload, dict)
                        assert isinstance(stats_payload, dict)
                        self.assertGreaterEqual(int(stats_payload.get("completed", 0)), 3)

                anyio.run(exercise)

                persisted = json.loads(history_file.read_text(encoding="utf-8"))
                self.assertGreaterEqual(len(persisted), 3)
                self.assertTrue(all(item.get("status") == "completed" for item in persisted[-3:]))
            finally:
                stop_process(process)
                stop_process(native)


if __name__ == "__main__":
    unittest.main(verbosity=2)
