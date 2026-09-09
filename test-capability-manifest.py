#!/usr/bin/env python3
"""Offline synchronization tests for EVAVO-CAPABILITIES.json."""

from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = ROOT / "EVAVO-CAPABILITIES.json"
MCP_PATH = ROOT / "evavo_local_image_generator" / "mcp_server.py"
GATEWAY_PATH = ROOT / "EVAVO-GATEWAY.py"
PROVIDER_PATH = ROOT / "evavo_local_image_generator" / "provider_runner.py"


def registered_mcp_tools() -> set[str]:
    tree = ast.parse(MCP_PATH.read_text(encoding="utf-8"), filename=str(MCP_PATH))
    tools: set[str] = set()
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            call = decorator if isinstance(decorator, ast.Call) else None
            target = call.func if call else decorator
            if (
                isinstance(target, ast.Attribute)
                and target.attr == "tool"
                and isinstance(target.value, ast.Name)
                and target.value.id == "mcp"
            ):
                tools.add(node.name)
                break
    return tools


class CapabilityManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_manifest_is_machine_readable_and_owned_contract_is_image_only(self) -> None:
        self.assertEqual(self.manifest["schema_version"], 1)
        self.assertEqual(self.manifest["capability_id"], "evavo.local.image-generation")
        contract = self.manifest["production_contract"]
        self.assertEqual(contract["owned_modality"], "image")
        self.assertEqual(contract["backend"], "native-comfyui")
        self.assertFalse(contract["mock_is_renderer"])
        self.assertEqual(contract["canonical_endpoint_environment"], "COMFYUI_ENDPOINT")

    def test_manifest_tool_inventory_matches_registered_mcp_tools_exactly(self) -> None:
        manifest_tools = set(self.manifest["interfaces"]["mcp"]["tools"])
        actual_tools = registered_mcp_tools()
        self.assertEqual(manifest_tools, actual_tools)
        self.assertEqual(self.manifest["interfaces"]["mcp"]["owned_generation_modalities"], ["image"])
        self.assertNotIn("generate_video", actual_tools)
        self.assertNotIn("generate_audio", actual_tools)
        self.assertNotIn("generate_3d", actual_tools)

    def test_chatgpt_contract_uses_secure_tunnel_not_direct_localhost(self) -> None:
        chatgpt = self.manifest["interfaces"]["chatgpt"]
        self.assertEqual(chatgpt["transport"], "openai-secure-mcp-tunnel")
        self.assertFalse(chatgpt["direct_localhost_supported"])
        self.assertTrue(chatgpt["private_mcp_default"].startswith("http://127.0.0.1:"))

    def test_private_http_interfaces_are_loopback_only_and_cors_is_opt_in(self) -> None:
        mcp_http = self.manifest["interfaces"]["mcp"]["streamable_http"]
        gateway = self.manifest["interfaces"]["http_gateway"]
        self.assertTrue(mcp_http["loopback_only"])
        self.assertTrue(gateway["loopback_only"])
        self.assertEqual(gateway["cors_default"], "disabled")
        self.assertFalse(gateway["cors_wildcard_allowed"])
        self.assertTrue(mcp_http["default_url"].startswith("http://127.0.0.1:"))
        self.assertTrue(gateway["default_url"].startswith("http://127.0.0.1:"))
        source = GATEWAY_PATH.read_text(encoding="utf-8")
        self.assertIn('os.getenv("EVAVO_GATEWAY_CORS_ORIGINS", "")', source)
        self.assertIn('origin == "*"', source)
        self.assertIn("LOOPBACK_ORIGIN_RE", source)

    def test_gateway_manifest_matches_governed_auxiliary_delegation(self) -> None:
        gateway_source = GATEWAY_PATH.read_text(encoding="utf-8")
        auxiliary = self.manifest["interfaces"]["http_gateway"]["auxiliary_delegation"]
        self.assertTrue(auxiliary["fail_closed"])
        self.assertEqual(auxiliary["readiness_endpoint"], "/services")
        routes = auxiliary["routes"]
        self.assertEqual(set(routes), {"/generate/video", "/generate/audio", "/generate/3d"})
        for path, metadata in routes.items():
            with self.subTest(path=path):
                self.assertEqual(metadata["accepted_status"], 202)
                self.assertEqual(metadata["ownership"], "delegated")
                self.assertIn(path, gateway_source)
        self.assertIn('status_code=202', gateway_source)
        self.assertIn("_provider_worker", gateway_source)

    def test_delegated_modalities_are_not_owned_package_or_mcp_capabilities(self) -> None:
        not_owned = set(self.manifest["not_owned_production_modalities"])
        delegated = set(self.manifest["delegated_gateway_modalities"])
        self.assertEqual(delegated, {"video", "audio", "3d"})
        self.assertTrue(delegated.issubset(not_owned))
        self.assertEqual(self.manifest["interfaces"]["python"]["owned_generation_modalities"], ["image"])

    def test_provider_runner_is_fail_closed_and_not_shell_execution(self) -> None:
        source = PROVIDER_PATH.read_text(encoding="utf-8")
        self.assertIn("create_subprocess_exec", source)
        self.assertNotIn("shell=True", source)
        security = self.manifest["security"]
        self.assertFalse(security["provider_shell_execution"])
        self.assertTrue(security["provider_receipt_required"])
        self.assertTrue(security["provider_output_confinement"])

    def test_security_contract_rejects_old_dangerous_defaults(self) -> None:
        security = self.manifest["security"]
        self.assertFalse(security["public_bind_by_default"])
        self.assertFalse(security["gateway_wildcard_cors_by_default"])
        self.assertFalse(security["broad_python_process_kill"])
        self.assertTrue(security["managed_process_identity_verification"])
        self.assertTrue(security["chatgpt_tunnel_executable_sha256_verification"])
        self.assertFalse(security["plaintext_tunnel_key_in_repo_or_startup"])
        self.assertFalse(security["arbitrary_model_url_from_mcp_tool"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
