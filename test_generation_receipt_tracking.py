"""Offline tests for durable generation receipts in task history."""

from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path

from evavo_operations import GENERATION_RECEIPT_MAX_BYTES, TaskTracker


class GenerationReceiptTrackingTests(unittest.TestCase):
    def test_add_and_update_generation_receipt(self):
        with tempfile.TemporaryDirectory() as value:
            history = Path(value) / "history.json"
            tracker = TaskTracker(history)
            created = tracker.add_task(
                "task-1",
                "fixture",
                generation_receipt={
                    "seed": 1337,
                    "quality_profile": "hero",
                    "workflow_sha256": "a" * 64,
                    "render_passes": 2,
                },
            )
            self.assertEqual(created["generation_receipt"]["seed"], 1337)
            self.assertEqual(created["generation_receipt"]["quality_profile"], "hero")

            updated = tracker.update_task(
                "task-1",
                "completed",
                generation_receipt={
                    "seed": 1337,
                    "quality_profile": "hero",
                    "workflow_sha256": "b" * 64,
                    "output_width": 1536,
                    "output_height": 1536,
                },
            )
            self.assertEqual(updated["status"], "completed")
            self.assertEqual(updated["generation_receipt"]["workflow_sha256"], "b" * 64)
            self.assertEqual(TaskTracker(history).get_task("task-1")["generation_receipt"]["output_width"], 1536)

    def test_non_finite_receipt_fails_closed(self):
        with tempfile.TemporaryDirectory() as value:
            tracker = TaskTracker(Path(value) / "history.json")
            with self.assertRaisesRegex(ValueError, "finite JSON"):
                tracker.add_task("task-1", "fixture", generation_receipt={"cfg": math.nan})

    def test_oversized_receipt_fails_closed(self):
        with tempfile.TemporaryDirectory() as value:
            tracker = TaskTracker(Path(value) / "history.json")
            with self.assertRaisesRegex(ValueError, "exceeds"):
                tracker.add_task(
                    "task-1",
                    "fixture",
                    generation_receipt={"payload": "x" * (GENERATION_RECEIPT_MAX_BYTES + 1000)},
                )

    def test_receipt_can_be_removed_explicitly(self):
        with tempfile.TemporaryDirectory() as value:
            history = Path(value) / "history.json"
            tracker = TaskTracker(history)
            tracker.add_task("task-1", "fixture", generation_receipt={"seed": 1})
            updated = tracker.update_task("task-1", "queued", generation_receipt=None)
            self.assertNotIn("generation_receipt", updated)


if __name__ == "__main__":
    unittest.main(verbosity=2)
