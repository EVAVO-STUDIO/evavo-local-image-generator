#!/usr/bin/env python3
"""Regression tests for the authoritative verifier's suite discovery."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VERIFIER_PATH = ROOT / "verify-evavo.py"


def load_verifier():
    spec = importlib.util.spec_from_file_location("evavo_verify_module", VERIFIER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load verify-evavo.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class VerifierDiscoveryTests(unittest.TestCase):
    def test_discovers_root_hyphen_underscore_and_package_suites(self) -> None:
        verifier = load_verifier()
        tests = set(verifier.discover_tests())
        self.assertIn("test-capability-manifest.py", tests)
        self.assertIn("test-gateway.py", tests)
        self.assertIn("test-legacy-compatibility.py", tests)
        self.assertIn("test-package-direct-execution.py", tests)
        self.assertIn("test-agent-stop-safety.py", tests)
        self.assertIn("test_autonomous.py", tests)
        self.assertIn("evavo_local_image_generator/tests/test_backends.py", tests)
        self.assertIn("evavo_local_image_generator/tests/test_generators.py", tests)

    def test_test_inventory_is_deterministic_and_unique(self) -> None:
        verifier = load_verifier()
        tests = verifier.discover_tests()
        self.assertEqual(tests, sorted(tests))
        self.assertEqual(len(tests), len(set(tests)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
