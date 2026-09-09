#!/usr/bin/env python3
"""Static safety tests for EVAVO MCP/tunnel shutdown helpers."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class AgentStopSafetyTests(unittest.TestCase):
    def test_private_mcp_stop_is_port_and_command_identity_scoped(self) -> None:
        source = (ROOT / "STOP-AGENT-MCP.ps1").read_text(encoding="utf-8")
        lower = source.lower()
        self.assertIn("Get-NetTCPConnection", source)
        self.assertIn("evavo_local_image_generator\\.mcp_server", source)
        self.assertIn("--transport\\s+streamable-http", source)
        self.assertIn("Stop-Process -Id $pidValue", source)
        self.assertNotIn("taskkill /im", lower)
        self.assertNotIn("get-process python", lower)
        self.assertNotIn("stop-process -name", lower)

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
