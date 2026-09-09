#!/usr/bin/env python3
"""Stdlib-only tests for the project MCP bootstrap into the repo-local venv."""

from __future__ import annotations

import importlib.util
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
    def test_missing_venv_from_shared_authority_fails_with_setup_instruction(self) -> None:
        module = load_bootstrap()
        with patch.object(
            module,
            "inspect_venv",
            return_value={"ok": False, "status": "missing", "python": None, "message": None},
        ):
            with self.assertRaisesRegex(RuntimeError, "MCP_BOOTSTRAP_VENV_MISSING"):
                module._venv_python()

    def test_invalid_venv_from_shared_authority_fails_closed(self) -> None:
        module = load_bootstrap()
        with patch.object(
            module,
            "inspect_venv",
            return_value={"ok": False, "status": "invalid", "python": None, "message": "VENV_INVALID:test"},
        ):
            with self.assertRaisesRegex(RuntimeError, "MCP_BOOTSTRAP_INVALID_VENV"):
                module._venv_python()

    def test_validated_python_is_forwarded_exactly(self) -> None:
        module = load_bootstrap()
        expected = Path("C:/EVAVO/.venv/Scripts/python.exe")
        with patch.object(
            module,
            "inspect_venv",
            return_value={"ok": True, "status": "ready", "python": str(expected)},
        ):
            selected = module._venv_python()
        self.assertEqual(selected, expected)

    def test_validated_result_without_python_path_fails_closed(self) -> None:
        module = load_bootstrap()
        with patch.object(module, "inspect_venv", return_value={"ok": True, "status": "ready", "python": None}):
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

    def test_bootstrap_uses_shared_stdlib_venv_authority(self) -> None:
        source = BOOTSTRAP.read_text(encoding="utf-8")
        self.assertIn("from evavo_venv import inspect_venv", source)
        self.assertIn("inspect_venv(ROOT / \".venv\")", source)
        self.assertNotIn("from mcp", source)
        self.assertNotIn("import mcp", source)
        self.assertNotIn("requests", source)
        self.assertNotIn("subprocess", source)
        self.assertIn("os.chdir(ROOT)", source)
        self.assertIn("os.execv", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
