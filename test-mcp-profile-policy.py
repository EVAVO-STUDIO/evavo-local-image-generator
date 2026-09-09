#!/usr/bin/env python3
"""Static contract tests for persistent Claude/HTTP MCP policy settings."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PERSISTED_POLICY = {
    "EVAVO_MCP_OUTPUT_ROOTS",
    "EVAVO_MCP_ALLOW_WORKFLOW_PATHS",
    "EVAVO_MCP_WORKFLOW_ROOT",
}


def assert_profile_contract(test: unittest.TestCase, source: str) -> None:
    for name in PERSISTED_POLICY:
        with test.subTest(name=name):
            test.assertIn(f'"{name}"', source)
    test.assertNotIn('"EVAVO_CHECKPOINT_URL",', source)
    test.assertIn('"COMFYUI_ENDPOINT"', source)
    test.assertIn('[Environment]::GetEnvironmentVariable("COMFYUI_ENDPOINT")', source)
    test.assertIn('[Environment]::GetEnvironmentVariable("EVAVO_COMFYUI_ENDPOINT")', source)
    test.assertNotIn('"EVAVO_COMFYUI_ENDPOINT" =', source)


class McpProfilePolicyTests(unittest.TestCase):
    def test_claude_installer_persists_non_secret_owner_path_policy_and_canonical_endpoint(self) -> None:
        source = (ROOT / "INSTALL-CLAUDE-MCP.ps1").read_text(encoding="utf-8")
        assert_profile_contract(self, source)

    def test_http_autostart_persists_same_non_secret_policy_and_canonical_endpoint(self) -> None:
        source = (ROOT / "INSTALL-AGENT-MCP-AUTOSTART.ps1").read_text(encoding="utf-8")
        assert_profile_contract(self, source)

    def test_root_mcp_profile_uses_canonical_endpoint(self) -> None:
        profile = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
        server = profile["mcpServers"]["evavo-local-image-generator"]
        environment = server["env"]
        self.assertEqual(environment["COMFYUI_ENDPOINT"], "http://127.0.0.1:8188")
        self.assertNotIn("EVAVO_COMFYUI_ENDPOINT", environment)

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
