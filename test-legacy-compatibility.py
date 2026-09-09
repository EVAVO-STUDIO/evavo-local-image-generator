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

    def test_autonomous_runner_requires_explicit_generation_request_before_repair(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "run_autonomous.py")],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertNotEqual(result.returncode, 0)
        output = result.stderr + result.stdout
        self.assertIn("no longer starts surprise generation or provisioning jobs", output)
        self.assertNotIn("COMFYUI_NOT_FOUND", output)

    def test_shared_legacy_cli_requires_explicit_intent(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "legacy_image_cli.py")],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("provide --prompts or explicit --examples", result.stderr + result.stdout)

    def test_historical_mcp_setup_delegates_to_canonical_installer(self) -> None:
        source = (ROOT / "SETUP-MCP-INTEGRATION.ps1").read_text(encoding="utf-8")
        self.assertIn("INSTALL-CLAUDE-MCP.ps1", source)
        self.assertNotIn("$env:KOKORO_ENDPOINT", source)
        self.assertNotIn("$env:MODEL3D_ENDPOINT", source)
        self.assertNotIn("$env:TEXTURE_ENDPOINT", source)
        self.assertNotIn("$env:PARTICLE_ENDPOINT", source)

    def test_start_everything_delegates_without_hidden_generation(self) -> None:
        source = (ROOT / "START-EVERYTHING.ps1").read_text(encoding="utf-8")
        self.assertIn("UPDATE-AND-VERIFY-EVAVO.ps1", source)
        self.assertIn("evavo.py", source)
        self.assertNotIn("run_autonomous.py", source)
        self.assertNotIn("Start-Process", source)
        self.assertNotIn("Register-ScheduledTask", source)

    def test_package_health_helper_is_native_image_only(self) -> None:
        source = (ROOT / "evavo_local_image_generator" / "tests" / "health_check.py").read_text(encoding="utf-8")
        self.assertIn("native_health", source)
        self.assertNotIn("127.0.0.1:11434", source)
        self.assertNotIn("127.0.0.1:8000/api", source)
        self.assertNotIn("/api/models", source)

    def test_package_setup_validation_delegates_to_authoritative_verifier(self) -> None:
        source = (ROOT / "evavo_local_image_generator" / "tests" / "validate_setup.py").read_text(encoding="utf-8")
        self.assertIn("verify-evavo.py", source)
        self.assertNotIn("EVAVO_LOCAL_IMAGE_GENERATOR_STORAGE", source)

    def test_destructive_source_regenerators_are_retired(self) -> None:
        setup = (ROOT / "setup-production.py").read_text(encoding="utf-8")
        package = (ROOT / "create-complete-production.py").read_text(encoding="utf-8")
        self.assertIn("no longer rewrites repository files", setup)
        self.assertIn("source regeneration has been retired", package)
        for source in (setup, package):
            self.assertNotIn("PRODUCTION_FILES =", source)
            self.assertNotIn("files = {", source)
            self.assertNotIn("EvavoLocalImageGeneratorMCPServer", source)

    def test_fake_autonomous_demo_is_removed(self) -> None:
        source = (ROOT / "demo_autonomous.py").read_text(encoding="utf-8")
        self.assertIn("legacy_image_cli", source)
        self.assertNotIn("MOCK_VIDEO_DATA", source)
        self.assertNotIn("write_bytes", source)

    def test_generate_now_batch_does_not_kill_python_or_start_services(self) -> None:
        source = (ROOT / "EVAVO-GENERATE-NOW.bat").read_text(encoding="utf-8").lower()
        self.assertIn("legacy_image_cli.py", source)
        self.assertNotIn("taskkill /f /im python.exe", source)
        self.assertNotIn("ollama serve", source)
        self.assertNotIn("kokoro-fastapi", source)
        self.assertNotIn("start \"\" cmd /c", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
