#!/usr/bin/env python3
"""End-to-end MCP targeted cancellation against the native ComfyUI simulator."""

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

import anyio
from mcp import Client

ROOT = Path(__file__).resolve().parent
NATIVE_PORT = 18272
MCP_PORT = 18273


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


def tool_names(result: object) -> set[str]:
    return {str(getattr(tool, "name", "")) for tool in getattr(result, "tools", [])}


class McpCancelIntegrationTests(unittest.TestCase):
    def test_pending_prompt_can_be_cancelled_without_stopping_renderer(self) -> None:
        native = subprocess.Popen(
            [
                sys.executable,
                str(ROOT / "mock-comfyui-server.py"),
                "--port",
                str(NATIVE_PORT),
                "--native-only",
                "--hold-prompts",
            ],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        try:
            wait_port(NATIVE_PORT)
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                output_root = root / "outputs"
                output_root.mkdir()
                history = root / "history.json"
                env = os.environ.copy()
                env.update(
                    {
                        "PYTHONPATH": str(ROOT),
                        "PYTHONUNBUFFERED": "1",
                        "COMFYUI_ENDPOINT": f"http://127.0.0.1:{NATIVE_PORT}",
                        "EVAVO_GENERATION_OUTPUT_DIR": str(output_root),
                        "EVAVO_TASK_HISTORY": str(history),
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
                            names = tool_names(await client.list_tools())
                            for name in ("cancel_generation", "diagnose_backend", "last_startup_failure"):
                                self.assertIn(name, names)

                            queued = await client.call_tool(
                                "generate_image",
                                {
                                    "prompt": "cancel this held EVAVO prompt",
                                    "project_name": "cancel_smoke",
                                    "width": 512,
                                    "height": 512,
                                    "steps": 2,
                                    "wait": False,
                                    "auto_start": False,
                                },
                            )
                            queued_payload = queued.structured_content
                            self.assertIsInstance(queued_payload, dict)
                            assert isinstance(queued_payload, dict)
                            task_id = str(queued_payload.get("task_id", ""))
                            self.assertTrue(task_id)

                            before = await client.call_tool("generation_status", {"task_id": task_id, "auto_start": False})
                            before_payload = before.structured_content
                            self.assertIsInstance(before_payload, dict)
                            assert isinstance(before_payload, dict)
                            self.assertEqual(before_payload.get("status"), "queued")

                            cancelled = await client.call_tool("cancel_generation", {"task_id": task_id, "auto_start": False})
                            cancelled_payload = cancelled.structured_content
                            self.assertIsInstance(cancelled_payload, dict)
                            assert isinstance(cancelled_payload, dict)
                            self.assertTrue(cancelled_payload.get("ok"), cancelled_payload)
                            self.assertTrue(cancelled_payload.get("cancel_requested"), cancelled_payload)
                            self.assertTrue(cancelled_payload.get("cancelled"), cancelled_payload)
                            self.assertEqual(cancelled_payload.get("status"), "cancelled")
                            self.assertEqual(cancelled_payload.get("method"), "jobs_cancel")

                            after = await client.call_tool("generation_status", {"task_id": task_id, "auto_start": False})
                            after_payload = after.structured_content
                            self.assertIsInstance(after_payload, dict)
                            assert isinstance(after_payload, dict)
                            self.assertEqual(after_payload.get("status"), "cancelled")
                            self.assertTrue(after_payload.get("job_api"))

                            again = await client.call_tool("cancel_generation", {"task_id": task_id, "auto_start": False})
                            again_payload = again.structured_content
                            self.assertIsInstance(again_payload, dict)
                            assert isinstance(again_payload, dict)
                            self.assertTrue(again_payload.get("ok"), again_payload)
                            self.assertEqual(again_payload.get("status"), "cancelled")
                            self.assertFalse(again_payload.get("cancel_requested"), again_payload)
                            self.assertEqual(again_payload.get("method"), "terminal_noop")

                            recent = await client.call_tool("task_history", {"limit": 20})
                            rows = recent.structured_content
                            self.assertIsInstance(rows, list)
                            assert isinstance(rows, list)
                            record = next((row for row in rows if isinstance(row, dict) and row.get("task_id") == task_id), None)
                            self.assertIsNotNone(record)
                            assert isinstance(record, dict)
                            self.assertEqual(record.get("status"), "cancelled")

                    anyio.run(exercise)
                    persisted = json.loads(history.read_text(encoding="utf-8"))
                    record = next(item for item in persisted if item.get("status") == "cancelled")
                    self.assertTrue(record.get("task_id"))
                finally:
                    stop_process(mcp)
        finally:
            stop_process(native)


if __name__ == "__main__":
    unittest.main(verbosity=2)
