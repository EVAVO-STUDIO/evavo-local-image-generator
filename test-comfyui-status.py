#!/usr/bin/env python3
"""Tests for normalized ComfyUI history/queue state and MCP reconciliation."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, Mock, patch

from evavo_local_image_generator.backends import ComfyUIBackend
from evavo_local_image_generator.comfyui_status import prompt_status
from evavo_local_image_generator import mcp_server


class ComfyUIStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = ComfyUIBackend("http://127.0.0.1:18199")

    def test_completed_history_with_output(self) -> None:
        history = {
            "prompt-1": {
                "outputs": {"7": {"images": [{"filename": "out.png", "subfolder": "", "type": "output"}]}},
                "status": {"status_str": "success", "completed": True, "messages": []},
            }
        }
        with patch.object(self.backend, "history", return_value=history), patch.object(self.backend, "_request") as queue:
            state = prompt_status(self.backend, "prompt-1")
        self.assertEqual(state["status"], "completed")
        self.assertEqual(state["outputs"][0]["filename"], "out.png")
        queue.assert_not_called()

    def test_failed_history_is_not_reported_as_queued(self) -> None:
        messages = [["execution_error", {"exception_message": "CUDA out of memory"}]]
        history = {
            "prompt-2": {
                "outputs": {},
                "status": {"status_str": "error", "completed": False, "messages": messages},
            }
        }
        with patch.object(self.backend, "history", return_value=history), patch.object(self.backend, "_request") as queue:
            state = prompt_status(self.backend, "prompt-2")
        self.assertEqual(state["status"], "failed")
        self.assertEqual(state["messages"], messages)
        queue.assert_not_called()

    def test_running_queue_is_reported_running(self) -> None:
        with patch.object(self.backend, "history", return_value={}), patch.object(
            self.backend,
            "_request",
            return_value={"queue_running": [[1, "prompt-3", {}, {}, []]], "queue_pending": []},
        ):
            state = prompt_status(self.backend, "prompt-3")
        self.assertEqual(state["status"], "running")
        self.assertFalse(state["history_present"])

    def test_pending_queue_is_reported_queued(self) -> None:
        with patch.object(self.backend, "history", return_value={}), patch.object(
            self.backend,
            "_request",
            return_value={"queue_running": [], "queue_pending": [[2, "prompt-4", {}, {}, []]]},
        ):
            state = prompt_status(self.backend, "prompt-4")
        self.assertEqual(state["status"], "queued")

    def test_unknown_prompt_is_not_invented_as_queued(self) -> None:
        with patch.object(self.backend, "history", return_value={}), patch.object(
            self.backend,
            "_request",
            return_value={"queue_running": [], "queue_pending": []},
        ):
            state = prompt_status(self.backend, "missing")
        self.assertEqual(state["status"], "unknown")

    def test_terminal_success_without_image_is_completed_for_status_layer(self) -> None:
        history = {"prompt-5": {"outputs": {}, "status": {"status_str": "success", "completed": True, "messages": []}}}
        with patch.object(self.backend, "history", return_value=history):
            state = prompt_status(self.backend, "prompt-5")
        self.assertEqual(state["status"], "completed")
        self.assertEqual(state["outputs"], [])


class McpStatusReconciliationTests(unittest.IsolatedAsyncioTestCase):
    async def test_mcp_failed_status_updates_history_as_failed(self) -> None:
        ensure = AsyncMock()
        track = AsyncMock(return_value=None)
        backend = Mock()
        state = {
            "task_id": "prompt-failed",
            "status": "failed",
            "outputs": [],
            "history_present": True,
            "comfyui_status": "error",
            "completed": False,
            "messages": [["execution_error", {"exception_message": "boom"}]],
        }
        with (
            patch.object(mcp_server, "_ensure", ensure),
            patch.object(mcp_server, "_backend", return_value=backend),
            patch.object(mcp_server, "prompt_status", return_value=state),
            patch.object(mcp_server, "_track_update", track),
        ):
            result = await mcp_server.generation_status("prompt-failed", auto_start=False)
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "COMFYUI_EXECUTION_FAILED")
        ensure.assert_awaited_once_with(auto_start=False)
        track.assert_awaited_once()
        args = track.await_args
        self.assertEqual(args.args[0], "prompt-failed")
        self.assertEqual(args.args[1], "failed")
        self.assertEqual(args.kwargs["error_code"], "COMFYUI_EXECUTION_FAILED")

    async def test_mcp_unknown_status_reconciles_as_unknown(self) -> None:
        with (
            patch.object(mcp_server, "_ensure", AsyncMock()),
            patch.object(mcp_server, "_backend", return_value=Mock()),
            patch.object(
                mcp_server,
                "prompt_status",
                return_value={
                    "task_id": "missing",
                    "status": "unknown",
                    "outputs": [],
                    "history_present": False,
                    "comfyui_status": None,
                    "completed": None,
                    "messages": [],
                },
            ),
            patch.object(mcp_server, "_track_update", AsyncMock(return_value=None)) as track,
        ):
            result = await mcp_server.generation_status("missing", auto_start=False)
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(track.await_args.args[1], "unknown")


if __name__ == "__main__":
    unittest.main(verbosity=2)
