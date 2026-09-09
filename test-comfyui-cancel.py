#!/usr/bin/env python3
"""Tests for EVAVO's safe per-job ComfyUI cancellation contract."""

from __future__ import annotations

import io
import unittest
from unittest.mock import Mock, patch

from evavo_local_image_generator.backends import ComfyUIBackend
from evavo_local_image_generator.comfyui_cancel import cancel_prompt


class ComfyUICancelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = ComfyUIBackend("http://127.0.0.1:18199")

    def test_modern_pending_job_cancels_with_jobs_endpoint(self) -> None:
        before = {"task_id": "job-1", "status": "queued"}
        with patch("evavo_local_image_generator.comfyui_cancel.prompt_status", return_value=before), patch.object(
            self.backend, "_request", return_value={"cancelled": True}
        ) as request:
            result = cancel_prompt(self.backend, "job-1")
        self.assertTrue(result["ok"])
        self.assertTrue(result["cancelled"])
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["method"], "jobs_cancel")
        self.assertEqual(request.call_args.args[0], "/api/jobs/job-1/cancel")

    def test_modern_running_cancel_is_request_until_backend_confirms_terminal(self) -> None:
        states = [
            {"task_id": "job-2", "status": "running"},
            {"task_id": "job-2", "status": "running"},
        ]
        with patch("evavo_local_image_generator.comfyui_cancel.prompt_status", side_effect=states), patch.object(
            self.backend, "_request", return_value={"cancelled": True}
        ):
            result = cancel_prompt(self.backend, "job-2")
        self.assertTrue(result["ok"])
        self.assertTrue(result["cancel_requested"])
        self.assertFalse(result["cancelled"])
        self.assertEqual(result["status"], "cancel_requested")
        self.assertEqual(result["backend_status"], "running")

    def test_terminal_job_is_idempotent_noop(self) -> None:
        before = {"task_id": "job-3", "status": "completed"}
        with patch("evavo_local_image_generator.comfyui_cancel.prompt_status", return_value=before), patch.object(
            self.backend, "_request"
        ) as request:
            result = cancel_prompt(self.backend, "job-3")
        request.assert_not_called()
        self.assertTrue(result["ok"])
        self.assertFalse(result["cancel_requested"])
        self.assertEqual(result["status"], "completed")

    def test_legacy_pending_job_uses_exact_queue_delete(self) -> None:
        before = {"task_id": "job-4", "status": "queued"}
        response = io.BytesIO(b"")
        with patch("evavo_local_image_generator.comfyui_cancel.prompt_status", return_value=before), patch.object(
            self.backend, "_request", side_effect=RuntimeError("COMFYUI_HTTP_ERROR:404:no jobs api")
        ), patch.object(self.backend, "_open", return_value=response) as open_request:
            result = cancel_prompt(self.backend, "job-4")
        self.assertTrue(result["cancelled"])
        self.assertEqual(result["method"], "legacy_pending_queue_delete")
        self.assertEqual(open_request.call_args.args[0], "/queue")
        self.assertEqual(open_request.call_args.kwargs["payload"], {"delete": ["job-4"]})

    def test_legacy_running_job_never_uses_broad_interrupt(self) -> None:
        before = {"task_id": "job-5", "status": "running"}
        with patch("evavo_local_image_generator.comfyui_cancel.prompt_status", return_value=before), patch.object(
            self.backend, "_request", side_effect=RuntimeError("COMFYUI_HTTP_ERROR:404:no jobs api")
        ), patch.object(self.backend, "_open") as open_request:
            result = cancel_prompt(self.backend, "job-5")
        open_request.assert_not_called()
        self.assertFalse(result["ok"])
        self.assertFalse(result["cancel_requested"])
        self.assertEqual(result["error_code"], "COMFYUI_TARGETED_CANCEL_UNSUPPORTED")
        self.assertNotIn("/interrupt", str(result))

    def test_unknown_job_is_idempotent_noop(self) -> None:
        with patch("evavo_local_image_generator.comfyui_cancel.prompt_status", return_value={"task_id": "missing", "status": "unknown"}), patch.object(
            self.backend, "_request"
        ) as request:
            result = cancel_prompt(self.backend, "missing")
        request.assert_not_called()
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "unknown")
        self.assertFalse(result["cancel_requested"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
