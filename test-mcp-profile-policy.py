#!/usr/bin/env python3
"""Static contract tests for persistent Claude/HTTP MCP file-policy settings."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PERSISTED_POLICY = {
    "EVAVO_MCP_OUTPUT_ROOTS",
    "EVAVO_MCP_ALLOW_WORKFLOW_PATHS",
    "EVAVO_MCP_WORKFLOW_ROOT",
}


class McpProfilePolicyTests(unittest.TestCase):
    def test_claude_installer_persists_non_secret_owner_path_policy(self) -> None:
        source = (ROOT / "INSTALL-CLAUDE-MCP.ps1").read_text(encoding="utf-8")
        for name in PERSISTED_POLICY:
            with self.subTest(name=name):
                self.assertIn(f'"{name}"', source)
        self.assertNotIn('"EVAVO_CHECKPOINT_URL",', source)

    def test_http_autostart_persists_same_non_secret_owner_path_policy(self) -> None:
        source = (ROOT / "INSTALL-AGENT-MCP-AUTOSTART.ps1").read_text(encoding="utf-8")
        for name in PERSISTED_POLICY:
            with self.subTest(name=name):
                self.assertIn(f'"{name}"', source)
        self.assertNotIn('"EVAVO_CHECKPOINT_URL",', source)

    def test_mcp_server_enforces_workflow_and_output_roots(self) -> None:
        source = (ROOT / "evavo_local_image_generator" / "mcp_server.py").read_text(encoding="utf-8")
        self.assertIn("EVAVO_MCP_OUTPUT_ROOTS", source)
        self.assertIn("EVAVO_MCP_ALLOW_WORKFLOW_PATHS", source)
        self.assertIn("EVAVO_MCP_WORKFLOW_ROOT", source)
        self.assertIn("output_dir is outside EVAVO_GENERATION_OUTPUT_DIR/EVAVO_MCP_OUTPUT_ROOTS", source)
        self.assertIn("workflow_path is outside EVAVO_MCP_WORKFLOW_ROOT", source)
        self.assertIn("generated image content does not match", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
