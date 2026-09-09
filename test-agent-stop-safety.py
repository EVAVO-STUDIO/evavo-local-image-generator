#!/usr/bin/env python3
"""Static safety tests for EVAVO MCP/tunnel shutdown and listener reload helpers."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class AgentStopSafetyTests(unittest.TestCase):
    def test_private_mcp_stop_is_runtime_host_port_path_and_command_identity_scoped(self) -> None:
        source = (ROOT / "STOP-AGENT-MCP.ps1").read_text(encoding="utf-8")
        lower = source.lower()
        self.assertIn("Get-NetTCPConnection", source)
        self.assertIn("ExecutablePath", source)
        self.assertIn("OrdinalIgnoreCase", source)
        self.assertIn("evavo_local_image_generator\\.(?:mcp_entry|mcp_server)", source)
        self.assertIn("evavo_local_image_generator\\.mcp_entry", source)
        self.assertIn("--transport\\s+streamable-http", source)
        self.assertIn("--host\\s+127\\.0\\.0\\.1", source)
        self.assertIn("--port\\s+$Port", source)
        self.assertIn("--path\\s+", source)
        self.assertIn("START-AGENT-MCP.ps1", source)
        self.assertIn("Stop-Process -Id $pidValue", source)
        self.assertIn("cannot prove", lower)
        self.assertIn("legacy mcp_server", lower)
        self.assertNotIn("taskkill /im", lower)
        self.assertNotIn("get-process python", lower)
        self.assertNotIn("stop-process -name", lower)

    def test_private_mcp_start_reloads_only_a_verified_listener_and_migrates_legacy(self) -> None:
        source = (ROOT / "START-AGENT-MCP.ps1").read_text(encoding="utf-8")
        lower = source.lower()
        self.assertIn("[switch]$RestartIfRunning", source)
        self.assertIn("Test-EvavoMcpListenerIdentity", source)
        self.assertIn("ExecutablePath", source)
        self.assertIn("ParentProcessId", source)
        self.assertIn("evavo_local_image_generator\\.(?:mcp_entry|mcp_server)", source)
        self.assertIn('"-m", "evavo_local_image_generator.mcp_entry"', source)
        self.assertIn("legacy mcp_server", lower)
        self.assertIn("policy-validated mcp_entry", lower)
        self.assertIn("--transport\\s+streamable-http", source)
        self.assertIn("--host\\s+127\\.0\\.0\\.1", source)
        self.assertIn("--port\\s+$Port", source)
        self.assertIn("--path\\s+", source)
        self.assertIn("Stop-Process -Id ([int]$listener.OwningProcess)", source)
        self.assertIn("refusing to adopt or stop", lower)
        self.assertNotIn("taskkill /im", lower)
        self.assertNotIn("stop-process -name", lower)

    def test_autostart_installer_reloads_verified_listener_after_update(self) -> None:
        source = (ROOT / "INSTALL-AGENT-MCP-AUTOSTART.ps1").read_text(encoding="utf-8")
        self.assertIn("-RestartIfRunning", source)
        self.assertIn('"COMFYUI_ENDPOINT" = $comfyEndpoint', source)
        self.assertNotIn('"EVAVO_COMFYUI_ENDPOINT" =', source)

    def test_tunnel_stop_requires_exact_verified_binary(self) -> None:
        source = (ROOT / "STOP-CHATGPT-MCP-TUNNEL.ps1").read_text(encoding="utf-8")
        lower = source.lower()
        self.assertIn("tunnel-client-install.json", source)
        self.assertIn("binary_digest", source)
        self.assertIn("Get-FileHash -Path $expectedBinary -Algorithm SHA256", source)
        self.assertIn("ExecutablePath", source)
        self.assertIn("OrdinalIgnoreCase", source)
        self.assertIn("--profile\\s+", source)
        self.assertIn("Stop-Process -Id $pidValue", source)
        self.assertNotIn("taskkill /im", lower)
        self.assertNotIn("stop-process -name tunnel-client", lower)

    def test_shutdown_helpers_offer_explicit_autostart_removal(self) -> None:
        mcp = (ROOT / "STOP-AGENT-MCP.ps1").read_text(encoding="utf-8")
        tunnel = (ROOT / "STOP-CHATGPT-MCP-TUNNEL.ps1").read_text(encoding="utf-8")
        self.assertIn("[switch]$RemoveAutostart", mcp)
        self.assertIn("INSTALL-AGENT-MCP-AUTOSTART.ps1", mcp)
        self.assertIn("[switch]$RemoveAutostart", tunnel)
        self.assertIn("INSTALL-CHATGPT-MCP-TUNNEL-AUTOSTART.ps1", tunnel)


if __name__ == "__main__":
    unittest.main(verbosity=2)
