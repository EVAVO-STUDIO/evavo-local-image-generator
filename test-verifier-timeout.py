#!/usr/bin/env python3
"""Offline tests for EVAVO verifier timeout policy."""

from __future__ import annotations

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
VERIFIER = ROOT / "verify-evavo.py"


def load_verifier():
    spec = importlib.util.spec_from_file_location("evavo_verify_timeout_test", VERIFIER)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to import verifier")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class VerifierTimeoutTests(unittest.TestCase):
    def test_default_timeout_is_five_minutes_and_bounded(self) -> None:
        verifier = load_verifier()
        self.assertEqual(verifier.DEFAULT_TEST_TIMEOUT_SECONDS, 300.0)
        self.assertEqual(verifier._test_timeout(300), 300.0)
        for value in (0, 9.9, float("nan"), float("inf"), 1801):
            with self.subTest(value=value), self.assertRaises(ValueError):
                verifier._test_timeout(value)

    def test_run_tests_passes_selected_timeout_to_subprocess(self) -> None:
        verifier = load_verifier()
        with tempfile.TemporaryDirectory() as temp:
            test_file = Path(temp) / "test-timeout-fixture.py"
            test_file.write_text("raise SystemExit(0)\n", encoding="utf-8")
            original_root = verifier.ROOT
            verifier.ROOT = Path(temp)
            completed = subprocess.CompletedProcess(["python"], 0, stdout="ok\n", stderr="")
            try:
                with patch.object(verifier.subprocess, "run", return_value=completed) as run:
                    results = verifier.run_tests([test_file.name], timeout_seconds=42)
            finally:
                verifier.ROOT = original_root
        self.assertTrue(results[0]["ok"])
        self.assertEqual(run.call_args.kwargs["timeout"], 42.0)

    def test_timeout_expiry_has_stable_failure_detail(self) -> None:
        verifier = load_verifier()
        with tempfile.TemporaryDirectory() as temp:
            test_file = Path(temp) / "test-timeout-fixture.py"
            test_file.write_text("raise SystemExit(0)\n", encoding="utf-8")
            original_root = verifier.ROOT
            verifier.ROOT = Path(temp)
            try:
                with patch.object(verifier.subprocess, "run", side_effect=subprocess.TimeoutExpired(["python"], 25)):
                    results = verifier.run_tests([test_file.name], timeout_seconds=25)
            finally:
                verifier.ROOT = original_root
        self.assertFalse(results[0]["ok"])
        self.assertIn("timed out after 25 seconds", results[0]["detail"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
