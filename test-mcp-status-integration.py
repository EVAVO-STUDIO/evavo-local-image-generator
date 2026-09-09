#!/usr/bin/env python3
"""End-to-end MCP generation-status smoke test against the native simulator."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import anyio
from mcp import Client

ROOT = Path(__file__).resolve().parent
NATIVE_PORT = 18270
MCP_PORT = 18271


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


class McpStatusIntegrationTests(unittest.TestCase):
    def test_http_client_sees_completed_status_from_history_queue_contract(self) -> None:
        native = subprocess.Popen(
            [sys.executable, str(ROOT / "mock-comfyui-server.py"), "--port", str(NATIVE_PORT), "--native-only"],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        try:
            wait_port(NATIVE_PORT)
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                history = root / "history.json"
                output_root = root / "outputs"
                output_root.mkdir()
                env = os.environ.copy()
                env.update(
                    {
                        "PYTHONPATH": str(ROOT),
                        "PYTHONUNBUFFERED": "1",
                        "COMFYUI_ENDPOINT": f"http://127.0.0.1:{NATIVE_PORT}",
                        "EVAVO_TASK_HISTORY": str(history),
                        "EVAVO_GENERATION_OUTPUT_DIR": str(output_root),
                        "EVAVO_AUTO_PROVISION_COMFYUI": "0",
                    }
                )
                mcp = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "evavo_local_image_generator.mcp_server",
                        "--transport",
                        "streamable-http",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(MCP_PORT),
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
                    wait_port(MCP_PORT)

                    async def exercise() -> None:
                        async with Client(f"http://127.0.0.1:{MCP_PORT}/mcp") as client:
                            queued = await client.call_tool(
                                "generate_image",
                                {
                                    "prompt": "status integration smoke",
                                    "project_name": "status_smoke",
                                    "width": 512,
                                    "height": 512,
                                    "steps": 2,
                                    "wait": False,
                                    "auto_start": False,
                                },
                            )
                            payload = queued.structured_content
                            self.assertIsInstance(payload, dict)
                            assert isinstance(payload, dict)
                            self.assertTrue(payload.get("ok"), payload)
                            task_id = str(payload.get("task_id", ""))
                            self.assertTrue(task_id)

                            status_result = await client.call_tool(
                                "generation_status",
                                {"task_id": task_id, "auto_start": False},
                            )
                            status_payload = status_result.structured_content
                            self.assertIsInstance(status_payload, dict)
                            assert isinstance(status_payload, dict)
                            self.assertTrue(status_payload.get("ok"), status_payload)
                            self.assertEqual(status_payload.get("status"), "completed")
                            self.assertTrue(status_payload.get("history_present"))
                            self.assertEqual(status_payload.get("comfyui_status"), "success")
                            self.assertTrue(status_payload.get("outputs"))

                    anyio.run(exercise)
                finally:
                    stop_process(mcp)
        finally:
            stop_process(native)


if __name__ == "__main__":
    unittest.main(verbosity=2)
