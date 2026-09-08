#!/usr/bin/env python3
"""Agent-facing integration tests for Claude/ChatGPT-compatible MCP operation."""

from __future__ import annotations

import importlib
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HTTP_PORT = 18192


def wait_port(port: int, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"port {port} did not become ready")


class AgentIntegrationTests(unittest.TestCase):
    def test_mcp_module_imports_and_registers_server(self) -> None:
        module = importlib.import_module("evavo_local_image_generator.mcp_server")
        self.assertTrue(hasattr(module, "mcp"))
        self.assertTrue(callable(module.main))

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

    def test_mcp_stdio_process_stays_alive(self) -> None:
        process = subprocess.Popen(
            [sys.executable, "-m", "evavo_local_image_generator.mcp_server", "--transport", "stdio"],
            cwd=str(ROOT),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            time.sleep(0.75)
            self.assertIsNone(process.poll(), "stdio MCP server exited unexpectedly")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    def test_mcp_streamable_http_starts_on_loopback(self) -> None:
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
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        try:
            wait_port(HTTP_PORT)
            self.assertIsNone(process.poll(), "HTTP MCP server exited unexpectedly")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
