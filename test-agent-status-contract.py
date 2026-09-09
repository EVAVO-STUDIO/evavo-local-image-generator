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
        self.assertNotIn("-Method Post", SOURCE)

    def test_private_mcp_identity_is_checked(self) -> None:
        self.assertIn("Get-NetTCPConnection", SOURCE)
        self.assertIn("evavo_local_image_generator\\.mcp_server", SOURCE)
        self.assertIn("--transport\\s+streamable-http", SOURCE)
        self.assertIn("unexpected_listener", SOURCE)

    def test_tunnel_control_plane_check_is_optional(self) -> None:
        self.assertIn("[switch]$CheckTunnelControlPlane", SOURCE)
        self.assertIn("-SkipControlPlane", SOURCE)
        self.assertIn("CHATGPT-TUNNEL-DOCTOR.ps1", SOURCE)

    def test_chatgpt_tunnel_gateway_and_old_smoke_proof_are_not_live_readiness_authority(self) -> None:
        self.assertIn("$localReady = [bool]($repoOk -and $agentOk -and $backendOk)", SOURCE)
        self.assertIn("ChatGPT tunnel is optional for local/Claude use", SOURCE)
        self.assertIn("current owned native-image readiness remains the status exit-code", SOURCE)
        self.assertNotIn("$localReady = [bool]($repoOk -and $agentOk -and $backendOk -and $gateway", SOURCE)
        self.assertNotIn("$localReady = [bool]($repoOk -and $agentOk -and $backendOk -and $smoke", SOURCE)

    def test_latest_real_generation_proof_is_reported_from_shared_history(self) -> None:
        self.assertIn('"task-tracker.py"', SOURCE)
        self.assertIn('"--project", "setup-smoke"', SOURCE)
        self.assertIn('"--limit", "1"', SOURCE)
        self.assertIn('real_generation_proof = $smoke', SOURCE)
        self.assertIn("Latest real generation proof", SOURCE)
        self.assertIn("files_present", SOURCE)
        self.assertIn("Test-Path -LiteralPath", SOURCE)
        self.assertNotIn("real-generation-smoke.py", SOURCE)

    def test_optional_gateway_services_are_reported_separately(self) -> None:
        self.assertIn('[int]$GatewayPort = 8000', SOURCE)
        self.assertIn('$gatewayBase = "http://127.0.0.1:$GatewayPort"', SOURCE)
        self.assertIn('Invoke-LocalJson "$gatewayBase/health"', SOURCE)
        self.assertIn('Invoke-LocalJson "$gatewayBase/services"', SOURCE)
        self.assertIn("optional_gateway = $gateway", SOURCE)
        for kind in ("image", "video", "audio", "3d"):
            self.assertIn(f'"{kind}"', SOURCE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
