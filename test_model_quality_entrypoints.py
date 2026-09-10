"""Contract coverage for model, VAE and GPU quality operator surfaces."""

from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent

PYTHON_ENTRYPOINTS = (
    "model-inventory.py",
    "checkpoint-sweep.py",
    "vae-sweep.py",
    "gpu-quality-benchmark.py",
)

POWERSHELL_ENTRYPOINTS = (
    "RUN-MODEL-INVENTORY.ps1",
    "RUN-CHECKPOINT-SWEEP.ps1",
    "RUN-VAE-SWEEP.ps1",
    "RUN-GPU-QUALITY-BENCHMARK.ps1",
)


class ModelQualityEntrypointTests(unittest.TestCase):
    def test_python_entrypoints_compile(self):
        for relative in PYTHON_ENTRYPOINTS:
            path = ROOT / relative
            with self.subTest(path=relative):
                self.assertTrue(path.is_file(), f"missing entrypoint: {relative}")
                compile(path.read_text(encoding="utf-8-sig"), str(path), "exec", dont_inherit=True)

    def test_powershell_entrypoints_parse_when_available(self):
        executable = next(
            (
                value
                for name in ("pwsh.exe", "powershell.exe", "pwsh", "powershell")
                if (value := shutil.which(name))
            ),
            None,
        )
        if executable is None:
            self.skipTest("PowerShell is not available in this environment")
        for relative in POWERSHELL_ENTRYPOINTS:
            path = (ROOT / relative).resolve()
            escaped = str(path).replace("'", "''")
            command = (
                "$tokens=$null; $errors=$null; "
                f"[System.Management.Automation.Language.Parser]::ParseFile('{escaped}', [ref]$tokens, [ref]$errors) | Out-Null; "
                "if ($errors.Count -gt 0) { $errors | ForEach-Object { Write-Error $_.Message }; exit 1 }; exit 0"
            )
            with self.subTest(path=relative):
                result = subprocess.run(
                    [executable, "-NoProfile", "-NonInteractive", "-Command", command],
                    cwd=str(ROOT),
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_batch_plan_schema_exposes_explicit_vae_only(self):
        schema = json.loads((ROOT / "config" / "batch-plan-v1.schema.json").read_text(encoding="utf-8"))
        options = schema["$defs"]["options"]["properties"]
        self.assertIn("vae_name", options)
        self.assertNotIn("automatic_vae", options)

    def test_vae_runner_keeps_baked_decoder_as_baseline(self):
        sweep = (ROOT / "vae-sweep.py").read_text(encoding="utf-8-sig")
        runner = (ROOT / "RUN-VAE-SWEEP.ps1").read_text(encoding="utf-8-sig")
        self.assertIn('"checkpoint_vae"', sweep)
        self.assertIn('use_environment=False', sweep)
        self.assertIn('lora_name=""', sweep)
        self.assertIn("quality-report.py", runner)
        self.assertIn("runtime-snapshot.py", runner)
        self.assertIn("human_review.csv", runner)

    def test_model_inventory_does_not_load_model_tensors(self):
        source = (ROOT / "model-inventory.py").read_text(encoding="utf-8-sig")
        self.assertIn("_safetensors_header", source)
        self.assertNotIn("torch.load", source)
        self.assertNotIn("safetensors.torch", source)

    def test_checkpoint_sweep_is_explicit_and_non_promoting(self):
        source = (ROOT / "checkpoint-sweep.py").read_text(encoding="utf-8-sig")
        self.assertIn("--checkpoints", source)
        self.assertIn("use_environment=False", source)
        self.assertIn("no checkpoint is promoted automatically", source)

    def test_gpu_benchmark_never_auto_promotes_quality(self):
        source = (ROOT / "gpu-quality-benchmark.py").read_text(encoding="utf-8-sig")
        self.assertIn("nvidia-smi", source)
        self.assertIn("Throughput and VRAM evidence do not measure visual quality", source)
        self.assertNotIn("set_default_profile", source)

    def test_documentation_preserves_evidence_first_policy(self):
        model_doc = (ROOT / "MODEL-QUALITY.md").read_text(encoding="utf-8-sig")
        vae_doc = (ROOT / "VAE-QUALITY.md").read_text(encoding="utf-8-sig")
        self.assertIn("Architecture hints are not certification", model_doc)
        self.assertIn("checkpoint's baked VAE by default", vae_doc)
        self.assertIn("No VAE sweep or inventory command changes the production default automatically", vae_doc)


if __name__ == "__main__":
    unittest.main(verbosity=2)
