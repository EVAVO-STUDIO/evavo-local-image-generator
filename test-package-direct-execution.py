#!/usr/bin/env python3
"""Prove package test files can execute directly from a clean-checkout path."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PACKAGE_TESTS = (
    ROOT / "evavo_local_image_generator" / "tests" / "test_backends.py",
    ROOT / "evavo_local_image_generator" / "tests" / "test_generators.py",
)


class DirectPackageTestExecutionTests(unittest.TestCase):
    def test_package_suites_import_without_external_pythonpath(self) -> None:
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        for path in PACKAGE_TESTS:
            with self.subTest(path=path.name):
                result = subprocess.run(
                    [sys.executable, str(path)],
                    cwd=str(ROOT),
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                self.assertEqual(result.returncode, 0, result.stderr or result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
