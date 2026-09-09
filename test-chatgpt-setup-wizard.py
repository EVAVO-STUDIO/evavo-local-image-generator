#!/usr/bin/env python3
"""Static security/behavior tests for SETUP-CHATGPT-EVAVO.ps1."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = (ROOT / "SETUP-CHATGPT-EVAVO.ps1").read_text(encoding="utf-8")


class ChatGPTSetupWizardTests(unittest.TestCase):
    def test_exact_tunnel_id_contract(self) -> None:
        self.assertIn("^tunnel_[0-9a-f]{32}$", SOURCE)

    def test_wizard_uses_existing_verified_tunnel_scripts(self) -> None:
        for name in (
            "INSTALL-CHATGPT-MCP-TUNNEL.ps1",
            "SAVE-CHATGPT-TUNNEL-KEY.ps1",
            "INSTALL-CHATGPT-MCP-TUNNEL-AUTOSTART.ps1",
            "CHATGPT-TUNNEL-DOCTOR.ps1",
            "START-CHATGPT-MCP-TUNNEL.ps1",
        ):
            self.assertIn(name, SOURCE)

    def test_no_plaintext_runtime_key_prompt_or_command_argument(self) -> None:
        self.assertNotIn('Read-Host "CONTROL_PLANE_API_KEY', SOURCE)
        self.assertNotIn("-RuntimeKey", SOURCE)
        self.assertNotIn("--api-key", SOURCE)
        self.assertNotIn("--control-plane-api-key", SOURCE)
        self.assertIn("SAVE-CHATGPT-TUNNEL-KEY.ps1", SOURCE)

    def test_persistent_mode_uses_dpapi_autostart_and_doctor(self) -> None:
        self.assertIn("chatgpt-tunnel-runtime-key.dpapi", SOURCE)
        self.assertIn("-RequireRuntimeKey -RequireRunning", SOURCE)
        self.assertIn("Windows DPAPI current-user store", SOURCE)

    def test_session_only_mode_requires_existing_process_environment_key(self) -> None:
        self.assertIn("[switch]$SessionOnly", SOURCE)
        self.assertIn("-SessionOnly requires CONTROL_PLANE_API_KEY", SOURCE)
        self.assertIn("will not turn an interactive secret into plaintext environment state", SOURCE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
