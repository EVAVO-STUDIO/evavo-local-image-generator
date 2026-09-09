#!/usr/bin/env python3
"""Subprocess-level configuration safety tests for EVAVO-SERVICE-MANAGER.py."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANAGER = ROOT / "EVAVO-SERVICE-MANAGER.py"


class ServiceManagerConfigurationSafetyTests(unittest.TestCase):
    def base_env(self, state_dir: Path) -> dict[str, str]:
        env = os.environ.copy()
        env["EVAVO_GATEWAY_STATE_DIR"] = str(state_dir)
        env["EVAVO_GATEWAY_HOST"] = "127.0.0.1"
        env["EVAVO_GATEWAY_PORT"] = "8000"
        env["EVAVO_3D_ENDPOINT"] = "http://127.0.0.1:4314"
        env["EVAVO_GATEWAY_COMFYUI_START_TIMEOUT"] = "120"
        return env

    def run_manager(self, env: dict[str, str], *args: str, timeout: float = 10.0) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(MANAGER), *args],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def test_invalid_gateway_port_fails_with_stable_config_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            env = self.base_env(Path(temp))
            env["EVAVO_GATEWAY_PORT"] = "not-a-port"
            result = self.run_manager(env, "health")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SERVICE_MANAGER_CONFIG_INVALID:EVAVO_GATEWAY_PORT", result.stdout + result.stderr)

    def test_out_of_range_gateway_port_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            env = self.base_env(Path(temp))
            env["EVAVO_GATEWAY_PORT"] = "70000"
            result = self.run_manager(env, "health")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SERVICE_MANAGER_CONFIG_INVALID:EVAVO_GATEWAY_PORT", result.stdout + result.stderr)
        self.assertIn("between 1 and 65535", result.stdout + result.stderr)

    def test_remote_3d_endpoint_is_rejected_before_health_probe(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            env = self.base_env(Path(temp))
            env["EVAVO_3D_ENDPOINT"] = "http://example.com:4314"
            result = self.run_manager(env, "health")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SERVICE_MANAGER_CONFIG_INVALID:EVAVO_3D_ENDPOINT", result.stdout + result.stderr)
        self.assertIn("loopback", (result.stdout + result.stderr).lower())

    def test_invalid_3d_endpoint_port_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            env = self.base_env(Path(temp))
            env["EVAVO_3D_ENDPOINT"] = "http://localhost:99999"
            result = self.run_manager(env, "health")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SERVICE_MANAGER_CONFIG_INVALID:EVAVO_3D_ENDPOINT", result.stdout + result.stderr)
        self.assertIn("invalid port", (result.stdout + result.stderr).lower())

    def test_nonfinite_comfyui_start_timeout_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            env = self.base_env(Path(temp))
            env["EVAVO_GATEWAY_COMFYUI_START_TIMEOUT"] = "nan"
            result = self.run_manager(env, "health")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SERVICE_MANAGER_CONFIG_INVALID:EVAVO_GATEWAY_COMFYUI_START_TIMEOUT", result.stdout + result.stderr)
        self.assertIn("finite", (result.stdout + result.stderr).lower())

    def test_monitor_interval_rejects_nonfinite_value_before_start(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            env = self.base_env(Path(temp))
            result = self.run_manager(env, "monitor", "--interval", "nan")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("finite value between 1 and 3600", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
