#!/usr/bin/env python3
"""Cross-check machine-readable MCP entrypoint/policy claims against live files."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class McpEntryManifestTests(unittest.TestCase):
    def test_manifest_points_to_validated_entry_and_internal_server_implementation(self) -> None:
        manifest = json.loads((ROOT / "EVAVO-CAPABILITIES.json").read_text(encoding="utf-8"))
        mcp = manifest["interfaces"]["mcp"]
        self.assertEqual(mcp["production_entry_module"], "evavo_local_image_generator.mcp_entry")
        self.assertEqual(mcp["implementation_module"], "evavo_local_image_generator.mcp_server")
        self.assertEqual(mcp["stdio"], "python -m evavo_local_image_generator.mcp_entry --transport stdio")

    def test_manifest_policy_guarantees_are_backed_by_entry_and_installers(self) -> None:
        manifest = json.loads((ROOT / "EVAVO-CAPABILITIES.json").read_text(encoding="utf-8"))
        policy = manifest["interfaces"]["mcp"]["file_policy"]
        security = manifest["security"]
        self.assertTrue(policy["additional_output_roots_must_be_writable"])
        self.assertTrue(policy["validated_before_profile_persistence"])
        self.assertTrue(policy["validated_at_production_server_entry"])
        self.assertTrue(security["mcp_profile_policy_validated_before_persistence"])
        self.assertTrue(security["mcp_production_entry_policy_validation"])

        entry = (ROOT / "evavo_local_image_generator" / "mcp_entry.py").read_text(encoding="utf-8")
        policy_source = (ROOT / "evavo_local_image_generator" / "mcp_policy.py").read_text(encoding="utf-8")
        claude = (ROOT / "INSTALL-CLAUDE-MCP.ps1").read_text(encoding="utf-8")
        autostart = (ROOT / "INSTALL-AGENT-MCP-AUTOSTART.ps1").read_text(encoding="utf-8")
        self.assertIn("validate_startup_policy", entry)
        self.assertIn("validate_environment", entry)
        self.assertIn("writable=True", policy_source)
        self.assertIn("evavo_local_image_generator.mcp_policy --json", claude)
        self.assertIn("evavo_local_image_generator.mcp_policy --json", autostart)

    def test_project_profile_bootstraps_to_validated_entry_and_generated_profiles_use_it_directly(self) -> None:
        profile = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
        server = profile["mcpServers"]["evavo-local-image-generator"]
        self.assertEqual(server["command"], "python")
        self.assertEqual(server["args"][:2], ["mcp-bootstrap.py", "--transport"])
        bootstrap = (ROOT / "mcp-bootstrap.py").read_text(encoding="utf-8")
        self.assertIn('"evavo_local_image_generator.mcp_entry"', bootstrap)

        claude = (ROOT / "INSTALL-CLAUDE-MCP.ps1").read_text(encoding="utf-8")
        start = (ROOT / "START-AGENT-MCP.ps1").read_text(encoding="utf-8")
        self.assertIn('"evavo_local_image_generator.mcp_entry"', claude)
        self.assertIn('"-m", "evavo_local_image_generator.mcp_entry"', start)


if __name__ == "__main__":
    unittest.main(verbosity=2)
