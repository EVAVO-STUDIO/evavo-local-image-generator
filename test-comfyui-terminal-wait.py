#!/usr/bin/env python3
"""Tests for terminal ComfyUI collection semantics and public jobs helpers."""

from __future__ import annotations

import io
import unittest
from unittest.mock import patch

from evavo_local_image_generator.backends import ComfyUIBackend


class ComfyUITerminalWaitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = ComfyUIBackend("http://127.0.0.1:18199")

    def test_terminal_error_without_messages_fails_immediately(self) -> None:
        history = {"p": {"outputs": {}, "status": {"status_str": "error", "completed": False, "messages": []}}}
        with patch.object(self.backend, "history", return_value=history) as history_call, patch("time.sleep") as sleep:
            with self.assertRaisesRegex(RuntimeError, "COMFYUI_EXECUTION_FAILED"):
                self.backend.wait_for_outputs("p", timeout=60, interval=1)
        history_call.assert_called_once_with("p")
        sleep.assert_not_called()

    def test_terminal_cancelled_fails_immediately(self) -> None:
        history = {"p": {"outputs": {}, "status": {"status_str": "cancelled", "completed": False, "messages": []}}}
        with patch.object(self.backend, "history", return_value=history), patch("time.sleep") as sleep:
            with self.assertRaisesRegex(RuntimeError, "COMFYUI_EXECUTION_CANCELLED"):
                self.backend.wait_for_outputs("p", timeout=60, interval=1)
        sleep.assert_not_called()

    def test_terminal_success_without_image_is_no_output_not_timeout(self) -> None:
        history = {"p": {"outputs": {}, "status": {"status_str": "success", "completed": True, "messages": []}}}
        with patch.object(self.backend, "history", return_value=history), patch("time.sleep") as sleep:
            with self.assertRaisesRegex(RuntimeError, "COMFYUI_NO_OUTPUT"):
                self.backend.wait_for_outputs("p", timeout=60, interval=1)
        sleep.assert_not_called()

    def test_public_job_and_queue_helpers_use_targeted_routes(self) -> None:
        with patch.object(self.backend, "_request", side_effect=[{"queue_running": [], "queue_pending": []}, {"id": "abc", "status": "pending"}, {"cancelled": True}]) as request:
            self.assertEqual(self.backend.queue_state()["queue_pending"], [])
            self.assertEqual(self.backend.job_detail("abc")["status"], "pending")
            self.assertTrue(self.backend.cancel_job("abc")["cancelled"])
        self.assertEqual(request.call_args_list[0].args[0], "/queue")
        self.assertEqual(request.call_args_list[1].args[0], "/api/jobs/abc")
        self.assertEqual(request.call_args_list[2].args[0], "/api/jobs/abc/cancel")
        self.assertEqual(request.call_args_list[2].kwargs["method"], "POST")

    def test_legacy_delete_pending_targets_only_requested_prompt(self) -> None:
        response = io.BytesIO(b"")
        with patch.object(self.backend, "_open", return_value=response) as open_request:
            self.backend.delete_pending("abc")
        self.assertEqual(open_request.call_args.args[0], "/queue")
        self.assertEqual(open_request.call_args.kwargs["method"], "POST")
        self.assertEqual(open_request.call_args.kwargs["payload"], {"delete": ["abc"]})


if __name__ == "__main__":
    unittest.main(verbosity=2)
