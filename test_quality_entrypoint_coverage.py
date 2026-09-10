"""Compile and contract-check production batch/release entrypoints."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent

PYTHON_ENTRYPOINTS = (
    "generate-batch.py",
    "batch-plan.py",
    "batch-resume.py",
    "quality-benchmark.py",
    "lora-sweep.py",
    "release-evidence.py",
    "runtime-snapshot.py",
    "studio-runtime-snapshot.py",
    "kokoro-runtime-snapshot.py",
)


class QualityEntrypointCoverageTests(unittest.TestCase):
    def test_python_entrypoints_compile(self):
        for relative in PYTHON_ENTRYPOINTS:
            path = ROOT / relative
            with self.subTest(path=relative):
                self.assertTrue(path.is_file(), f"missing production entrypoint: {relative}")
                compile(path.read_text(encoding="utf-8-sig"), str(path), "exec", dont_inherit=True)

    def test_batch_plan_schema_and_example_are_versioned(self):
        schema_path = ROOT / "config" / "batch-plan-v1.schema.json"
        example_path = ROOT / "examples" / "batch-plan-mixed-quality-v1.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        example = json.loads(example_path.read_text(encoding="utf-8"))
        self.assertEqual(schema.get("$id"), "https://evavo.local/schemas/batch-plan-v1.schema.json")
        self.assertEqual(example.get("schema_version"), 1)
        self.assertGreaterEqual(len(example.get("items", [])), 3)
        profiles = {
            item.get("options", {}).get("quality_profile")
            for item in example["items"]
            if isinstance(item, dict)
        }
        self.assertIn("hero", profiles)

    def test_versioned_batch_plan_is_environment_frozen(self):
        source = (ROOT / "batch-plan.py").read_text(encoding="utf-8-sig")
        self.assertIn("use_environment=False", source)
        self.assertIn('options["use_environment"] = False', source)
        self.assertIn('"environment_mode": "frozen"', source)
        self.assertIn('"resolved_quality": settings.as_dict()', source)
        self.assertIn("COMFYUI", (ROOT / "BATCH-QUALITY.md").read_text(encoding="utf-8-sig"))

    def test_controlled_benchmarks_are_environment_frozen(self):
        benchmark = (ROOT / "quality-benchmark.py").read_text(encoding="utf-8-sig")
        lora = (ROOT / "lora-sweep.py").read_text(encoding="utf-8-sig")
        self.assertIn("use_environment=False", benchmark)
        self.assertIn("QUALITY_AMBIENT_LORA_LEAK", benchmark)
        self.assertIn('"use_environment": False', lora)
        self.assertIn("LORA_SWEEP_AMBIENT_LORA_LEAK", lora)

    def test_batch_resume_remains_non_duplicating_by_default(self):
        source = (ROOT / "batch-resume.py").read_text(encoding="utf-8-sig")
        self.assertIn("force-retry-identified", source)
        self.assertIn("retry-failed", source)
        self.assertIn("retry-pending", source)

    def test_release_bundle_is_tamper_evident(self):
        release = (ROOT / "RUN-FULL-QUALITY-RELEASE.ps1").read_text(encoding="utf-8-sig")
        finalizer = (ROOT / "FINALIZE-FULL-RELEASE.ps1").read_text(encoding="utf-8-sig")
        verifier = (ROOT / "VERIFY-FULL-RELEASE.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("release-evidence.py create", release)
        self.assertIn("release-evidence.py verify", release)
        self.assertIn("release-evidence.py create", finalizer)
        self.assertIn("release-evidence.py verify", verifier)


if __name__ == "__main__":
    unittest.main(verbosity=2)
