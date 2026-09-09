#!/usr/bin/env python3
"""Stdlib-only tests for the project MCP bootstrap into the repo-local venv."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
BOOTSTRAP = ROOT / "mcp-bootstrap.py"


def load_bootstrap():
    spec = importlib.util.spec_from_file_location("evavo_mcp_bootstrap_test", BOOTSTRAP)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load mcp-bootstrap.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class McpBootstrapTests(unittest.TestCase):
    def test_missing_venv_fails_with_setup_instruction(self) -> None:
        module = load_bootstrap()
        with tempfile.TemporaryDirectory() as temp, patch.object(module, "ROOT", Path(temp)):
            with self.assertRaisesRegex(RuntimeError, "MCP_BOOTSTRAP_VENV_MISSING"):
                module._venv_python()

    def test_windows_style_venv_python_is_selected_as_ordinary_file(self) -> None:
        module = load_bootstrap()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            python = root / ".venv" / "Scripts" / "python.exe"
            python.parent.mkdir(parents=True)
            python.write_bytes(b"fixture")
            with patch.object(module, "ROOT", root):
                selected = module._venv_python()
        self.assertEqual(selected, python.resolve())

    def test_posix_style_venv_python_is_selected_as_fallback(self) -> None:
        module = load_bootstrap()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            python = root / ".venv" / "bin" / "python"
            python.parent.mkdir(parents=True)
            python.write_bytes(b"fixture")
            with patch.object(module, "ROOT", root):
                selected = module._venv_python()
        self.assertEqual(selected, python.resolve())

    def test_symlinked_venv_is_rejected_when_supported(self) -> None:
        module = load_bootstrap()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            actual = root / "actual-venv"
            actual.mkdir()
            link = root / ".venv"
            try:
                link.symlink_to(actual, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation is unavailable on this host")
            with patch.object(module, "ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "MCP_BOOTSTRAP_INVALID_VENV"):
                    module._venv_python()

    def test_main_normalizes_repo_cwd_then_execs_exact_venv_python_into_validated_entry(self) -> None:
        module = load_bootstrap()
        fake_python = Path("C:/EVAVO/.venv/Scripts/python.exe")
        fake_root = Path("C:/EVAVO")
        with (
            patch.object(module, "ROOT", fake_root),
            patch.object(module, "_venv_python", return_value=fake_python),
            patch.object(module.sys, "argv", ["mcp-bootstrap.py", "--transport", "stdio"]),
            patch.object(module.os, "chdir") as chdir,
            patch.object(module.os, "execv") as execv,
        ):
            module.main()
        chdir.assert_called_once_with(fake_root)
        execv.assert_called_once_with(
            str(fake_python),
            [
                str(fake_python),
                "-m",
                "evavo_local_image_generator.mcp_entry",
                "--transport",
                "stdio",
            ],
        )

    def test_bootstrap_is_stdlib_only(self) -> None:
        source = BOOTSTRAP.read_text(encoding="utf-8")
        self.assertNotIn("from mcp", source)
        self.assertNotIn("import mcp", source)
        self.assertNotIn("requests", source)
        self.assertNotIn("subprocess", source)
        self.assertIn("os.chdir(ROOT)", source)
        self.assertIn("os.execv", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
