#!/usr/bin/env python3
"""Safety tests for agent-exposed ComfyUI dependency repair."""

from __future__ import annotations

import inspect
import unittest
from unittest.mock import patch

from evavo_local_image_generator import comfyui_repair, mcp_server


class ComfyUIRepairSafetyTests(unittest.TestCase):
    def test_mcp_tool_does_not_accept_arbitrary_module_or_package_input(self) -> None:
        parameters = inspect.signature(mcp_server.repair_backend_dependencies).parameters
        self.assertEqual(set(parameters), {"force_sync", "verify_only", "timeout_seconds"})
        self.assertNotIn("module", parameters)
        self.assertNotIn("package", parameters)
        self.assertNotIn("requirements", parameters)
        self.assertNotIn("url", parameters)

    def test_normal_repair_requires_structured_missing_dependency_evidence(self) -> None:
        with patch.object(comfyui_repair, "load_last_failure", return_value={}):
            result = comfyui_repair.repair_backend_dependencies(timeout_seconds=10)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "NO_REPAIR_EVIDENCE")
        self.assertFalse(result["repair_performed"])

    def test_custom_node_failure_does_not_mutate_core_requirements(self) -> None:
        failure = {"category": "custom_node_dependency", "missing_modules": ["custom_module"]}
        with patch.object(comfyui_repair, "load_last_failure", return_value=failure):
            result = comfyui_repair.repair_backend_dependencies(timeout_seconds=10)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "CUSTOM_NODE_DEPENDENCY")
        self.assertFalse(result["repair_performed"])

    def test_repair_command_uses_fixed_script_without_shell(self) -> None:
        command = comfyui_repair.build_repair_command(module="comfy_aimdo", timeout_seconds=60, verify_only=True)
        self.assertEqual(command[0], comfyui_repair.sys.executable)
        self.assertEqual(command[1], str(comfyui_repair.REPAIR_SCRIPT))
        self.assertIn("--module", command)
        self.assertIn("comfy_aimdo", command)
        self.assertIn("--verify-only", command)
        source = comfyui_repair.__file__
        self.assertTrue(source)
        text = open(source, "r", encoding="utf-8").read()
        self.assertIn("subprocess.run", text)
        self.assertNotIn("shell=True", text)

    def test_invalid_module_name_is_rejected_before_process_launch(self) -> None:
        with self.assertRaises(ValueError):
            comfyui_repair.build_repair_command(module="requests; calc.exe", timeout_seconds=60)

    def test_timeout_is_bounded_and_finite(self) -> None:
        for value in (0, -1, float("nan"), float("inf"), 3601):
            with self.subTest(value=value), self.assertRaises(ValueError):
                comfyui_repair.build_repair_command(module="comfy_aimdo", timeout_seconds=value)


if __name__ == "__main__":
    unittest.main(verbosity=2)
