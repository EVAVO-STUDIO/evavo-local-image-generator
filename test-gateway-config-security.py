#!/usr/bin/env python3
"""Focused offline/subprocess tests for gateway configuration security boundaries."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GATEWAY = ROOT / "EVAVO-GATEWAY.py"


def gateway_import(env: dict[str, str], code: str = "print('ok')") -> subprocess.CompletedProcess[str]:
    script = textwrap.dedent(
        f"""
        import importlib.util
        spec = importlib.util.spec_from_file_location('evavo_gateway_config_test', {str(GATEWAY)!r})
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        {code}
        """
    )
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )


class GatewayConfigSecurityTests(unittest.TestCase):
    def base_env(self, root: Path) -> dict[str, str]:
        env = os.environ.copy()
        env["EVAVO_GATEWAY_STATE_DIR"] = str(root / "state")
        env["EVAVO_GATEWAY_TASK_FILE"] = str(root / "state" / "tasks.json")
        env["EVAVO_GATEWAY_RESULT_DIR"] = str(root / "results")
        env.pop("EVAVO_GATEWAY_ALLOW_REQUEST_WORKFLOW_PATHS", None)
        env.pop("EVAVO_GATEWAY_WORKFLOW_ROOT", None)
        env.pop("EVAVO_COMFYUI_WORKFLOW", None)
        return env

    def test_invalid_numeric_config_has_stable_category(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            env = self.base_env(Path(temp))
            env["EVAVO_GATEWAY_PORT"] = "not-a-port"
            result = gateway_import(env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("GATEWAY_CONFIG_INVALID:EVAVO_GATEWAY_PORT", result.stderr + result.stdout)

    def test_workflow_path_opt_in_requires_owner_selected_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            env = self.base_env(Path(temp))
            env["EVAVO_GATEWAY_ALLOW_REQUEST_WORKFLOW_PATHS"] = "1"
            result = gateway_import(env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("GATEWAY_CONFIG_INVALID:EVAVO_GATEWAY_WORKFLOW_ROOT", result.stderr + result.stdout)

    def test_workflow_path_is_confined_to_configured_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            workflow_root = base / "workflows"
            workflow_root.mkdir()
            inside = workflow_root / "inside.json"
            inside.write_text("{}\n", encoding="utf-8")
            outside = base / "outside.json"
            outside.write_text("{}\n", encoding="utf-8")
            env = self.base_env(base)
            env["EVAVO_GATEWAY_ALLOW_REQUEST_WORKFLOW_PATHS"] = "1"
            env["EVAVO_GATEWAY_WORKFLOW_ROOT"] = str(workflow_root)
            code = textwrap.dedent(
                f"""
                import json
                from fastapi import HTTPException
                inside = module._request_workflow_path({str(inside)!r})
                outside_status = None
                try:
                    module._request_workflow_path({str(outside)!r})
                except HTTPException as exc:
                    outside_status = exc.status_code
                print(json.dumps({{'inside': inside, 'outside_status': outside_status}}))
                """
            )
            result = gateway_import(env, code)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(Path(payload["inside"]), inside.resolve())
        self.assertEqual(payload["outside_status"], 403)

    def test_workflow_symlink_is_rejected_even_inside_owner_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            workflow_root = base / "workflows"
            workflow_root.mkdir()
            real = workflow_root / "real.json"
            real.write_text("{}\n", encoding="utf-8")
            link = workflow_root / "link.json"
            try:
                link.symlink_to(real)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"symlinks unavailable: {exc}")
            env = self.base_env(base)
            env["EVAVO_GATEWAY_ALLOW_REQUEST_WORKFLOW_PATHS"] = "1"
            env["EVAVO_GATEWAY_WORKFLOW_ROOT"] = str(workflow_root)
            code = textwrap.dedent(
                f"""
                import json
                from fastapi import HTTPException
                status = None
                detail = None
                try:
                    module._request_workflow_path({str(link)!r})
                except HTTPException as exc:
                    status = exc.status_code
                    detail = str(exc.detail)
                print(json.dumps({{'status': status, 'detail': detail}}))
                """
            )
            result = gateway_import(env, code)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(payload["status"], 422)
        self.assertIn("symlink", payload["detail"].lower())

    def test_result_symlink_swap_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            task_id = "img_1234567890"
            result_root = base / "results"
            task_root = result_root / task_id
            task_root.mkdir(parents=True)
            external = base / "external.png"
            external.write_bytes(b"not served")
            link = task_root / "generated.png"
            try:
                link.symlink_to(external)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"symlinks unavailable: {exc}")
            env = self.base_env(base)
            code = textwrap.dedent(
                f"""
                import json
                from fastapi import HTTPException
                status = None
                detail = None
                try:
                    module._validated_result_path({str(link)!r}, {task_id!r})
                except HTTPException as exc:
                    status = exc.status_code
                    detail = str(exc.detail)
                print(json.dumps({{'status': status, 'detail': detail}}))
                """
            )
            result = gateway_import(env, code)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(payload["status"], 410)
        self.assertIn("symlink", payload["detail"].lower())

    def test_public_interprocess_lock_api_is_used(self) -> None:
        gateway_source = GATEWAY.read_text(encoding="utf-8")
        operations_source = (ROOT / "evavo_operations.py").read_text(encoding="utf-8")
        self.assertIn("def interprocess_lock(", operations_source)
        self.assertIn("_interprocess_lock = interprocess_lock", operations_source)
        self.assertIn("from evavo_operations import TaskTracker, interprocess_lock", gateway_source)
        self.assertNotIn("from evavo_operations import TaskTracker, _interprocess_lock", gateway_source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
