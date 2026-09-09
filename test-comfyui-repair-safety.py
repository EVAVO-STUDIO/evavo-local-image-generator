#!/usr/bin/env python3
"""Safety tests for agent-exposed ComfyUI dependency repair."""

from __future__ import annotations

import importlib.util
import inspect
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from evavo_local_image_generator import comfyui_repair, mcp_server

ROOT = Path(__file__).resolve().parent
STANDALONE_REPAIR = ROOT / "repair-comfyui-dependencies.py"


def load_standalone_repair():
    spec = importlib.util.spec_from_file_location("evavo_standalone_repair_test", STANDALONE_REPAIR)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load repair-comfyui-dependencies.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ComfyUIRepairSafetyTests(unittest.TestCase):
    def test_fixed_repair_module_and_script_are_present(self) -> None:
        self.assertTrue(Path(comfyui_repair.__file__).is_file())
        self.assertTrue(comfyui_repair.REPAIR_SCRIPT.is_file())
        self.assertEqual(comfyui_repair.REPAIR_SCRIPT.name, "repair-comfyui-dependencies.py")

    def test_mcp_tool_does_not_accept_arbitrary_module_or_package_input(self) -> None:
        parameters = inspect.signature(mcp_server.repair_backend_dependencies).parameters
        self.assertEqual(set(parameters), {"force_sync", "verify_only", "timeout_seconds"})
        self.assertNotIn("module", parameters)
        self.assertNotIn("package", parameters)
        self.assertNotIn("requirements", parameters)
        self.assertNotIn("url", parameters)

    def test_normal_repair_requires_structured_missing_dependency_evidence(self) -> None:
        with patch.object(comfyui_repair, "_latest_repair_evidence", return_value={}):
            result = comfyui_repair.repair_backend_dependencies(timeout_seconds=10)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "NO_REPAIR_EVIDENCE")
        self.assertFalse(result["repair_performed"])

    def test_force_sync_requires_owner_environment_authorization_before_evidence_or_process_work(self) -> None:
        with (
            patch.dict(os.environ, {"EVAVO_ALLOW_FORCED_DEPENDENCY_REPAIR": "0"}, clear=False),
            patch.object(comfyui_repair, "_latest_repair_evidence") as evidence,
            patch.object(comfyui_repair.subprocess, "run") as run,
        ):
            result = comfyui_repair.repair_backend_dependencies(force_sync=True, timeout_seconds=10)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "FORCE_SYNC_NOT_AUTHORIZED")
        self.assertFalse(result["repair_performed"])
        evidence.assert_not_called()
        run.assert_not_called()

    def test_custom_node_failure_does_not_mutate_core_requirements(self) -> None:
        failure = {"category": "custom_node_dependency", "missing_modules": ["custom_module"]}
        with patch.object(comfyui_repair, "_latest_repair_evidence", return_value=failure):
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
        source = Path(comfyui_repair.__file__).read_text(encoding="utf-8")
        self.assertIn("subprocess.run", source)
        self.assertIn("shell=False", source)
        self.assertNotIn("shell=True", source)

    def test_build_command_carries_exact_comfy_home_and_python(self) -> None:
        home = Path("C:/Gitrepos/ComfyUI")
        python = Path("C:/Gitrepos/ComfyUI/.venv/Scripts/python.exe")
        command = comfyui_repair.build_repair_command(
            module="comfy_aimdo",
            timeout_seconds=60,
            comfy_home=home,
            python_exe=python,
        )
        self.assertEqual(command[command.index("--comfy-home") + 1], str(home))
        self.assertEqual(command[command.index("--python") + 1], str(python))

    def test_structured_startup_failure_selects_exact_diagnosed_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            home = base / "portable" / "ComfyUI"
            home.mkdir(parents=True)
            (home / "main.py").write_text("# fixture\n", encoding="utf-8")
            (home / "requirements.txt").write_text("# fixture\n", encoding="utf-8")
            python = base / "portable" / "python_embeded" / "python.exe"
            python.parent.mkdir(parents=True)
            python.write_bytes(b"fixture")
            evidence = {
                "category": "missing_dependency",
                "missing_modules": ["comfy_aimdo"],
                "install": {"workdir": str(home), "python": str(python)},
            }
            target = comfyui_repair._repair_target(evidence)
        self.assertIsNotNone(target)
        assert target is not None
        self.assertEqual(target[0], home.resolve())
        self.assertEqual(target[1], python.resolve())
        self.assertEqual(target[2], "startup_failure")

    def test_discovery_fallback_uses_same_first_install_contract_as_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            home = base / "ComfyUI"
            home.mkdir()
            (home / "main.py").write_text("# fixture\n", encoding="utf-8")
            (home / "requirements.txt").write_text("# fixture\n", encoding="utf-8")
            python = home / ".venv" / "Scripts" / "python.exe"
            python.parent.mkdir(parents=True)
            python.write_bytes(b"fixture")
            install = SimpleNamespace(workdir=home.resolve(), python=python.resolve())
            with patch.object(comfyui_repair, "discover_comfyui", return_value=[install]):
                target = comfyui_repair._repair_target({})
        self.assertIsNotNone(target)
        assert target is not None
        self.assertEqual(target[0], home.resolve())
        self.assertEqual(target[1], python.resolve())
        self.assertEqual(target[2], "discovery")

    def test_repair_receipt_proves_selected_runtime_handoff_without_running_pip(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            home = base / "ComfyUI"
            home.mkdir()
            (home / "main.py").write_text("# fixture\n", encoding="utf-8")
            (home / "requirements.txt").write_text("# fixture\n", encoding="utf-8")
            python = home / ".venv" / "Scripts" / "python.exe"
            python.parent.mkdir(parents=True)
            python.write_bytes(b"fixture")
            evidence = {
                "category": "missing_dependency",
                "missing_modules": ["comfy_aimdo"],
                "install": {"workdir": str(home), "python": str(python)},
                "evidence_source": "test",
            }
            receipt = {"ok": True, "status": "repaired", "repair_performed": True}
            completed = subprocess.CompletedProcess([], 0, stdout=json.dumps(receipt), stderr="")
            with (
                patch.object(comfyui_repair, "_latest_repair_evidence", return_value=evidence),
                patch.object(comfyui_repair.subprocess, "run", return_value=completed) as run,
            ):
                result = comfyui_repair.repair_backend_dependencies(timeout_seconds=60)
        command = run.call_args.args[0]
        self.assertEqual(command[command.index("--comfy-home") + 1], str(home.resolve()))
        self.assertEqual(command[command.index("--python") + 1], str(python.resolve()))
        self.assertTrue(result["used_selected_runtime"])
        self.assertEqual(result["target_source"], "startup_failure")
        self.assertEqual(result["selected_comfy_home"], str(home.resolve()))
        self.assertEqual(result["selected_python"], str(python.resolve()))

    def test_standalone_discovery_accepts_portable_parent_layout(self) -> None:
        standalone = load_standalone_repair()
        with tempfile.TemporaryDirectory() as temp:
            portable = Path(temp) / "ComfyUI_windows_portable"
            home = portable / "ComfyUI"
            home.mkdir(parents=True)
            (home / "main.py").write_text("# fixture\n", encoding="utf-8")
            (home / "requirements.txt").write_text("# fixture\n", encoding="utf-8")
            python = portable / "python_embeded" / "python.exe"
            python.parent.mkdir(parents=True)
            python.write_bytes(b"fixture")
            self.assertEqual(standalone._discover_home(str(portable)), home.resolve())
            self.assertEqual(standalone._select_python(home), python.resolve())

    def test_standalone_discovery_honors_extra_search_paths(self) -> None:
        standalone = load_standalone_repair()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "custom-search" / "ComfyUI"
            root.mkdir(parents=True)
            (root / "main.py").write_text("# fixture\n", encoding="utf-8")
            (root / "requirements.txt").write_text("# fixture\n", encoding="utf-8")
            python = root / ".venv" / "Scripts" / "python.exe"
            python.parent.mkdir(parents=True)
            python.write_bytes(b"fixture")
            with patch.dict(os.environ, {"EVAVO_COMFYUI_SEARCH_PATHS": str(root)}, clear=False):
                discovered = standalone._discover_home()
            self.assertEqual(discovered, root.resolve())

    def test_invalid_module_name_is_rejected_before_process_launch(self) -> None:
        with self.assertRaises(ValueError):
            comfyui_repair.build_repair_command(module="requests; calc.exe", timeout_seconds=60)

    def test_timeout_is_bounded_and_finite(self) -> None:
        for value in (0, -1, float("nan"), float("inf"), 3601):
            with self.subTest(value=value), self.assertRaises(ValueError):
                comfyui_repair.build_repair_command(module="comfy_aimdo", timeout_seconds=value)


if __name__ == "__main__":
    unittest.main(verbosity=2)
