#!/usr/bin/env python3
"""Runtime parity tests for read-only MCP policy validation vs server enforcement."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evavo_local_image_generator import mcp_policy, mcp_server


POLICY_ENV = (
    "COMFYUI_ENDPOINT",
    "EVAVO_COMFYUI_ENDPOINT",
    "EVAVO_GENERATION_OUTPUT_DIR",
    "EVAVO_MCP_OUTPUT_ROOTS",
    "EVAVO_COMFYUI_WORKFLOW",
    "EVAVO_MCP_ALLOW_WORKFLOW_PATHS",
    "EVAVO_MCP_WORKFLOW_ROOT",
)


def clean_env() -> dict[str, str]:
    env = os.environ.copy()
    for name in POLICY_ENV:
        env.pop(name, None)
    return env


class McpPolicyParityTests(unittest.TestCase):
    def test_default_loopback_endpoint_matches_server_default(self) -> None:
        with patch.dict(os.environ, clean_env(), clear=True):
            policy = mcp_policy.validate_environment()
            endpoint = mcp_server._endpoint()
        self.assertTrue(policy["ok"], policy)
        self.assertEqual(policy["policy"]["comfyui_endpoint"], "http://127.0.0.1:8188")
        self.assertEqual(endpoint, "http://127.0.0.1:8188")

    def test_canonical_endpoint_wins_over_conflicting_legacy_alias(self) -> None:
        env = clean_env()
        env["COMFYUI_ENDPOINT"] = "http://localhost:18188/"
        env["EVAVO_COMFYUI_ENDPOINT"] = "http://127.0.0.1:9999"
        with patch.dict(os.environ, env, clear=True):
            policy = mcp_policy.validate_environment()
            endpoint = mcp_server._endpoint()
        self.assertTrue(policy["ok"], policy)
        self.assertEqual(policy["policy"]["comfyui_endpoint"], "http://localhost:18188")
        self.assertEqual(endpoint, "http://localhost:18188")
        self.assertTrue(any("ignored" in warning for warning in policy["warnings"]))

    def test_legacy_endpoint_is_migration_input_with_warning(self) -> None:
        env = clean_env()
        env["EVAVO_COMFYUI_ENDPOINT"] = "http://127.0.0.1:18189/"
        with patch.dict(os.environ, env, clear=True):
            policy = mcp_policy.validate_environment()
        self.assertTrue(policy["ok"], policy)
        self.assertEqual(policy["policy"]["comfyui_endpoint"], "http://127.0.0.1:18189")
        self.assertTrue(any("migration input" in warning for warning in policy["warnings"]))

    def test_remote_or_nonlocal_endpoint_is_rejected_before_mcp_start(self) -> None:
        for endpoint in (
            "http://192.168.1.50:8188",
            "http://example.com:8188",
            "https://127.0.0.1:8188",
            "http://user:pass@127.0.0.1:8188",
            "http://127.0.0.1:8188/api",
            "http://127.0.0.1:8188?x=1",
            "http://127.0.0.1:8188#fragment",
        ):
            env = clean_env()
            env["COMFYUI_ENDPOINT"] = endpoint
            with self.subTest(endpoint=endpoint), patch.dict(os.environ, env, clear=True):
                policy = mcp_policy.validate_environment()
            self.assertFalse(policy["ok"])
            self.assertIsNone(policy["policy"]["comfyui_endpoint"])
            self.assertTrue(any("COMFYUI_ENDPOINT" in error for error in policy["errors"]))

    def test_ipv6_loopback_is_normalized(self) -> None:
        env = clean_env()
        env["COMFYUI_ENDPOINT"] = "http://[::1]:8188/"
        with patch.dict(os.environ, env, clear=True):
            policy = mcp_policy.validate_environment()
        self.assertTrue(policy["ok"], policy)
        self.assertEqual(policy["policy"]["comfyui_endpoint"], "http://[::1]:8188")

    def test_default_and_additional_output_roots_match_server_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            default_root = base / "default-output"
            additional = base / "approved-output"
            additional.mkdir()
            env = clean_env()
            env["EVAVO_GENERATION_OUTPUT_DIR"] = str(default_root)
            env["EVAVO_MCP_OUTPUT_ROOTS"] = str(additional)
            with patch.dict(os.environ, env, clear=True):
                policy = mcp_policy.validate_environment()
                server_roots = mcp_server._allowed_output_roots()
                nested = mcp_server._validated_output_dir(str(additional / "project"))

        self.assertTrue(policy["ok"], policy)
        self.assertEqual(Path(policy["policy"]["default_output_root"]), default_root.resolve())
        self.assertIn(additional.resolve(), server_roots)
        self.assertEqual(nested, additional.resolve() / "project")

    def test_missing_additional_output_root_fails_both_layers(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            missing = Path(temp) / "missing"
            env = clean_env()
            env["EVAVO_MCP_OUTPUT_ROOTS"] = str(missing)
            with patch.dict(os.environ, env, clear=True):
                policy = mcp_policy.validate_environment()
                with self.assertRaisesRegex(RuntimeError, "MCP_OUTPUT_ROOT_INVALID"):
                    mcp_server._allowed_output_roots()

        self.assertFalse(policy["ok"])
        self.assertTrue(any("EVAVO_MCP_OUTPUT_ROOTS" in item for item in policy["errors"]))

    def test_tool_workflow_opt_in_without_root_fails_both_layers(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workflow = Path(temp) / "workflow.json"
            workflow.write_text("{}\n", encoding="utf-8")
            env = clean_env()
            env["EVAVO_MCP_ALLOW_WORKFLOW_PATHS"] = "1"
            with patch.dict(os.environ, env, clear=True):
                policy = mcp_policy.validate_environment()
                with self.assertRaisesRegex(RuntimeError, "MCP_WORKFLOW_ROOT_REQUIRED"):
                    mcp_server._validated_workflow_path(str(workflow))

        self.assertFalse(policy["ok"])
        self.assertTrue(any("EVAVO_MCP_WORKFLOW_ROOT" in item for item in policy["errors"]))

    def test_reviewed_workflow_root_is_accepted_by_both_layers(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "workflows"
            root.mkdir()
            workflow = root / "production.json"
            workflow.write_text("{}\n", encoding="utf-8")
            env = clean_env()
            env["EVAVO_MCP_ALLOW_WORKFLOW_PATHS"] = "1"
            env["EVAVO_MCP_WORKFLOW_ROOT"] = str(root)
            with patch.dict(os.environ, env, clear=True):
                policy = mcp_policy.validate_environment()
                selected = mcp_server._validated_workflow_path(str(workflow))

        self.assertTrue(policy["ok"], policy)
        self.assertEqual(Path(policy["policy"]["tool_workflow_root"]), root.resolve())
        self.assertEqual(Path(str(selected)), workflow.resolve())

    def test_owner_default_workflow_does_not_require_tool_path_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workflow = Path(temp) / "owner.json"
            workflow.write_text("{}\n", encoding="utf-8")
            env = clean_env()
            env["EVAVO_COMFYUI_WORKFLOW"] = str(workflow)
            with patch.dict(os.environ, env, clear=True):
                policy = mcp_policy.validate_environment()
                selected = mcp_server._effective_workflow_path(None)

        self.assertTrue(policy["ok"], policy)
        self.assertFalse(policy["policy"]["tool_workflow_paths_allowed"])
        self.assertEqual(Path(str(selected)), workflow.resolve())


if __name__ == "__main__":
    unittest.main(verbosity=2)
