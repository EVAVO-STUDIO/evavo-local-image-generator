#!/usr/bin/env python3
"""Offline tests for the historical ClaudeController compatibility API."""

from __future__ import annotations

import json
import unittest

from claude_control import ClaudeController, GenerationStatus


class AutonomousCompatibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.controller = ClaudeController("http://127.0.0.1:18199")

    def test_controller_initialization(self) -> None:
        self.assertEqual(self.controller.base_url, "http://127.0.0.1:18199")
        self.assertEqual(self.controller.results_cache, [])
        self.assertEqual(self.controller.execution_log, [])

    def test_invalid_image_prompt_fails_offline(self) -> None:
        result = self.controller.generate_image_simple("   ")
        self.assertEqual(result["status"], GenerationStatus.FAILED.value)
        self.assertEqual(result["error_code"], "INVALID_PROMPT")
        self.assertNotIn("output", result)

    def test_video_is_explicitly_unsupported(self) -> None:
        result = self.controller.generate_video_simple("Test video", length="short")
        self.assertEqual(result["status"], GenerationStatus.FAILED.value)
        self.assertEqual(result["error_code"], "NOT_IMPLEMENTED")
        self.assertEqual(result["length"], "short")
        self.assertNotIn("request_id", result)

    def test_statistics_include_failures(self) -> None:
        self.controller.generate_image_simple("")
        self.controller.generate_video_simple("not supported")
        stats = self.controller.get_stats()
        self.assertEqual(stats["total_generations"], 2)
        self.assertEqual(stats["successful"], 0)
        self.assertEqual(stats["failed"], 2)

    def test_json_export_is_valid(self) -> None:
        self.controller.generate_image_simple("")
        report = json.loads(self.controller.export_results(format="json"))
        self.assertIn("generated_at", report)
        self.assertIn("statistics", report)
        self.assertEqual(report["statistics"]["failed"], 1)

    def test_text_export_describes_image_generation(self) -> None:
        report = self.controller.export_results(format="text")
        self.assertIn("EVAVO Image Generation Report", report)

    def test_action_logging(self) -> None:
        self.controller.log_action("test_action", {"detail": "value"})
        self.assertEqual(self.controller.execution_log[0]["action"], "test_action")
        self.assertEqual(self.controller.execution_log[0]["details"]["detail"], "value")


if __name__ == "__main__":
    unittest.main(verbosity=2)
