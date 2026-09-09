#!/usr/bin/env python3
"""Stdlib-only tests for EVAVO repository virtual-environment authority."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import evavo_venv


class EvavoVenvRuntimeTests(unittest.TestCase):
    def test_missing_venv_is_read_only_missing_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / ".venv"
            result = evavo_venv.inspect_venv(root)
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "missing")
        self.assertFalse(root.exists())

    def test_existing_non_venv_directory_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / ".venv"
            root.mkdir()
            (root / "important.txt").write_text("do not delete\n", encoding="utf-8")
            with patch.object(evavo_venv.subprocess, "run") as run:
                result = evavo_venv.ensure_venv(root=root, bootstrap_python=sys.executable)
            run.assert_not_called()
            self.assertFalse(result["ok"])
            self.assertEqual(result["status"], "invalid")
            self.assertTrue((root / "important.txt").is_file())

    def test_ordinary_fixture_venv_is_ready_without_probe(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / ".venv"
            python = root / "Scripts" / "python.exe"
            python.parent.mkdir(parents=True)
            python.write_bytes(b"fixture")
            (root / "pyvenv.cfg").write_text("home = fixture\n", encoding="utf-8")
            result = evavo_venv.inspect_venv(root, probe=False)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(Path(result["python"]), python.resolve())

    def test_symlinked_venv_is_rejected_when_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            actual = base / "actual"
            actual.mkdir()
            link = base / ".venv"
            try:
                link.symlink_to(actual, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation unavailable")
            result = evavo_venv.inspect_venv(link, probe=False)
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "invalid")
        self.assertIn("symlink", result["message"].lower())

    def test_ensure_missing_venv_runs_only_version_probe_and_python_m_venv(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / ".venv"
            missing = {"ok": False, "status": "missing", "venv": str(root), "python": None}
            ready = {
                "ok": True,
                "status": "ready",
                "venv": str(root),
                "python": str(root / "Scripts" / "python.exe"),
            }
            version = subprocess.CompletedProcess([], 0, stdout="", stderr="")
            created = subprocess.CompletedProcess([], 0, stdout="", stderr="")
            with (
                patch.object(evavo_venv, "inspect_venv", side_effect=[missing, ready]),
                patch.object(evavo_venv.subprocess, "run", side_effect=[version, created]) as run,
            ):
                result = evavo_venv.ensure_venv(root=root, bootstrap_python=sys.executable)
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["created"])
        self.assertEqual(run.call_count, 2)
        create_command = run.call_args_list[1].args[0]
        self.assertEqual(create_command[1:3], ["-m", "venv"])
        self.assertEqual(Path(create_command[3]), root.absolute())

    def test_redirected_bootstrap_python_is_rejected_when_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            actual = base / "python-real"
            actual.write_bytes(b"fixture")
            link = base / "python-link"
            try:
                link.symlink_to(actual)
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation unavailable")
            root = base / ".venv"
            with patch.object(
                evavo_venv,
                "inspect_venv",
                return_value={"ok": False, "status": "missing", "venv": str(root), "python": None},
            ), patch.object(evavo_venv.subprocess, "run") as run:
                result = evavo_venv.ensure_venv(root=root, bootstrap_python=link)
            run.assert_not_called()
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "bootstrap_invalid")

    def test_module_never_installs_packages_or_deletes_existing_venv(self) -> None:
        source = Path(evavo_venv.__file__).read_text(encoding="utf-8")
        self.assertNotIn("pip install", source)
        self.assertNotIn("shutil.rmtree", source)
        self.assertNotIn("rmtree(", source)
        self.assertNotIn("unlink(", source)
        self.assertIn('"-m", "venv"', source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
