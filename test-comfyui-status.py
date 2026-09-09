#!/usr/bin/env python3
"""Tests for normalized ComfyUI jobs/history/queue state and MCP reconciliation."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, Mock, patch

from evavo_local_image_generator.backends import ComfyUIBackend
from evavo_local_image_generator.comfyui_status import prompt_status
from evavo_local_image_generator import mcp_server


class ComfyUIStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = ComfyUIBackend("http://127.0.0.1:18199")

    def legacy(self, history: dict, queue: dict):
        return (
            patch.object(self.backend, "job_detail", return_value=None),
            patch.object(self.backend, "history", return_value=history),
            patch.object(self.backend, "queue_state", return_value=queue),
        )

    def test_completed_history_with_output_legacy_fallback(self) -> None:
        history = {
            "prompt-1": {
                "outputs": {"7": {"images": [{"filename": "out.png", "subfolder": "", "type": "output"}]}},
                "status": {"status_str": "success", "completed": True, "messages": []},
            }
        }
        job, hist, queue = self.legacy(history, {"queue_running": [], "queue_pending": []})
        with job, hist, queue:
            state = prompt_status(self.backend, "prompt-1")
        self.assertEqual(state["status"], "completed")
        self.assertFalse(state["job_api"])
        self.assertEqual(state["outputs"][0]["filename"], "out.png")

    def test_failed_history_is_not_reported_as_queued_legacy_fallback(self) -> None:
        messages = [["execution_error", {"exception_message": "CUDA out of memory"}]]
        history = {"prompt-2": {"outputs": {}, "status": {"status_str": "error", "completed": False, "messages": messages}}}
        job, hist, queue = self.legacy(history, {"queue_running": [], "queue_pending": []})
        with job, hist, queue:
            state = prompt_status(self.backend, "prompt-2")
        self.assertEqual(state["status"], "failed")
        self.assertEqual(state["messages"], messages)

    def test_running_queue_is_reported_running_on_legacy_server(self) -> None:
        job, hist, queue = self.legacy({}, {"queue_running": [[1, "prompt-3", {}, {}, []]], "queue_pending": []})
        with job, hist, queue:
            state = prompt_status(self.backend, "prompt-3")
        self.assertEqual(state["status"], "running")
        self.assertFalse(state["history_present"])

    def test_pending_queue_is_reported_queued_on_legacy_server(self) -> None:
        job, hist, queue = self.legacy({}, {"queue_running": [], "queue_pending": [[2, "prompt-4", {}, {}, []]]})
        with job, hist, queue:
            state = prompt_status(self.backend, "prompt-4")
        self.assertEqual(state["status"], "queued")

    def test_unknown_prompt_is_not_invented_as_queued(self) -> None:
        job, hist, queue = self.legacy({}, {"queue_running": [], "queue_pending": []})
        with job, hist, queue:
            state = prompt_status(self.backend, "missing")
        self.assertEqual(state["status"], "unknown")

    def test_terminal_success_without_image_is_completed_for_status_layer(self) -> None:
        history = {"prompt-5": {"outputs": {}, "status": {"status_str": "success", "completed": True, "messages": []}}}
        job, hist, queue = self.legacy(history, {"queue_running": [], "queue_pending": []})
        with job, hist, queue:
            state = prompt_status(self.backend, "prompt-5")
        self.assertEqual(state["status"], "completed")
        self.assertEqual(state["outputs"], [])

    def test_current_jobs_api_reports_cancelled(self) -> None:
        with patch.object(
            self.backend,
            "job_detail",
            return_value={"id": "job-1", "status": "cancelled", "error_message": None},
        ), patch.object(self.backend, "history") as history, patch.object(self.backend, "queue_state") as queue:
            state = prompt_status(self.backend, "job-1")
        self.assertEqual(state["status"], "cancelled")
        self.assertTrue(state["job_api"])
        history.assert_not_called()
        queue.assert_not_called()

    def test_current_jobs_api_reports_running_without_legacy_queue_lookup(self) -> None:
        with patch.object(
            self.backend,
            "job_detail",
            return_value={"id": "job-2", "status": "in_progress", "error_message": None},
        ), patch.object(self.backend, "history") as history, patch.object(self.backend, "queue_state") as queue:
            state = prompt_status(self.backend, "job-2")
        self.assertEqual(state["status"], "running")
        self.assertTrue(state["job_api"])
        history.assert_not_called()
        queue.assert_not_called()

    def test_current_jobs_api_reports_error_and_preserves_message(self) -> None:
        with patch.object(
            self.backend,
            "job_detail",
            return_value={"id": "job-3", "status": "error", "error_message": "CUDA out of memory"},
        ), patch.object(self.backend, "history", return_value={}):
            state = prompt_status(self.backend, "job-3")
        self.assertEqual(state["status"], "failed")
        self.assertEqual(state["error_message"], "CUDA out of memory")
        self.assertTrue(state["messages"])


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
            "job_api": True,
            "comfyui_status": "error",
            "completed": True,
            "messages": [["execution_error", {"exception_message": "boom"}]],
            "error_message": "boom",
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
        self.assertEqual(track.await_args.args[1], "failed")
        self.assertEqual(track.await_args.kwargs["error_code"], "COMFYUI_EXECUTION_FAILED")

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
                    "job_api": False,
                    "comfyui_status": None,
                    "completed": None,
                    "messages": [],
                    "error_message": None,
                },
            ),
            patch.object(mcp_server, "_track_update", AsyncMock(return_value=None)) as track,
        ):
            result = await mcp_server.generation_status("missing", auto_start=False)
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(track.await_args.args[1], "unknown")

    async def test_mcp_cancelled_status_reconciles_as_cancelled(self) -> None:
        with (
            patch.object(mcp_server, "_ensure", AsyncMock()),
            patch.object(mcp_server, "_backend", return_value=Mock()),
            patch.object(
                mcp_server,
                "prompt_status",
                return_value={
                    "task_id": "cancelled",
                    "status": "cancelled",
                    "outputs": [],
                    "history_present": False,
                    "job_api": True,
                    "comfyui_status": "cancelled",
                    "completed": True,
                    "messages": [],
                    "error_message": None,
                },
            ),
            patch.object(mcp_server, "_track_update", AsyncMock(return_value=None)) as track,
        ):
            result = await mcp_server.generation_status("cancelled", auto_start=False)
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(track.await_args.args[1], "cancelled")


if __name__ == "__main__":
    unittest.main(verbosity=2)
