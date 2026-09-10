"""Cross-surface contract checks for explicit image VAE selection."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def _load_script(filename: str, module_name: str):
    path = ROOT / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class VaeSurfaceContractTests(unittest.TestCase):
    def test_versioned_batch_schema_exposes_vae_name(self):
        schema = json.loads((ROOT / "config" / "batch-plan-v1.schema.json").read_text(encoding="utf-8"))
        options = schema["$defs"]["options"]["properties"]
        self.assertIn("vae_name", options)
        self.assertEqual(options["vae_name"]["type"], "string")
        self.assertEqual(options["vae_name"]["minLength"], 1)

    def test_regular_batch_generation_options_forward_vae(self):
        module = _load_script("generate-batch.py", "evavo_batch_vae_contract")
        args = Namespace(
            negative_prompt="",
            quality_profile="quality",
            width=None,
            height=None,
            steps=None,
            cfg_scale=None,
            sampler=None,
            scheduler=None,
            denoise=None,
            upscale_factor=None,
            second_pass_steps=None,
            second_pass_cfg=None,
            second_pass_sampler=None,
            second_pass_scheduler=None,
            second_pass_denoise=None,
            latent_upscale_method=None,
            lora=None,
            lora_model_strength=None,
            lora_clip_strength=None,
            vae="sdxl-vae-fp16-fix.safetensors",
            checkpoint=None,
        )
        options = module._generation_options(args)
        self.assertEqual(options["vae_name"], "sdxl-vae-fp16-fix.safetensors")
        self.assertIn("vae", module.RECEIPT_FIELDS)

    def test_regular_batch_rejects_automatic_vae_with_custom_workflow(self):
        module = _load_script("generate-batch.py", "evavo_batch_vae_custom_contract")
        args = Namespace(
            quality_profile="quality",
            width=None,
            height=None,
            steps=None,
            cfg_scale=None,
            sampler=None,
            scheduler=None,
            denoise=None,
            upscale_factor=None,
            second_pass_steps=None,
            second_pass_cfg=None,
            second_pass_sampler=None,
            second_pass_scheduler=None,
            second_pass_denoise=None,
            latent_upscale_method=None,
            workflow="workflow.json",
            lora=None,
            lora_model_strength=None,
            lora_clip_strength=None,
            vae="sdxl-vae-fp16-fix.safetensors",
        )
        with self.assertRaisesRegex(ValueError, "automatic VAE insertion"):
            module._validate_quality_options(args)

    def test_versioned_batch_plan_forwards_explicit_vae_in_frozen_mode(self):
        module = _load_script("batch-plan.py", "evavo_plan_vae_contract")
        payload = {
            "schema_version": 1,
            "project": "vae-plan-contract",
            "defaults": {
                "quality_profile": "quality",
                "vae_name": "sdxl-vae-fp16-fix.safetensors",
                "seed": 1337,
            },
            "items": [
                {
                    "id": "one",
                    "prompt": "Minimal black metal speaker on a matte surface, three-quarter front view, diffused studio light, accurate geometry",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as value:
            plan = Path(value) / "plan.json"
            plan.write_text("{}", encoding="utf-8")
            resolved = module.validate_plan(payload, plan_path=plan)
        self.assertEqual(resolved["environment_mode"], "frozen")
        self.assertEqual(resolved["items"][0]["generation_options"]["vae_name"], "sdxl-vae-fp16-fix.safetensors")
        self.assertIn("VAE", resolved["environment_policy"])

    def test_versioned_batch_plan_rejects_vae_injection_into_custom_workflow(self):
        source = (ROOT / "batch-plan.py").read_text(encoding="utf-8-sig")
        self.assertIn("custom workflows cannot use automatic VAE insertion", source)
        self.assertIn('vae_name=""', source)

    def test_gateway_forwards_and_reports_vae(self):
        source = (ROOT / "EVAVO-GATEWAY.py").read_text(encoding="utf-8-sig")
        self.assertIn('"vae_name"', source)
        self.assertIn('"vae": queued.get("vae")', source)
        self.assertIn('"vae_override": True', source)
        self.assertIn('"frozen_recipe": True', source)

    def test_wrapper_forwards_vae(self):
        source = (ROOT / "evavo-wrapper.py").read_text(encoding="utf-8-sig")
        self.assertIn('vae_name=payload.get("vae_name")', source)
        self.assertIn("use_environment=use_environment", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
