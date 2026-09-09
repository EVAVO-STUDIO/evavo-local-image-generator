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
POLICY_COMMAND = "-m evavo_local_image_generator.mcp_policy --json"
VALIDATED_ENTRY = "evavo_local_image_generator.mcp_entry"


def assert_profile_contract(test: unittest.TestCase, source: str) -> None:
    for name in PERSISTED_POLICY:
        with test.subTest(name=name):
            test.assertIn(f'"{name}"', source)
    test.assertNotIn('"EVAVO_CHECKPOINT_URL",', source)
    test.assertIn('"COMFYUI_ENDPOINT"', source)
    test.assertIn('[Environment]::GetEnvironmentVariable("COMFYUI_ENDPOINT")', source)
    test.assertIn('[Environment]::GetEnvironmentVariable("EVAVO_COMFYUI_ENDPOINT")', source)
    test.assertNotIn('"EVAVO_COMFYUI_ENDPOINT" =', source)
    test.assertIn(POLICY_COMMAND, source)
    test.assertIn("MCP filesystem policy is invalid", source)
    test.assertIn('$generationOutputDir = [string]$policyResult.policy.default_output_root', source)
    test.assertIn('"EVAVO_GENERATION_OUTPUT_DIR" = $generationOutputDir', source)
    test.assertNotIn('"EVAVO_GENERATION_OUTPUT_DIR" = (Join-Path', source)


class McpProfilePolicyTests(unittest.TestCase):
    def test_claude_installer_persists_non_secret_owner_path_policy_and_canonical_endpoint(self) -> None:
        source = (ROOT / "INSTALL-CLAUDE-MCP.ps1").read_text(encoding="utf-8")
        assert_profile_contract(self, source)
        self.assertIn(VALIDATED_ENTRY, source)
        self.assertNotIn('"args" = @("-m", "evavo_local_image_generator.mcp_server"', source)

    def test_http_autostart_persists_same_non_secret_policy_and_canonical_endpoint(self) -> None:
        source = (ROOT / "INSTALL-AGENT-MCP-AUTOSTART.ps1").read_text(encoding="utf-8")
        assert_profile_contract(self, source)
        start = (ROOT / "START-AGENT-MCP.ps1").read_text(encoding="utf-8")
        self.assertIn(VALIDATED_ENTRY, start)

    def test_claude_policy_validation_precedes_any_config_write_or_backup(self) -> None:
        source = (ROOT / "INSTALL-CLAUDE-MCP.ps1").read_text(encoding="utf-8")
        policy = source.index(POLICY_COMMAND)
        policy_parse = source.index('$generationOutputDir = [string]$policyResult.policy.default_output_root')
        create_dir = source.index('New-Item -ItemType Directory -Force -Path $configDir')
        backup = source.index("Copy-Item $configPath $backup")
        write = source.index("Set-Content -Path $configPath")
        self.assertLess(policy, policy_parse)
        self.assertLess(policy_parse, create_dir)
        self.assertLess(policy, backup)
        self.assertLess(policy, write)

    def test_http_policy_validation_precedes_startup_directory_and_launcher_write(self) -> None:
        source = (ROOT / "INSTALL-AGENT-MCP-AUTOSTART.ps1").read_text(encoding="utf-8")
        policy = source.index(POLICY_COMMAND)
        policy_parse = source.index('$generationOutputDir = [string]$policyResult.policy.default_output_root')
        create_dir = source.index('New-Item -ItemType Directory -Force -Path $startupDir')
        write = source.index("Set-Content -Path $launcher")
        start = source.index('Start-Process -FilePath "powershell.exe"')
        self.assertLess(policy, policy_parse)
        self.assertLess(policy_parse, create_dir)
        self.assertLess(policy, write)
        self.assertLess(policy, start)

    def test_skip_validation_never_skips_policy_validation(self) -> None:
        for name in ("INSTALL-CLAUDE-MCP.ps1", "INSTALL-AGENT-MCP-AUTOSTART.ps1"):
            source = (ROOT / name).read_text(encoding="utf-8")
            with self.subTest(name=name):
                skip_block = source.index("if (-not $SkipValidation)")
                policy = source.index(POLICY_COMMAND)
                self.assertGreater(policy, skip_block)
                self.assertIn("Always validate", source[skip_block:policy])

    def test_root_mcp_profile_uses_validated_entry_and_canonical_endpoint(self) -> None:
        profile = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
        server = profile["mcpServers"]["evavo-local-image-generator"]
        environment = server["env"]
        self.assertEqual(server["args"][:2], ["-m", VALIDATED_ENTRY])
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
