#!/usr/bin/env python3
"""CLI argument-boundary tests for standalone ComfyUI dependency repair."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "repair-comfyui-dependencies.py"


class StandaloneRepairCliTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=20,
        )

    def test_non_finite_timeout_is_rejected_before_discovery(self) -> None:
        result = self.run_cli("--timeout", "nan")
        self.assertEqual(result.returncode, 64, result.stderr or result.stdout)
        self.assertIn('"status": "invalid_arguments"', result.stdout)
        self.assertIn("timeout must be finite", result.stdout)
        self.assertNotIn("Traceback (most recent call last)", result.stderr + result.stdout)

    def test_excessive_timeout_is_rejected_before_discovery(self) -> None:
        result = self.run_cli("--timeout", "3601")
        self.assertEqual(result.returncode, 64, result.stderr or result.stdout)
        self.assertIn('"status": "invalid_arguments"', result.stdout)
        self.assertIn("at most 3600", result.stdout)

    def test_unsafe_module_syntax_is_rejected_before_discovery(self) -> None:
        result = self.run_cli("--module", "requests;calc.exe")
        self.assertEqual(result.returncode, 64, result.stderr or result.stdout)
        self.assertIn('"status": "invalid_arguments"', result.stdout)
        self.assertIn("dotted Python import name", result.stdout)
        self.assertNotIn("Traceback (most recent call last)", result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
