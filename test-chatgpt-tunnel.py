#!/usr/bin/env python3
"""Static/offline contract tests for EVAVO ChatGPT Secure MCP Tunnel scripts."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FILES = {
    "install": ROOT / "INSTALL-CHATGPT-MCP-TUNNEL.ps1",
    "save_key": ROOT / "SAVE-CHATGPT-TUNNEL-KEY.ps1",
    "start": ROOT / "START-CHATGPT-MCP-TUNNEL.ps1",
    "autostart": ROOT / "INSTALL-CHATGPT-MCP-TUNNEL-AUTOSTART.ps1",
    "doctor": ROOT / "CHATGPT-TUNNEL-DOCTOR.ps1",
}


def text(name: str) -> str:
    return FILES[name].read_text(encoding="utf-8")


class ChatGPTTunnelContractTests(unittest.TestCase):
    def test_required_tunnel_scripts_exist(self) -> None:
        for name, path in FILES.items():
            self.assertTrue(path.is_file(), f"missing {name}: {path}")

    def test_installer_uses_latest_official_release_and_verifies_sha256(self) -> None:
        source = text("install")
        self.assertIn("api.github.com/repos/openai/tunnel-client/releases/latest", source)
        self.assertIn("browser_download_url", source)
        self.assertIn("asset.digest", source)
        self.assertIn("Get-FileHash", source)
        self.assertIn("-Algorithm SHA256", source)
        self.assertIn("refusing unverified install", source.lower())

    def test_installer_records_and_rechecks_extracted_executable_hash(self) -> None:
        source = text("install")
        self.assertIn("binary_digest", source)
        self.assertIn("$installedBinaryHash", source)
        self.assertIn("$recordedBinaryHash", source)
        self.assertIn("Get-FileHash -Path $binary -Algorithm SHA256", source)
        self.assertIn("hash-verified and executable", source)

    def test_installer_uses_supported_http_dcr_profile_shape(self) -> None:
        source = text("install")
        self.assertIn("sample_mcp_with_dcr", source)
        self.assertIn("--tunnel-id", source)
        self.assertIn("--mcp-server-url", source)
        self.assertIn("http://127.0.0.1:$McpPort/mcp", source)
        self.assertNotIn("--listen 0.0.0.0", source)

    def test_tunnel_id_validation_matches_openai_shape(self) -> None:
        installer = text("install")
        doctor = text("doctor")
        exact_pattern = r"\^tunnel_\[0-9a-f\]\{32\}\$"
        self.assertRegex(installer, exact_pattern)
        self.assertRegex(doctor, exact_pattern)
        self.assertNotIn("[A-Za-z0-9_-]{8,}", installer)
        self.assertNotIn("[A-Za-z0-9_-]{8,}", doctor)

    def test_runtime_key_store_uses_current_user_dpapi(self) -> None:
        source = text("save_key")
        self.assertIn("ConvertFrom-SecureString", source)
        self.assertIn("ConvertTo-SecureString", source)
        self.assertIn("LOCALAPPDATA", source)
        self.assertIn("chatgpt-tunnel-runtime-key.dpapi", source)
        self.assertNotRegex(source, r"Set-Content[^\n]*CONTROL_PLANE_API_KEY")

    def test_tunnel_launcher_verifies_binary_before_loading_runtime_key(self) -> None:
        source = text("start")
        integrity_index = source.index("tunnel-client-install.json")
        key_index = source.index("# Load the runtime key")
        self.assertLess(integrity_index, key_index)
        self.assertIn("binary_digest", source)
        self.assertIn("Get-FileHash -Path $binary -Algorithm SHA256", source)
        self.assertIn("Refusing to run", source)

    def test_tunnel_launcher_loads_key_at_runtime_and_runs_named_profile(self) -> None:
        source = text("start")
        self.assertIn("CONTROL_PLANE_API_KEY", source)
        self.assertIn("chatgpt-tunnel-runtime-key.dpapi", source)
        self.assertIn("doctor --profile", source)
        self.assertIn("run --profile", source)
        self.assertIn("127.0.0.1", source)
        self.assertNotIn("0.0.0.0", source)

    def test_tunnel_launcher_derives_unspecified_port_from_saved_profile(self) -> None:
        source = text("start")
        self.assertIn("[int]$McpPort = 0", source)
        self.assertIn("$state.mcp_server_url", source)
        self.assertIn("$savedMcpUri.Port", source)
        self.assertIn('$savedMcpUri.Host -notin @("127.0.0.1", "localhost", "::1")', source)

    def test_tunnel_launcher_preserves_caller_supplied_key(self) -> None:
        source = text("start")
        self.assertIn("$loadedFromDpapi = $false", source)
        self.assertIn("$loadedFromDpapi = [bool]$env:CONTROL_PLANE_API_KEY", source)
        self.assertIn("if ($loadedFromDpapi)", source)
        self.assertNotRegex(source, r"\$env:CONTROL_PLANE_API_KEY\s*=\s*\$null\s*\nexit")

    def test_login_autostart_requires_dpapi_and_never_embeds_plaintext_key(self) -> None:
        source = text("autostart")
        self.assertIn("START-CHATGPT-MCP-TUNNEL.ps1", source)
        self.assertIn("-SkipDoctor", source)
        self.assertIn("chatgpt-tunnel-runtime-key.dpapi", source)
        self.assertIn("login autostart requires the DPAPI key blob", source)
        self.assertIn("ConvertTo-SecureString", source)
        self.assertNotRegex(source, r"(?i)set\s+[\"']?CONTROL_PLANE_API_KEY\s*=")
        self.assertNotIn("$env:CONTROL_PLANE_API_KEY = $env:CONTROL_PLANE_API_KEY", source)

    def test_doctor_verifies_tunnel_executable_integrity(self) -> None:
        source = text("doctor")
        self.assertIn("tunnel_client_integrity", source)
        self.assertIn("binary_digest", source)
        self.assertIn("Get-FileHash -Path $binary -Algorithm SHA256", source)
        self.assertIn("hash-verified executable smoke check passed", source)

    def test_doctor_never_serializes_or_prints_the_key(self) -> None:
        source = text("doctor")
        self.assertIn("tunnel-client", source)
        self.assertIn("doctor --profile", source)
        self.assertIn("runtime_key", source)
        self.assertNotRegex(source, r"Write-Host[^\n]*\$env:CONTROL_PLANE_API_KEY")
        self.assertNotRegex(source, r"ConvertTo-Json[^\n]*CONTROL_PLANE_API_KEY")

    def test_doctor_does_not_overclaim_chatgpt_workspace_visibility(self) -> None:
        source = text("doctor")
        self.assertIn("local preflight", source.lower())
        self.assertIn("does not by itself prove", source)
        self.assertNotIn('status = "chatgpt_connected"', source)

    def test_non_secret_tunnel_state_contains_no_api_key_field(self) -> None:
        source = text("install")
        state_block = re.search(r"\$state\s*=\s*\[ordered\]@\{(?P<body>.*?)\n\}", source, re.DOTALL)
        self.assertIsNotNone(state_block)
        assert state_block is not None
        body = state_block.group("body")
        self.assertNotIn("CONTROL_PLANE_API_KEY", body)
        self.assertNotRegex(body, r"(?i)api[_-]?key\s*=")


if __name__ == "__main__":
    unittest.main(verbosity=2)
