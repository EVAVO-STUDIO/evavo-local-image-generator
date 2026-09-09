#!/usr/bin/env python3
"""Transport-level parity tests for Claude/ChatGPT MCP recovery controls."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import unittest
from pathlib import Path

import anyio
from mcp import Client, StdioServerParameters

ROOT = Path(__file__).resolve().parent
REQUIRED_RECOVERY_TOOLS = {
    "ensure_backend",
    "diagnose_backend",
    "last_startup_failure",
    "repair_backend_dependencies",
    "generation_status",
    "cancel_generation",
    "stop_managed_backend",
}


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
    raise RuntimeError(f"port {port} did not become ready")


def tool_names(result: object) -> set[str]:
    return {str(getattr(tool, "name", "")) for tool in getattr(result, "tools", [])}


class McpRecoveryParityTests(unittest.TestCase):
    def base_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT)
        env["PYTHONUNBUFFERED"] = "1"
        env["EVAVO_AUTO_PROVISION_COMFYUI"] = "0"
        return env

    def test_stdio_and_streamable_http_negotiate_same_recovery_controls(self) -> None:
        env = self.base_env()
        stdio = StdioServerParameters(
            command=sys.executable,
            args=["-m", "evavo_local_image_generator.mcp_server", "--transport", "stdio"],
            env=env,
        )
        port = free_port()
        http = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "evavo_local_image_generator.mcp_server",
                "--transport",
                "streamable-http",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
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
            wait_port(port)

            async def exercise() -> None:
                async with Client(stdio) as claude_client:
                    stdio_tools = tool_names(await claude_client.list_tools())
                async with Client(f"http://127.0.0.1:{port}/mcp") as chatgpt_client:
                    http_tools = tool_names(await chatgpt_client.list_tools())

                self.assertTrue(REQUIRED_RECOVERY_TOOLS.issubset(stdio_tools), sorted(REQUIRED_RECOVERY_TOOLS - stdio_tools))
                self.assertTrue(REQUIRED_RECOVERY_TOOLS.issubset(http_tools), sorted(REQUIRED_RECOVERY_TOOLS - http_tools))
                self.assertEqual(stdio_tools, http_tools)

            anyio.run(exercise)
        finally:
            if http.poll() is None:
                http.terminate()
                try:
                    http.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    http.kill()
                    http.wait(timeout=5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
