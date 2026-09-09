#!/usr/bin/env python3
"""Regression tests for cancellation metadata in shared EVAVO task history."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from evavo_operations import TaskTracker


class TaskCancellationHistoryTests(unittest.TestCase):
    def test_running_cancel_request_preserves_non_terminal_status_and_audit_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            tracker = TaskTracker(Path(temp) / "history.json")
            tracker.add_task("prompt-1", "fixture", "running", project_name="cancel")
            updated = tracker.update_task(
                "prompt-1",
                "running",
                backend_mode="native-comfyui",
                cancel_requested_at="2026-09-09T21:00:00+10:00",
                cancel_method="jobs_cancel",
                backend_status="in_progress",
            )
            self.assertEqual(updated["status"], "running")
            self.assertEqual(updated["cancel_requested_at"], "2026-09-09T21:00:00+10:00")
            self.assertEqual(updated["cancel_method"], "jobs_cancel")
            self.assertEqual(updated["backend_status"], "in_progress")

            reloaded = TaskTracker(Path(temp) / "history.json").get_task("prompt-1")
            self.assertIsNotNone(reloaded)
            assert reloaded is not None
            self.assertEqual(reloaded["status"], "running")
            self.assertEqual(reloaded["cancel_method"], "jobs_cancel")

    def test_terminal_cancel_preserves_request_evidence_and_records_cancelled_at(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            tracker = TaskTracker(Path(temp) / "history.json")
            tracker.add_task(
                "prompt-2",
                "fixture",
                "running",
                cancel_requested_at="2026-09-09T21:00:00+10:00",
                cancel_method="jobs_cancel",
            )
            updated = tracker.update_task(
                "prompt-2",
                "cancelled",
                cancelled_at="2026-09-09T21:00:01+10:00",
                backend_status="cancelled",
            )
            self.assertEqual(updated["status"], "cancelled")
            self.assertEqual(updated["cancel_requested_at"], "2026-09-09T21:00:00+10:00")
            self.assertEqual(updated["cancel_method"], "jobs_cancel")
            self.assertEqual(updated["cancelled_at"], "2026-09-09T21:00:01+10:00")
            self.assertEqual(updated["backend_status"], "cancelled")
            stats = tracker.get_statistics()
            self.assertEqual(stats["cancelled"], 1)
            self.assertEqual(stats["running"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
