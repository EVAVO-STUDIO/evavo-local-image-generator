#!/usr/bin/env python3
"""Offline contract tests for canonical Windows updater ordering."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UPDATER = ROOT / "UPDATE-AND-VERIFY-EVAVO.ps1"


class UpdaterOrderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = UPDATER.read_text(encoding="utf-8")

    def test_native_backend_preparation_precedes_strict_bootstrap(self) -> None:
        source = self.source
        verify_index = source.index("verify --full --require-powershell")
        backend_index = source.index("Preparing and validating the native ComfyUI generation contract")
        bootstrap_index = source.index("bootstrap --skip-pull --skip-verify")
        self.assertLess(verify_index, backend_index)
        self.assertLess(backend_index, bootstrap_index)

    def test_prebootstrap_doctor_supports_optional_provisioning(self) -> None:
        source = self.source
        self.assertIn('$backendDoctorArgs += "--provision"', source)
        self.assertIn("if (-not $SkipComfyUIProvision)", source)

    def test_dependency_recovery_is_one_evidence_gated_retry_after_strict_doctor_failure(self) -> None:
        source = self.source
        doctor_run = source.index("& $python @backendDoctorArgs")
        recovery_guard = source.index("if ($backendDoctorCode -ne 0 -and -not $SkipComfyUIDependencyRepair)")
        recovery_run = source.index('recover-comfyui.py") --json')
        retry_doctor = source.index("& $python @backendDoctorArgs", doctor_run + 1)
        bootstrap = source.index("bootstrap --skip-pull --skip-verify")
        self.assertLess(doctor_run, recovery_guard)
        self.assertLess(recovery_guard, recovery_run)
        self.assertLess(recovery_run, retry_doctor)
        self.assertLess(retry_doctor, bootstrap)
        self.assertEqual(source.count('recover-comfyui.py") --json'), 1)
        self.assertIn("$recoveryCode -eq 0", source)

    def test_dependency_recovery_has_explicit_disable_switch_and_no_force_sync_authority(self) -> None:
        source = self.source
        self.assertIn("[switch]$SkipComfyUIDependencyRepair", source)
        self.assertIn("$SkipComfyUIDependencyRepair", source)
        self.assertNotIn("EVAVO_ALLOW_FORCED_DEPENDENCY_REPAIR", source)
        self.assertNotIn("--force-sync", source)
        self.assertNotIn("force_sync", source)

    def test_real_generation_proof_precedes_all_agent_configuration_writes(self) -> None:
        source = self.source
        bootstrap = source.index("bootstrap --skip-pull --skip-verify")
        smoke = source.index('real-generation-smoke.py") --json')
        claude = source.index("Installing/updating Claude Desktop stdio MCP configuration")
        http = source.index("Installing/updating per-user private HTTP MCP autostart")
        final_doctor = source.index("& $python @finalDoctorArgs")
        self.assertLess(bootstrap, smoke)
        self.assertLess(smoke, claude)
        self.assertLess(smoke, http)
        self.assertLess(claude, http)
        self.assertLess(http, final_doctor)
        self.assertIn("Agent configuration was not changed", source)

    def test_final_doctor_does_not_reprovision_or_dependency_repair_late_in_setup(self) -> None:
        source = self.source
        final_start = source.index("$finalDoctorArgs = @(")
        final_end = source.index("& $python @finalDoctorArgs", final_start)
        final_block = source[final_start:final_end]
        self.assertIn('"--repair"', final_block)
        self.assertNotIn('"--provision"', final_block)
        late = source[final_start:]
        self.assertNotIn('recover-comfyui.py") --json', late)
        self.assertNotIn('real-generation-smoke.py") --json', late)

    def test_real_generation_smoke_is_required_before_final_status_and_setup_success(self) -> None:
        source = self.source
        smoke = source.index('real-generation-smoke.py") --json')
        final_status = source.index('evavo.py") status', smoke)
        completed = source.index("EVAVO workstation setup completed.")
        self.assertLess(smoke, final_status)
        self.assertLess(final_status, completed)
        self.assertIn("Real native generation smoke proof failed", source)
        self.assertIn("Real native generation smoke proof: passed before agent config writes", source)

    def test_real_generation_smoke_command_is_repository_owned_and_not_skippable_by_default(self) -> None:
        source = self.source
        self.assertTrue((ROOT / "real-generation-smoke.py").is_file())
        self.assertNotIn("SkipRealGenerationSmoke", source)
        self.assertEqual(source.count('real-generation-smoke.py") --json'), 1)

    def test_bootstrap_itself_is_strict_native(self) -> None:
        controller = (ROOT / "evavo.py").read_text(encoding="utf-8")
        self.assertIn('[sys.executable, controller, "start", "--endpoint", endpoint, "--no-mock"]', controller)


if __name__ == "__main__":
    unittest.main(verbosity=2)
