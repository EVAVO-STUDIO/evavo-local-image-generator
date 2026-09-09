#!/usr/bin/env python3
"""Static contract tests for AGENT-STATUS.ps1."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = (ROOT / "AGENT-STATUS.ps1").read_text(encoding="utf-8")


class AgentStatusContractTests(unittest.TestCase):
    def test_status_command_is_read_only(self) -> None:
        lower = SOURCE.lower()
        self.assertIn('"doctor", "--json"', SOURCE)
        self.assertIn('"agent-doctor.py"', SOURCE)
        self.assertIn('"status"', SOURCE)
        self.assertNotIn("--repair", SOURCE)
        self.assertNotIn("--provision", SOURCE)
        self.assertNotIn("stop-process", lower)
        self.assertNotIn("taskkill", lower)
        self.assertNotIn("start-process", lower)

    def test_private_mcp_identity_is_checked(self) -> None:
        self.assertIn("Get-NetTCPConnection", SOURCE)
        self.assertIn("evavo_local_image_generator\\.mcp_server", SOURCE)
        self.assertIn("--transport\\s+streamable-http", SOURCE)
        self.assertIn("unexpected_listener", SOURCE)

    def test_tunnel_control_plane_check_is_optional(self) -> None:
        self.assertIn("[switch]$CheckTunnelControlPlane", SOURCE)
        self.assertIn("-SkipControlPlane", SOURCE)
        self.assertIn("CHATGPT-TUNNEL-DOCTOR.ps1", SOURCE)

    def test_chatgpt_tunnel_is_not_required_for_local_ready_state(self) -> None:
        self.assertIn("$localReady = [bool]($repoOk -and $agentOk -and $backendOk)", SOURCE)
        self.assertIn("ChatGPT tunnel is optional for local/Claude use", SOURCE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
