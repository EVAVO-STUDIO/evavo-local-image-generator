#!/usr/bin/env python3
"""Regression tests for legacy compatibility entry points."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

from claude_control import ClaudeController, GenerationStatus

ROOT = Path(__file__).resolve().parent


class LegacyCompatibilityTests(unittest.TestCase):
    def test_claude_controller_video_is_explicitly_unsupported(self) -> None:
        result = ClaudeController().generate_video_simple("legacy video request")
        self.assertEqual(result["status"], GenerationStatus.FAILED.value)
        self.assertEqual(result["error_code"], "NOT_IMPLEMENTED")
        self.assertNotIn(".mp4", str(result))

    def test_claude_controller_invalid_image_does_not_touch_backend(self) -> None:
        result = ClaudeController().generate_image_simple("   ")
        self.assertEqual(result["status"], GenerationStatus.FAILED.value)
        self.assertEqual(result["error_code"], "INVALID_PROMPT")
        self.assertNotIn("output", result)

    def test_autonomous_runner_requires_explicit_generation_request(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "run_autonomous.py")],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no longer starts surprise generation jobs", result.stderr + result.stdout)

    def test_historical_mcp_setup_delegates_to_canonical_installer(self) -> None:
        source = (ROOT / "SETUP-MCP-INTEGRATION.ps1").read_text(encoding="utf-8")
        self.assertIn("INSTALL-CLAUDE-MCP.ps1", source)
        for retired in ("KOKORO_ENDPOINT", "MODEL3D_ENDPOINT", "TEXTURE_ENDPOINT", "PARTICLE_ENDPOINT"):
            self.assertNotIn(retired, source)

    def test_start_everything_has_no_hidden_service_graph_or_generation(self) -> None:
        source = (ROOT / "START-EVERYTHING.ps1").read_text(encoding="utf-8")
        self.assertIn("UPDATE-AND-VERIFY-EVAVO.ps1", source)
        self.assertIn("evavo.py", source)
        self.assertNotIn("C:\\AI\\ComfyUI", source)
        self.assertNotIn("run_autonomous.py", source)
        self.assertNotIn("/models", source)

    def test_package_health_helper_is_native_image_only(self) -> None:
        source = (ROOT / "evavo_local_image_generator" / "tests" / "health_check.py").read_text(encoding="utf-8")
        self.assertIn("native_health", source)
        self.assertNotIn("ollama", source.lower())
        self.assertNotIn("kokoro", source.lower())
        self.assertNotIn("/api/models", source)

    def test_package_setup_validation_delegates_to_authoritative_verifier(self) -> None:
        source = (ROOT / "evavo_local_image_generator" / "tests" / "validate_setup.py").read_text(encoding="utf-8")
        self.assertIn("verify-evavo.py", source)
        self.assertNotIn("EVAVO_LOCAL_IMAGE_GENERATOR_STORAGE", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
