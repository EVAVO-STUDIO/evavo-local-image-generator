#!/usr/bin/env python3
"""Regression tests for MCP request validation before backend/task side effects."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from evavo_local_image_generator import mcp_server

ROOT = Path(__file__).resolve().parent


class McpRequestValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_wait_timeout_does_not_start_backend_or_create_task(self) -> None:
        ensure = AsyncMock()
        tracker = mcp_server._tracker()
        before = tracker.get_statistics()["total_tasks"]
        with patch.object(mcp_server, "_ensure", ensure):
            result = await mcp_server._generate_image_impl(
                "invalid wait should not start anything",
                wait_timeout=float("nan"),
                auto_start=True,
            )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "INVALID_FILE_OR_WAIT_POLICY")
        self.assertNotIn("task_id", result)
        ensure.assert_not_awaited()
        self.assertEqual(mcp_server._tracker().get_statistics()["total_tasks"], before)

    async def test_invalid_output_directory_does_not_start_backend(self) -> None:
        ensure = AsyncMock()
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "allowed"
            root.mkdir()
            outside = base / "outside"
            outside.mkdir()
            env = {
                "EVAVO_GENERATION_OUTPUT_DIR": str(root),
                "EVAVO_MCP_OUTPUT_ROOTS": "",
            }
            with patch.dict(os.environ, env, clear=False), patch.object(mcp_server, "_ensure", ensure):
                result = await mcp_server._generate_image_impl(
                    "invalid output should not start anything",
                    output_dir=str(outside),
                    wait=True,
                    auto_start=True,
                )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "INVALID_FILE_OR_WAIT_POLICY")
        ensure.assert_not_awaited()

    async def test_batch_file_policy_is_checked_before_backend_start(self) -> None:
        ensure = AsyncMock()
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "allowed"
            root.mkdir()
            outside = base / "outside"
            outside.mkdir()
            with patch.dict(
                os.environ,
                {"EVAVO_GENERATION_OUTPUT_DIR": str(root), "EVAVO_MCP_OUTPUT_ROOTS": ""},
                clear=False,
            ), patch.object(mcp_server, "_ensure", ensure):
                result = await mcp_server.generate_batch(
                    ["one"],
                    output_dir=str(outside),
                    auto_start=True,
                )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "INVALID_FILE_OR_WAIT_POLICY")
        ensure.assert_not_awaited()

    async def test_collect_invalid_timeout_is_checked_before_backend_start(self) -> None:
        ensure = AsyncMock()
        with patch.object(mcp_server, "_ensure", ensure):
            result = await mcp_server.collect_generation(
                "not-used",
                timeout=float("inf"),
                auto_start=True,
            )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "INVALID_OUTPUT_OR_TIMEOUT")
        ensure.assert_not_awaited()

    async def test_invalid_ensure_wait_is_structured_and_side_effect_free(self) -> None:
        with patch.object(mcp_server, "ensure_comfyui") as ensure_sync:
            result = await mcp_server.ensure_backend(auto_start=True, wait_seconds=float("nan"))
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "INVALID_WAIT_SECONDS")
        ensure_sync.assert_not_called()


class McpCliConfigValidationTests(unittest.TestCase):
    def test_invalid_environment_port_is_reported_by_argparse(self) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT)
        env["EVAVO_MCP_PORT"] = "not-a-port"
        result = subprocess.run(
            [sys.executable, "-m", "evavo_local_image_generator.mcp_server", "--transport", "streamable-http"],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )
        combined = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid int value", combined.lower())
        self.assertNotIn("Traceback (most recent call last)", combined)

    def test_invalid_http_path_is_rejected_before_server_start(self) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT)
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "evavo_local_image_generator.mcp_server",
                "--transport",
                "streamable-http",
                "--port",
                "18199",
                "--path",
                "/mcp?unsafe=1",
            ],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )
        combined = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must not contain ?, #, or NUL", combined)
        self.assertNotIn("Traceback (most recent call last)", combined)


if __name__ == "__main__":
    unittest.main(verbosity=2)
