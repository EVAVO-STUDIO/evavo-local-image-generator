#!/usr/bin/env python3
"""Static contract tests for persistent Claude/HTTP MCP production policy settings."""

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
    test.assertIn('"COMFYUI_ENDPOINT" = $comfyEndpoint', source)
    test.assertNotIn('"EVAVO_COMFYUI_ENDPOINT" =', source)
    test.assertNotIn('[Environment]::GetEnvironmentVariable("COMFYUI_ENDPOINT")', source)
    test.assertNotIn('[Environment]::GetEnvironmentVariable("EVAVO_COMFYUI_ENDPOINT")', source)
    test.assertIn(POLICY_COMMAND, source)
    test.assertIn("MCP production policy is invalid", source)
    test.assertIn('$generationOutputDir = [string]$policyResult.policy.default_output_root', source)
    test.assertIn('$taskHistoryFile = [string]$policyResult.policy.task_history_file', source)
    test.assertIn('$comfyEndpoint = [string]$policyResult.policy.comfyui_endpoint', source)
    test.assertIn("validated loopback ComfyUI endpoint", source)
    test.assertIn('"EVAVO_GENERATION_OUTPUT_DIR" = $generationOutputDir', source)
    test.assertIn('"EVAVO_TASK_HISTORY" = $taskHistoryFile', source)
    test.assertNotIn('"EVAVO_GENERATION_OUTPUT_DIR" = (Join-Path', source)
    test.assertIn('@($policyResult.policy.additional_output_roots)', source)
    test.assertIn('[string]$policyResult.policy.owner_workflow', source)
    test.assertIn('[bool]$policyResult.policy.tool_workflow_paths_allowed', source)
    test.assertIn('[string]$policyResult.policy.tool_workflow_root', source)
    test.assertIn('-join ";"', source)


class McpProfilePolicyTests(unittest.TestCase):
    def test_claude_installer_persists_validator_owned_policy_and_endpoint(self) -> None:
        source = (ROOT / "INSTALL-CLAUDE-MCP.ps1").read_text(encoding="utf-8")
        assert_profile_contract(self, source)
        self.assertIn(VALIDATED_ENTRY, source)
        self.assertNotIn('"args" = @("-m", "evavo_local_image_generator.mcp_server"', source)

    def test_http_autostart_persists_same_validator_owned_policy_and_endpoint(self) -> None:
        source = (ROOT / "INSTALL-AGENT-MCP-AUTOSTART.ps1").read_text(encoding="utf-8")
        assert_profile_contract(self, source)
        start = (ROOT / "START-AGENT-MCP.ps1").read_text(encoding="utf-8")
        self.assertIn(VALIDATED_ENTRY, start)

    def test_persistent_agent_surfaces_require_repo_local_venv_without_system_python_fallback(self) -> None:
        for name in ("INSTALL-CLAUDE-MCP.ps1", "INSTALL-AGENT-MCP-AUTOSTART.ps1", "START-AGENT-MCP.ps1"):
            source = (ROOT / name).read_text(encoding="utf-8")
            with self.subTest(name=name):
                self.assertIn('.venv\\Scripts\\python.exe', source)
                self.assertIn("EVAVO .venv is not ready", source)
                self.assertNotIn("Get-Command python", source)
                self.assertNotIn("$python = $cmd.Source", source)

    def test_claude_policy_validation_precedes_any_config_write_or_backup(self) -> None:
        source = (ROOT / "INSTALL-CLAUDE-MCP.ps1").read_text(encoding="utf-8")
        policy = source.index(POLICY_COMMAND)
        output_parse = source.index('$generationOutputDir = [string]$policyResult.policy.default_output_root')
        endpoint_parse = source.index('$comfyEndpoint = [string]$policyResult.policy.comfyui_endpoint')
        create_dir = source.index('New-Item -ItemType Directory -Force -Path $configDir')
        backup = source.index("Copy-Item $configPath $backup")
        write = source.index("Set-Content -Path $configPath")
        self.assertLess(policy, output_parse)
        self.assertLess(policy, endpoint_parse)
        self.assertLess(output_parse, create_dir)
        self.assertLess(endpoint_parse, create_dir)
        self.assertLess(policy, backup)
        self.assertLess(policy, write)

    def test_http_policy_validation_precedes_startup_directory_and_launcher_write(self) -> None:
        source = (ROOT / "INSTALL-AGENT-MCP-AUTOSTART.ps1").read_text(encoding="utf-8")
        policy = source.index(POLICY_COMMAND)
        output_parse = source.index('$generationOutputDir = [string]$policyResult.policy.default_output_root')
        endpoint_parse = source.index('$comfyEndpoint = [string]$policyResult.policy.comfyui_endpoint')
        create_dir = source.index('New-Item -ItemType Directory -Force -Path $startupDir')
        write = source.index("Set-Content -Path $launcher")
        start = source.index('Start-Process -FilePath "powershell.exe"')
        self.assertLess(policy, output_parse)
        self.assertLess(policy, endpoint_parse)
        self.assertLess(output_parse, create_dir)
        self.assertLess(endpoint_parse, create_dir)
        self.assertLess(policy, write)
        self.assertLess(policy, start)

    def test_skip_validation_never_skips_production_policy_validation(self) -> None:
        for name in ("INSTALL-CLAUDE-MCP.ps1", "INSTALL-AGENT-MCP-AUTOSTART.ps1"):
            source = (ROOT / name).read_text(encoding="utf-8")
            with self.subTest(name=name):
                skip_block = source.index("if (-not $SkipValidation)")
                policy = source.index(POLICY_COMMAND)
                self.assertGreater(policy, skip_block)

    def test_raw_relative_or_legacy_mcp_authority_is_not_re_persisted_from_environment(self) -> None:
        for name in ("INSTALL-CLAUDE-MCP.ps1", "INSTALL-AGENT-MCP-AUTOSTART.ps1"):
            source = (ROOT / name).read_text(encoding="utf-8")
            with self.subTest(name=name):
                non_secret_start = source.index("$nonSecretEnvironment = @(")
                non_secret_end = source.index(")", non_secret_start)
                block = source[non_secret_start:non_secret_end]
                self.assertNotIn('"EVAVO_COMFYUI_WORKFLOW"', block)
                self.assertNotIn('"EVAVO_MCP_OUTPUT_ROOTS"', block)
                self.assertNotIn('"EVAVO_MCP_ALLOW_WORKFLOW_PATHS"', block)
                self.assertNotIn('"EVAVO_MCP_WORKFLOW_ROOT"', block)
                self.assertNotIn('"COMFYUI_ENDPOINT"', block)
                self.assertNotIn('"EVAVO_COMFYUI_ENDPOINT"', block)
                self.assertNotIn('"EVAVO_TASK_HISTORY"', block)

    def test_root_mcp_profile_bootstraps_to_validated_entry_and_keeps_canonical_loopback_endpoint(self) -> None:
        profile = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
        server = profile["mcpServers"]["evavo-local-image-generator"]
        environment = server["env"]
        self.assertEqual(server["command"], "python")
        self.assertEqual(server["args"][:2], ["mcp-bootstrap.py", "--transport"])
        self.assertEqual(environment["COMFYUI_ENDPOINT"], "http://127.0.0.1:8188")
        self.assertNotIn("EVAVO_COMFYUI_ENDPOINT", environment)
        bootstrap = (ROOT / "mcp-bootstrap.py").read_text(encoding="utf-8")
        self.assertIn('"evavo_local_image_generator.mcp_entry"', bootstrap)
        self.assertIn('ROOT / ".venv"', bootstrap)

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
