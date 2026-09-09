#!/usr/bin/env python3
"""Regression tests for the authoritative verifier's suite discovery."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VERIFIER_PATH = ROOT / "verify-evavo.py"


def load_verifier():
    spec = importlib.util.spec_from_file_location("evavo_verify_module", VERIFIER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load verify-evavo.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class VerifierDiscoveryTests(unittest.TestCase):
    def test_discovers_root_repository_and_package_suites(self) -> None:
        verifier = load_verifier()
        tests = set(verifier.discover_tests())
        required = {
            "test-agent-doctor-config.py",
            "test-agent-status-contract.py",
            "test-capability-manifest.py",
            "test-comfyui-cancel.py",
            "test-comfyui-repair-cli.py",
            "test-comfyui-repair-safety.py",
            "test-comfyui-status.py",
            "test-comfyui-terminal-wait.py",
            "test-dependency-contract.py",
            "test-gateway.py",
            "test-gateway-config-safety.py",
            "test-gateway-config-security.py",
            "test-service-manager-config-safety.py",
            "test-mcp-cancel-integration.py",
            "test-mcp-entry-manifest.py",
            "test-mcp-entry-policy.py",
            "test-mcp-output-security.py",
            "test-mcp-policy-parity.py",
            "test-mcp-profile-policy.py",
            "test-mcp-recovery-parity.py",
            "test-mcp-request-validation.py",
            "test-mcp-status-integration.py",
            "test-real-generation-contract.py",
            "test-real-generation-smoke.py",
            "test-task-cancellation-history.py",
            "test-updater-dependency-recovery.py",
            "test-updater-order.py",
            "test-verifier-timeout.py",
            "test-legacy-compatibility.py",
            "test-package-direct-execution.py",
            "test-agent-stop-safety.py",
            "test_autonomous.py",
            "tests/test_gateway_providers.py",
            "tests/test_gateway_service_manager_providers.py",
            "tests/test_gateway_service_manager_locking.py",
            "evavo_local_image_generator/tests/test_backends.py",
            "evavo_local_image_generator/tests/test_generators.py",
            "evavo_local_image_generator/tests/test_unsupported_modalities.py",
        }
        self.assertTrue(required.issubset(tests), sorted(required - tests))

    def test_test_inventory_is_deterministic_and_unique(self) -> None:
        verifier = load_verifier()
        tests = verifier.discover_tests()
        self.assertEqual(tests, sorted(tests))
        self.assertEqual(len(tests), len(set(tests)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
