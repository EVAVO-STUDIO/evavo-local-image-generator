#!/usr/bin/env python3
"""Static contract tests for mandatory real-render workstation readiness proof."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "EVAVO-CAPABILITIES.json"
SMOKE = ROOT / "real-generation-smoke.py"
UPDATER = ROOT / "UPDATE-AND-VERIFY-EVAVO.ps1"


class RealGenerationContractTests(unittest.TestCase):
    def test_manifest_requires_real_generation_proof_for_windows_setup(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        automation = manifest["automation"]
        self.assertTrue(automation["real_generation_smoke_required_by_windows_setup"])
        self.assertTrue(automation["simulator_tests_do_not_satisfy_production_readiness"])
        self.assertEqual(manifest["interfaces"]["cli"]["real_generation_smoke"], "python real-generation-smoke.py --json")
        self.assertFalse(manifest["production_contract"]["mock_is_renderer"])

    def test_smoke_proof_requires_native_health_and_validated_download(self) -> None:
        source = SMOKE.read_text(encoding="utf-8")
        self.assertIn("native_health(endpoint)", source)
        self.assertIn("backend.queue_image", source)
        self.assertIn("backend.wait_and_download", source)
        self.assertIn('"status": "completed"', source)
        self.assertIn("signature-validated", source)
        self.assertNotIn("mock-comfyui-server.py", source)

    def test_updater_requires_exactly_one_real_smoke_after_final_doctor(self) -> None:
        source = UPDATER.read_text(encoding="utf-8")
        final_doctor = source.index("& $python @finalDoctorArgs")
        smoke = source.index('real-generation-smoke.py") --json')
        final_status = source.index('evavo.py") status', smoke)
        completed = source.index("EVAVO workstation setup completed.")
        self.assertEqual(source.count('real-generation-smoke.py") --json'), 1)
        self.assertLess(final_doctor, smoke)
        self.assertLess(smoke, final_status)
        self.assertLess(final_status, completed)
        self.assertIn("Setup will not report success until the active workflow actually renders a validated image", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
