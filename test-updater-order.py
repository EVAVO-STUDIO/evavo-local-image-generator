#!/usr/bin/env python3
"""Offline contract tests for canonical Windows updater ordering."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UPDATER = ROOT / "UPDATE-AND-VERIFY-EVAVO.ps1"


class UpdaterOrderingTests(unittest.TestCase):
    def test_native_backend_preparation_precedes_strict_bootstrap(self) -> None:
        source = UPDATER.read_text(encoding="utf-8")
        verify_index = source.index("verify --full --require-powershell")
        backend_index = source.index("Preparing and validating the native ComfyUI generation contract")
        bootstrap_index = source.index("bootstrap --skip-pull --skip-verify")
        claude_index = source.index("Installing/updating Claude Desktop stdio MCP configuration")
        self.assertLess(verify_index, backend_index)
        self.assertLess(backend_index, bootstrap_index)
        self.assertLess(bootstrap_index, claude_index)

    def test_prebootstrap_doctor_supports_optional_provisioning(self) -> None:
        source = UPDATER.read_text(encoding="utf-8")
        self.assertIn('$backendDoctorArgs += "--provision"', source)
        self.assertIn("if (-not $SkipComfyUIProvision)", source)
        self.assertIn("Native ComfyUI generation readiness failed while provisioning was disabled", source)

    def test_final_doctor_does_not_reprovision_late_in_setup(self) -> None:
        source = UPDATER.read_text(encoding="utf-8")
        final_start = source.index("$finalDoctorArgs = @(")
        final_end = source.index("& $python @finalDoctorArgs", final_start)
        final_block = source[final_start:final_end]
        self.assertIn('"--repair"', final_block)
        self.assertNotIn('"--provision"', final_block)

    def test_bootstrap_itself_is_strict_native(self) -> None:
        controller = (ROOT / "evavo.py").read_text(encoding="utf-8")
        self.assertIn('[sys.executable, controller, "start", "--endpoint", endpoint, "--no-mock"]', controller)


if __name__ == "__main__":
    unittest.main(verbosity=2)
