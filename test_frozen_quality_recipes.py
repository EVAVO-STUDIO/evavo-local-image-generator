"""Regression tests for environment-frozen quality recipes."""

from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evavo_local_image_generator.backends import QualityComfyUIBackend
from evavo_local_image_generator.quality_profiles import resolve_quality_settings


ROOT = Path(__file__).resolve().parent


class FrozenStubBackend(QualityComfyUIBackend):
    def checkpoints(self):
        return ["sd_xl_base_1.0.safetensors"]

    def choose_checkpoint(self, requested=None, *, allow_repair=True):
        return requested or "sd_xl_base_1.0.safetensors"

    def node_input_choices(self, node_class, input_name):
        if node_class == "KSampler" and input_name == "sampler_name":
            return ["euler", "dpmpp_2m", "dpmpp_2m_sde", "dpmpp_3m_sde"]
        if node_class == "KSampler" and input_name == "scheduler":
            return ["normal", "karras", "simple"]
        if node_class == "LatentUpscale" and input_name == "upscale_method":
            return ["nearest-exact", "bilinear", "area", "bicubic", "bislerp"]
        if node_class == "LoraLoader" and input_name == "lora_name":
            return ["ambient.safetensors", "planned.safetensors"]
        return []


def _load_batch_plan_module():
    path = ROOT / "batch-plan.py"
    spec = importlib.util.spec_from_file_location("evavo_batch_plan_frozen_test", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FrozenQualityRecipeTests(unittest.TestCase):
    def test_resolver_can_ignore_hostile_ambient_overrides(self):
        hostile = {
            "EVAVO_IMAGE_QUALITY_PROFILE": "legacy_768_reference",
            "EVAVO_IMAGE_WIDTH": "640",
            "EVAVO_IMAGE_HEIGHT": "640",
            "EVAVO_IMAGE_STEPS": "99",
            "EVAVO_IMAGE_CFG": "19",
            "EVAVO_IMAGE_SAMPLER": "euler",
            "EVAVO_IMAGE_SCHEDULER": "normal",
            "EVAVO_IMAGE_UPSCALE_FACTOR": "2",
            "EVAVO_IMAGE_SECOND_STEPS": "50",
            "EVAVO_IMAGE_SECOND_DENOISE": "0.8",
        }
        with patch.dict(os.environ, hostile, clear=False):
            settings = resolve_quality_settings(quality_profile="quality", use_environment=False)
        self.assertEqual(settings.name, "quality")
        self.assertEqual((settings.width, settings.height), (1024, 1024))
        self.assertEqual(settings.steps, 36)
        self.assertEqual(settings.cfg_scale, 6.5)
        self.assertEqual(settings.sampler_name, "dpmpp_2m_sde")
        self.assertEqual(settings.scheduler, "karras")
        self.assertFalse(settings.second_pass_enabled)

    def test_frozen_backend_does_not_inherit_ambient_lora(self):
        backend = FrozenStubBackend("http://127.0.0.1:8188")
        hostile = {
            "EVAVO_IMAGE_STEPS": "99",
            "EVAVO_IMAGE_CFG": "19",
            "EVAVO_IMAGE_LORA": "ambient.safetensors",
            "EVAVO_IMAGE_LORA_MODEL_STRENGTH": "1.8",
        }
        with patch.dict(os.environ, hostile, clear=False):
            workflow = backend.build_txt2img_workflow(
                "frozen environment regression",
                seed=1337,
                quality_profile="quality",
                use_environment=False,
            )
        self.assertEqual(workflow["5"]["inputs"]["steps"], 36)
        self.assertEqual(workflow["5"]["inputs"]["cfg"], 6.5)
        self.assertNotIn("10", workflow)

    def test_frozen_backend_fails_closed_on_ambient_workflow_injection(self):
        backend = FrozenStubBackend("http://127.0.0.1:8188")
        with patch.dict(os.environ, {"EVAVO_COMFYUI_WORKFLOW": "ambient-workflow.json"}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "COMFYUI_FROZEN_RECIPE_AMBIENT_WORKFLOW"):
                backend.build_txt2img_workflow(
                    "ambient workflow regression",
                    seed=1337,
                    quality_profile="quality",
                    use_environment=False,
                )

    def test_versioned_batch_plan_resolves_quality_without_ambient_overrides(self):
        module = _load_batch_plan_module()
        hostile = {
            "EVAVO_IMAGE_QUALITY_PROFILE": "legacy_768_reference",
            "EVAVO_IMAGE_STEPS": "88",
            "EVAVO_IMAGE_CFG": "18",
            "EVAVO_IMAGE_LORA": "ambient.safetensors",
        }
        payload = {
            "schema_version": 1,
            "project": "frozen-plan-test",
            "defaults": {"quality_profile": "hero", "seed": 1337},
            "items": [
                {
                    "id": "hero-one",
                    "prompt": "Minimal black metal speaker on a matte desk, three-quarter view, soft studio light, accurate geometry, natural contact shadow",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as value, patch.dict(os.environ, hostile, clear=False):
            plan_path = Path(value) / "plan.json"
            plan_path.write_text("{}", encoding="utf-8")
            resolved = module.validate_plan(payload, plan_path=plan_path)
        item = resolved["items"][0]
        self.assertEqual(resolved["environment_mode"], "frozen")
        self.assertEqual(item["resolved_quality"]["name"], "hero")
        self.assertEqual(item["resolved_quality"]["steps"], 36)
        self.assertEqual(item["resolved_quality"]["cfg_scale"], 6.5)
        self.assertEqual(item["resolved_quality"]["output_width"], 1536)
        self.assertNotIn("lora_name", item["generation_options"])

    def test_controlled_scripts_explicitly_request_frozen_environment(self):
        benchmark = (ROOT / "quality-benchmark.py").read_text(encoding="utf-8-sig")
        lora = (ROOT / "lora-sweep.py").read_text(encoding="utf-8-sig")
        plan = (ROOT / "batch-plan.py").read_text(encoding="utf-8-sig")
        self.assertIn("use_environment=False", benchmark)
        self.assertIn('"environment_mode": "frozen"', benchmark)
        self.assertIn('"use_environment": False', lora)
        self.assertIn("use_environment=False", plan)
        self.assertIn('options["use_environment"] = False', plan)


if __name__ == "__main__":
    unittest.main(verbosity=2)
