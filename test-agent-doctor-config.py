#!/usr/bin/env python3
"""Configuration parsing tests for agent-doctor.py."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOCTOR = ROOT / "agent-doctor.py"


class AgentDoctorConfigurationTests(unittest.TestCase):
    def test_canonical_comfyui_endpoint_wins_over_legacy_alias(self) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT)
        env["COMFYUI_ENDPOINT"] = "http://127.0.0.1:19181"
        env["EVAVO_COMFYUI_ENDPOINT"] = "http://127.0.0.1:29181"
        code = (
            "import importlib.util, pathlib; "
            f"p=pathlib.Path({str(DOCTOR)!r}); "
            "s=importlib.util.spec_from_file_location('agent_doctor_config', p); "
            "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
            "print(m.DEFAULT_ENDPOINT)"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertEqual(result.stdout.strip(), "http://127.0.0.1:19181")

    def test_invalid_environment_mcp_port_is_argparse_error_not_import_traceback(self) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT)
        env["EVAVO_MCP_PORT"] = "not-a-port"
        result = subprocess.run(
            [sys.executable, str(DOCTOR), "--skip-tests", "--json"],
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

    def test_source_declares_canonical_precedence(self) -> None:
        source = DOCTOR.read_text(encoding="utf-8")
        canonical = source.index('os.getenv("COMFYUI_ENDPOINT")')
        legacy = source.index('os.getenv("EVAVO_COMFYUI_ENDPOINT")')
        self.assertLess(canonical, legacy)


if __name__ == "__main__":
    unittest.main(verbosity=2)
