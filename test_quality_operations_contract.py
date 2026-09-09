"""Contract tests for the quality-first production control surface."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent

QUALITY_PYTHON = (
    "quality-benchmark.py",
    "quality-report.py",
    "lora-sweep.py",
    "kokoro-quality-test.py",
    "kokoro-provider.py",
)

QUALITY_POWERSHELL = (
    "RUN-PRODUCTION-QUALITY.ps1",
    "RUN-HERO-QUALITY.ps1",
    "RUN-LORA-SWEEP.ps1",
    "RUN-FULL-QUALITY-RELEASE.ps1",
    "START-EVAVO-QUALITY-STACK.ps1",
    "SETUP-COMFYUI-NEXT.ps1",
)


def _load_wrapper_module():
    path = ROOT / "evavo-wrapper.py"
    spec = importlib.util.spec_from_file_location("evavo_quality_wrapper_contract", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeComfyUIBackend:
    last_kwargs = None

    def __init__(self, endpoint):
        self.endpoint = endpoint

    def queue_image(self, prompt, **kwargs):
        type(self).last_kwargs = {"prompt": prompt, **kwargs}
        return {
            "status": "queued",
            "task_id": "fake-prompt-id",
            "checkpoint": "sd_xl_base_1.0.safetensors",
            "quality_profile": kwargs.get("quality_profile"),
        }


class QualityOperationsContractTests(unittest.TestCase):
    def test_quality_entrypoints_exist(self):
        for relative in (*QUALITY_PYTHON, *QUALITY_POWERSHELL, "QUALITY-PRODUCTION.md"):
            with self.subTest(path=relative):
                self.assertTrue((ROOT / relative).is_file(), f"missing quality entrypoint: {relative}")

    def test_quality_python_entrypoints_compile(self):
        for relative in QUALITY_PYTHON:
            path = ROOT / relative
            with self.subTest(path=relative):
                source = path.read_text(encoding="utf-8-sig")
                compile(source, str(path), "exec", dont_inherit=True)

    def test_quality_powershell_entrypoints_parse_when_powershell_is_available(self):
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

        for relative in QUALITY_POWERSHELL:
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
                self.assertEqual(
                    result.returncode,
                    0,
                    f"PowerShell parse failed for {relative}: {result.stderr or result.stdout}",
                )

    def test_wrapper_forwards_hero_lora_and_second_pass_controls(self):
        module = _load_wrapper_module()
        payload = {
            "prompt": "quality wrapper regression",
            "project_name": "quality-contract",
            "quality_profile": "hero",
            "sampler_name": "dpmpp_2m_sde",
            "scheduler": "karras",
            "denoise": 1.0,
            "upscale_factor": 1.5,
            "second_pass_steps": 18,
            "second_pass_cfg_scale": 5.5,
            "second_pass_sampler_name": "dpmpp_2m_sde",
            "second_pass_scheduler": "karras",
            "second_pass_denoise": 0.24,
            "latent_upscale_method": "bislerp",
            "lora_name": "detail-style.safetensors",
            "lora_model_strength": 0.7,
            "lora_clip_strength": 0.6,
        }
        FakeComfyUIBackend.last_kwargs = None
        with patch.object(
            module,
            "detect_backend",
            return_value={"kind": "native-comfyui", "mode": "native-comfyui", "endpoint": "http://127.0.0.1:8188", "health": {}},
        ), patch.object(module, "ComfyUIBackend", FakeComfyUIBackend):
            result = module.generate_image("http://127.0.0.1:8188", payload)

        self.assertTrue(result["ok"])
        forwarded = FakeComfyUIBackend.last_kwargs
        self.assertIsNotNone(forwarded)
        for key, value in payload.items():
            if key in {"prompt", "project_name"}:
                continue
            self.assertEqual(forwarded[key], value, f"wrapper did not preserve {key}")
        self.assertEqual(forwarded["prompt"], payload["prompt"])
        self.assertEqual(forwarded["project_name"], payload["project_name"])

    def test_hero_runner_builds_review_package(self):
        source = (ROOT / "RUN-HERO-QUALITY.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("quality,hero,detail,euler_reference,legacy_768_reference", source)
        self.assertIn("1337,424242", source)
        self.assertIn("test_quality_profiles.py", source)
        self.assertIn("quality-benchmark.py", source)
        self.assertIn("quality-report.py", source)
        self.assertIn("human_review.csv", source)

    def test_lora_runner_keeps_base_and_fixed_strengths(self):
        source = (ROOT / "RUN-LORA-SWEEP.ps1").read_text(encoding="utf-8-sig")
        self.assertIn('"0,0.5,0.7,0.9"', source)
        self.assertIn("lora-sweep.py", source)
        self.assertIn("quality-report.py", source)
        self.assertIn("human_review.csv", source)
        self.assertIn("test_quality_profiles.py", source)

    def test_full_release_runs_system_gate_before_expensive_hero_review(self):
        source = (ROOT / "RUN-FULL-QUALITY-RELEASE.ps1").read_text(encoding="utf-8-sig")
        production_index = source.index("RUN-PRODUCTION-QUALITY.ps1")
        hero_index = source.index("RUN-HERO-QUALITY.ps1")
        self.assertLess(production_index, hero_index)
        self.assertIn('"-Mode", "full"', source)
        self.assertIn("Require3DExecution", source)
        self.assertIn("human_review.csv", source)

    def test_3d_startup_is_opt_in_and_token_gated(self):
        source = (ROOT / "START-EVAVO-QUALITY-STACK.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("[switch]$Start3DWorker", source)
        self.assertIn("EVAVO_3D_AGENT_EXECUTION_TOKEN", source)
        self.assertIn("token-gated-candidate-production-only", source)
        self.assertIn("automaticApproval", source)
        self.assertIn("gitMutation", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
