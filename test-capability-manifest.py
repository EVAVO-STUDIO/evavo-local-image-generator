#!/usr/bin/env python3
"""Offline synchronization tests for EVAVO capability manifests."""

from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = ROOT / "EVAVO-CAPABILITIES.json"
REPOSITORY_CAPABILITIES_PATH = ROOT / ".evavo" / "capabilities.json"
MCP_PATH = ROOT / "evavo_local_image_generator" / "mcp_server.py"
BACKEND_PATH = ROOT / "evavo_local_image_generator" / "backends" / "comfyui_backend.py"
STATUS_PATH = ROOT / "evavo_local_image_generator" / "comfyui_status.py"
CANCEL_PATH = ROOT / "evavo_local_image_generator" / "comfyui_cancel.py"
GATEWAY_PATH = ROOT / "EVAVO-GATEWAY.py"
MANAGER_PATH = ROOT / "EVAVO-SERVICE-MANAGER.py"
OPERATIONS_PATH = ROOT / "evavo_operations.py"
PROVIDER_PATH = ROOT / "evavo_local_image_generator" / "provider_runner.py"
CLAUDE_INSTALLER = ROOT / "INSTALL-CLAUDE-MCP.ps1"
HTTP_AUTOSTART_INSTALLER = ROOT / "INSTALL-AGENT-MCP-AUTOSTART.ps1"


def registered_mcp_tools() -> set[str]:
    tree = ast.parse(MCP_PATH.read_text(encoding="utf-8"), filename=str(MCP_PATH))
    tools: set[str] = set()
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            call = decorator if isinstance(decorator, ast.Call) else None
            target = call.func if call else decorator
            if isinstance(target, ast.Attribute) and target.attr == "tool" and isinstance(target.value, ast.Name) and target.value.id == "mcp":
                tools.add(node.name)
                break
    return tools


class CapabilityManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        cls.repository_capabilities = json.loads(REPOSITORY_CAPABILITIES_PATH.read_text(encoding="utf-8"))

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
        for tool in ("diagnose_backend", "last_startup_failure", "cancel_generation"):
            self.assertIn(tool, actual_tools)
        self.assertNotIn("generate_video", actual_tools)
        self.assertNotIn("generate_audio", actual_tools)
        self.assertNotIn("generate_3d", actual_tools)

    def test_mcp_file_policy_matches_server_and_persistent_profiles(self) -> None:
        policy = self.manifest["interfaces"]["mcp"]["file_policy"]
        self.assertFalse(policy["arbitrary_output_directories_allowed"])
        self.assertFalse(policy["tool_workflow_paths_default_allowed"])
        self.assertTrue(policy["ordinary_file_identity_required"])
        self.assertTrue(policy["image_signature_validation"])
        self.assertTrue(policy["persistent_profiles_keep_non_secret_policy"])
        source = MCP_PATH.read_text(encoding="utf-8")
        self.assertIn("EVAVO_MCP_OUTPUT_ROOTS", source)
        self.assertIn("EVAVO_MCP_ALLOW_WORKFLOW_PATHS", source)
        self.assertIn("EVAVO_MCP_WORKFLOW_ROOT", source)
        self.assertIn("_resolve_ordinary_file", source)
        self.assertIn("_has_valid_image_signature", source)
        self.assertIn("INVALID_FILE_OR_WAIT_POLICY", source)
        for script in (CLAUDE_INSTALLER, HTTP_AUTOSTART_INSTALLER):
            text = script.read_text(encoding="utf-8")
            self.assertIn('"EVAVO_MCP_OUTPUT_ROOTS"', text)
            self.assertIn('"EVAVO_MCP_ALLOW_WORKFLOW_PATHS"', text)
            self.assertIn('"EVAVO_MCP_WORKFLOW_ROOT"', text)
            self.assertNotIn('"EVAVO_CHECKPOINT_URL",', text)

    def test_mcp_generation_status_uses_public_jobs_history_and_queue_contract(self) -> None:
        status_contract = self.manifest["interfaces"]["mcp"]["generation_status"]
        self.assertEqual(set(status_contract["normalized_states"]), {"queued", "running", "completed", "failed", "cancelled", "unknown"})
        self.assertTrue(status_contract["failed_history_updates_shared_task_history"])
        self.assertTrue(status_contract["missing_prompt_is_unknown_not_queued"])
        self.assertIn("GET /api/jobs/<job_id>", self.manifest["native_comfyui_api"])
        self.assertIn("GET /queue", self.manifest["native_comfyui_api"])
        mcp_source = MCP_PATH.read_text(encoding="utf-8")
        backend_source = BACKEND_PATH.read_text(encoding="utf-8")
        status_source = STATUS_PATH.read_text(encoding="utf-8")
        self.assertIn("from .comfyui_status import prompt_status", mcp_source)
        self.assertIn("prompt_status", mcp_source)
        self.assertIn('error_code="COMFYUI_EXECUTION_FAILED"', mcp_source)
        self.assertIn("def job_detail(", backend_source)
        self.assertIn("def queue_state(", backend_source)
        self.assertIn("/api/jobs/", backend_source)
        self.assertIn("backend.job_detail(", status_source)
        self.assertIn("backend.queue_state()", status_source)
        self.assertNotIn("backend._request", status_source)
        self.assertIn('"cancelled": "cancelled"', status_source)
        self.assertIn('status = "unknown"', status_source)

    def test_mcp_cancellation_is_targeted_and_legacy_running_interrupt_is_forbidden(self) -> None:
        contract = self.manifest["interfaces"]["mcp"]["generation_cancellation"]
        self.assertEqual(contract["tool"], "cancel_generation")
        self.assertEqual(contract["preferred_endpoint"], "POST /api/jobs/<job_id>/cancel")
        self.assertTrue(contract["idempotent_terminal_or_unknown_noop"])
        self.assertTrue(contract["legacy_pending_queue_delete"])
        self.assertFalse(contract["legacy_running_broad_interrupt_allowed"])
        self.assertIn("POST /api/jobs/<job_id>/cancel", self.manifest["native_comfyui_api"])
        mcp_source = MCP_PATH.read_text(encoding="utf-8")
        backend_source = BACKEND_PATH.read_text(encoding="utf-8")
        cancel_source = CANCEL_PATH.read_text(encoding="utf-8")
        self.assertIn("from .comfyui_cancel import cancel_prompt", mcp_source)
        self.assertIn("async def cancel_generation", mcp_source)
        self.assertIn("def cancel_job(", backend_source)
        self.assertIn("def delete_pending(", backend_source)
        self.assertIn("backend.cancel_job(", cancel_source)
        self.assertIn("backend.delete_pending(", cancel_source)
        self.assertNotIn("backend._request", cancel_source)
        self.assertNotIn("backend._open", cancel_source)
        self.assertNotIn('"/interrupt"', cancel_source)

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

    def test_gateway_request_boundary_matches_manifest(self) -> None:
        gateway = self.manifest["interfaces"]["http_gateway"]
        self.assertTrue(gateway["structured_config_errors"])
        self.assertEqual(gateway["max_request_bytes_default"], 1024 * 1024)
        self.assertEqual(gateway["max_request_bytes_hard_cap"], 16 * 1024 * 1024)
        self.assertEqual(gateway["max_project_chars_default"], 128)
        self.assertFalse(gateway["request_workflow_path_default_allowed"])
        self.assertTrue(gateway["request_workflow_path_requires_root"])
        self.assertTrue(gateway["result_file_identity_required"])
        source = GATEWAY_PATH.read_text(encoding="utf-8")
        self.assertIn("class RequestBodyLimitMiddleware", source)
        self.assertIn("GATEWAY_CONFIG_INVALID", source)
        self.assertIn("EVAVO_GATEWAY_MAX_REQUEST_BYTES", source)
        self.assertIn("more_body", source)
        self.assertIn("EVAVO_GATEWAY_MAX_PROJECT_CHARS", source)
        self.assertIn("EVAVO_GATEWAY_ALLOW_REQUEST_WORKFLOW_PATHS", source)
        self.assertIn("EVAVO_GATEWAY_WORKFLOW_ROOT", source)
        self.assertIn("outside EVAVO_GATEWAY_WORKFLOW_ROOT", source)
        self.assertIn("per-request workflow_path is disabled", source)
        self.assertIn("_validated_result_path", source)
        self.assertIn("must not be a symlink", source)

    def test_gateway_task_state_safety_matches_manifest_and_public_lock_api(self) -> None:
        gateway = self.manifest["interfaces"]["http_gateway"]
        self.assertTrue(gateway["task_state_cross_process_lock"])
        self.assertTrue(gateway["task_id_allocation_interprocess_atomic"])
        self.assertTrue(gateway["single_live_gateway_per_task_state"])
        self.assertEqual(gateway["state_in_use_error"], "GATEWAY_STATE_IN_USE")
        self.assertTrue(gateway["corrupt_task_state_fail_closed"])
        source = GATEWAY_PATH.read_text(encoding="utf-8")
        operations = OPERATIONS_PATH.read_text(encoding="utf-8")
        self.assertIn("from evavo_operations import TaskTracker, interprocess_lock", source)
        self.assertIn("def interprocess_lock", operations)
        self.assertIn("_interprocess_lock = interprocess_lock", operations)
        self.assertIn("GATEWAY_INSTANCE_LOCK", source)
        self.assertIn("GATEWAY_STATE_IN_USE", source)
        self.assertIn("def _create_sync", source)
        self.assertIn("GATEWAY_TASK_STATE_CORRUPT", source)
        self.assertIn("await STORE.create(", source)

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
        self.assertIn("status_code=202", gateway_source)
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
        self.assertTrue(security["provider_receipt_digest_verification_when_supplied"])
        self.assertTrue(security["provider_source_and_destination_symlink_rejection"])
        self.assertIn("provider artifact must not be a symlink", source)
        self.assertIn("provider destination must not be a symlink", source)
        self.assertIn("os.replace(temp_name, destination_lexical)", source)

    def test_service_manager_state_and_secret_contract_is_fail_closed_and_serialized(self) -> None:
        security = self.manifest["security"]
        self.assertTrue(security["service_manager_state_corruption_fail_closed"])
        self.assertTrue(security["service_manager_state_interprocess_lock"])
        self.assertTrue(security["service_manager_lifecycle_interprocess_lock"])
        self.assertFalse(security["service_manager_provider_secret_plaintext_in_state"])
        source = MANAGER_PATH.read_text(encoding="utf-8")
        self.assertIn("SERVICE_MANAGER_STATE_CORRUPT", source)
        self.assertIn("manager_state_health", source)
        self.assertIn("STATE_IO_LOCK", source)
        self.assertIn("LIFECYCLE_LOCK", source)
        self.assertIn("SERVICE_MANAGER_BUSY", source)
        self.assertIn("3d_token_sha256", source)
        self.assertNotIn('"3d_token": token', source)
        self.assertIn("state file must not be a symlink", source)

    def test_brain_capabilities_expose_hardened_gateway_without_claiming_mcp_ownership(self) -> None:
        self.assertEqual(self.repository_capabilities["authority"], "local-image-generation-control-plane")
        capabilities = {item.get("id"): item for item in self.repository_capabilities.get("capabilities", []) if isinstance(item, dict)}
        private_gateway = capabilities.get("local-image.gateway.private-contract")
        delegation = capabilities.get("local-image.gateway.aux-provider-delegation")
        self.assertIsNotNone(private_gateway)
        self.assertIsNotNone(delegation)
        private_description = str(private_gateway.get("description", "")).lower()
        self.assertIn("request", private_description)
        self.assertIn("one live gateway owner", private_description)
        self.assertIn("gateway_state_in_use", private_description)
        self.assertIn("fail-closed", str(delegation.get("description", "")).lower())
        self.assertNotIn("mcp", {str(value).lower() for value in delegation.get("interfaces", [])})

    def test_security_contract_rejects_old_dangerous_defaults(self) -> None:
        security = self.manifest["security"]
        self.assertFalse(security["public_bind_by_default"])
        self.assertFalse(security["gateway_wildcard_cors_by_default"])
        self.assertTrue(security["gateway_request_preparse_size_limit"])
        self.assertTrue(security["gateway_chunked_request_limit"])
        self.assertFalse(security["gateway_request_workflow_path_default_allowed"])
        self.assertTrue(security["gateway_request_workflow_root_confinement"])
        self.assertTrue(security["gateway_result_symlink_or_parent_redirection_rejected"])
        self.assertTrue(security["gateway_structured_config_errors"])
        self.assertTrue(security["gateway_task_state_corruption_fail_closed"])
        self.assertTrue(security["gateway_task_id_interprocess_atomic"])
        self.assertTrue(security["gateway_task_state_single_live_owner"])
        self.assertTrue(security["service_manager_state_corruption_fail_closed"])
        self.assertTrue(security["service_manager_state_interprocess_lock"])
        self.assertTrue(security["service_manager_lifecycle_interprocess_lock"])
        self.assertFalse(security["service_manager_provider_secret_plaintext_in_state"])
        self.assertFalse(security["mcp_tool_workflow_path_default_allowed"])
        self.assertTrue(security["mcp_tool_workflow_root_confinement"])
        self.assertTrue(security["mcp_output_directory_root_confinement"])
        self.assertTrue(security["mcp_output_symlink_or_parent_redirection_rejected"])
        self.assertTrue(security["mcp_image_signature_validation"])
        self.assertTrue(security["mcp_invalid_file_or_wait_policy_preflight"])
        self.assertTrue(security["mcp_failed_prompt_not_reported_as_queued"])
        self.assertTrue(security["mcp_targeted_cancel_preferred"])
        self.assertFalse(security["mcp_legacy_running_broad_interrupt_allowed"])
        self.assertFalse(security["broad_python_process_kill"])
        self.assertTrue(security["managed_process_identity_verification"])
        self.assertTrue(security["chatgpt_tunnel_executable_sha256_verification"])
        self.assertFalse(security["plaintext_tunnel_key_in_repo_or_startup"])
        self.assertFalse(security["arbitrary_model_url_from_mcp_tool"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
