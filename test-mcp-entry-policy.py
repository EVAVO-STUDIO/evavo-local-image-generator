#!/usr/bin/env python3
"""Contract tests for the policy-validated production MCP entrypoint."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evavo_local_image_generator import mcp_entry

ROOT = Path(__file__).resolve().parent


class McpEntryPolicyTests(unittest.TestCase):
    def test_invalid_policy_is_rejected_before_server_import(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            missing = Path(temp) / "missing-output-root"
            env = os.environ.copy()
            env["PYTHONPATH"] = str(ROOT)
            env["EVAVO_GENERATION_OUTPUT_DIR"] = str(Path(temp) / "default")
            env["EVAVO_MCP_OUTPUT_ROOTS"] = str(missing)
            result = subprocess.run(
                [sys.executable, "-m", "evavo_local_image_generator.mcp_entry", "--transport", "stdio"],
                cwd=str(ROOT),
                env=env,
                capture_output=True,
                text=True,
                timeout=15,
            )
        self.assertEqual(result.returncode, 78, result.stderr or result.stdout)
        self.assertIn("MCP_POLICY_INVALID", result.stderr)
        self.assertIn("EVAVO_MCP_OUTPUT_ROOTS", result.stderr)
        self.assertNotIn("MCP SDK is required", result.stderr)

    def test_validation_function_fails_closed(self) -> None:
        with patch.object(
            mcp_entry,
            "validate_environment",
            return_value={"ok": False, "errors": ["denied"], "warnings": [], "policy": {}},
        ):
            with self.assertRaisesRegex(RuntimeError, "MCP_POLICY_INVALID:denied"):
                mcp_entry.validate_startup_policy()

    def test_entry_imports_server_only_after_policy_validation(self) -> None:
        source = (ROOT / "evavo_local_image_generator" / "mcp_entry.py").read_text(encoding="utf-8")
        validate_call = source.index("policy = validate_startup_policy()")
        server_import = source.index("from .mcp_server import main as server_main")
        self.assertLess(validate_call, server_import)

    def test_package_module_entry_uses_validated_mcp_entry(self) -> None:
        source = (ROOT / "evavo_local_image_generator" / "__main__.py").read_text(encoding="utf-8")
        self.assertIn("from .mcp_entry import main", source)
        self.assertNotIn("from .mcp_server import main", source)

    def test_supported_profiles_use_validated_entry(self) -> None:
        root_profile = (ROOT / ".mcp.json").read_text(encoding="utf-8")
        claude = (ROOT / "INSTALL-CLAUDE-MCP.ps1").read_text(encoding="utf-8")
        http = (ROOT / "START-AGENT-MCP.ps1").read_text(encoding="utf-8")
        for name, source in (("root", root_profile), ("claude", claude), ("http", http)):
            with self.subTest(name=name):
                self.assertIn("evavo_local_image_generator.mcp_entry", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
