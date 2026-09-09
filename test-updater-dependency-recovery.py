#!/usr/bin/env python3
"""Critical contract for canonical updater dependency self-recovery."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RECOVERY = ROOT / "recover-comfyui.py"
UPDATER = ROOT / "UPDATE-AND-VERIFY-EVAVO.ps1"
REPAIR = ROOT / "evavo_local_image_generator" / "comfyui_repair.py"


class UpdaterDependencyRecoveryTests(unittest.TestCase):
    def test_recovery_command_is_present_and_python_valid(self) -> None:
        self.assertTrue(RECOVERY.is_file())
        ast.parse(RECOVERY.read_text(encoding="utf-8"), filename=str(RECOVERY))

    def test_recovery_command_uses_only_normal_evidence_gated_repair(self) -> None:
        source = RECOVERY.read_text(encoding="utf-8")
        self.assertIn("repair_backend_dependencies", source)
        self.assertIn("force_sync=False", source)
        self.assertIn("verify_only=False", source)
        self.assertNotIn("EVAVO_ALLOW_FORCED_DEPENDENCY_REPAIR", source)
        self.assertNotIn("subprocess", source)
        self.assertNotIn("pip install", source.lower())

    def test_updater_runs_recovery_only_after_failed_strict_doctor(self) -> None:
        source = UPDATER.read_text(encoding="utf-8")
        first_doctor = source.index("& $python @backendDoctorArgs")
        failure_guard = source.index("if ($backendDoctorCode -ne 0 -and -not $SkipComfyUIDependencyRepair)")
        recovery = source.index('recover-comfyui.py") --json')
        second_doctor = source.index("& $python @backendDoctorArgs", first_doctor + 1)
        self.assertLess(first_doctor, failure_guard)
        self.assertLess(failure_guard, recovery)
        self.assertLess(recovery, second_doctor)
        self.assertEqual(source.count('recover-comfyui.py") --json'), 1)

    def test_updater_never_enables_forced_dependency_repair(self) -> None:
        source = UPDATER.read_text(encoding="utf-8")
        self.assertIn("[switch]$SkipComfyUIDependencyRepair", source)
        self.assertNotIn("EVAVO_ALLOW_FORCED_DEPENDENCY_REPAIR", source)
        self.assertNotIn("--force-sync", source)

    def test_repair_bridge_owner_gate_exists(self) -> None:
        source = REPAIR.read_text(encoding="utf-8")
        self.assertIn("EVAVO_ALLOW_FORCED_DEPENDENCY_REPAIR", source)
        self.assertIn("FORCE_SYNC_NOT_AUTHORIZED", source)
        self.assertIn("force_sync and not _env_true", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
