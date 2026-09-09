"""Offline regressions for frozen image-quality recipes."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from evavo_local_image_generator.backends.quality_comfyui_backend import QualityComfyUIBackend
from evavo_local_image_generator.quality_profiles import resolve_quality_settings


class FrozenBackend(QualityComfyUIBackend):
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
            return ["ambient.safetensors", "explicit.safetensors"]
        return []


class FrozenQualityEnvironmentTests(unittest.TestCase):
    def test_profile_resolution_can_ignore_ambient_image_overrides(self):
        env = {
            "EVAVO_IMAGE_WIDTH": "768",
            "EVAVO_IMAGE_HEIGHT": "768",
            "EVAVO_IMAGE_STEPS": "11",
            "EVAVO_IMAGE_CFG": "9.5",
            "EVAVO_IMAGE_SAMPLER": "euler",
            "EVAVO_IMAGE_SCHEDULER": "normal",
            "EVAVO_IMAGE_UPSCALE_FACTOR": "1",
            "EVAVO_IMAGE_SECOND_STEPS": "0",
        }
        with patch.dict(os.environ, env, clear=False):
            normal = resolve_quality_settings(quality_profile="hero")
            frozen = resolve_quality_settings(quality_profile="hero", use_environment=False)
        self.assertEqual((normal.width, normal.height), (768, 768))
        self.assertEqual(normal.steps, 11)
        self.assertEqual(normal.cfg_scale, 9.5)
        self.assertEqual(normal.sampler_name, "euler")
        self.assertFalse(normal.second_pass_enabled)
        self.assertEqual((frozen.width, frozen.height), (1024, 1024))
        self.assertEqual(frozen.steps, 36)
        self.assertEqual(frozen.cfg_scale, 6.5)
        self.assertEqual(frozen.sampler_name, "dpmpp_2m_sde")
        self.assertTrue(frozen.second_pass_enabled)
        self.assertEqual((frozen.output_width, frozen.output_height), (1536, 1536))

    def test_frozen_graph_ignores_ambient_lora(self):
        backend = FrozenBackend("http://127.0.0.1:8188")
        with patch.dict(
            os.environ,
            {
                "EVAVO_IMAGE_LORA": "ambient.safetensors",
                "EVAVO_IMAGE_LORA_MODEL_STRENGTH": "1.2",
                "EVAVO_IMAGE_LORA_CLIP_STRENGTH": "1.1",
            },
            clear=False,
        ):
            normal = backend.build_txt2img_workflow("normal", seed=1337, quality_profile="quality")
            frozen = backend.build_txt2img_workflow(
                "frozen",
                seed=1337,
                quality_profile="quality",
                use_environment=False,
            )
        self.assertIn("10", normal)
        self.assertEqual(normal["10"]["inputs"]["lora_name"], "ambient.safetensors")
        self.assertNotIn("10", frozen)

    def test_frozen_graph_allows_explicit_lora(self):
        backend = FrozenBackend("http://127.0.0.1:8188")
        with patch.dict(os.environ, {"EVAVO_IMAGE_LORA": "ambient.safetensors"}, clear=False):
            workflow = backend.build_txt2img_workflow(
                "frozen explicit",
                seed=1337,
                quality_profile="hero",
                lora_name="explicit.safetensors",
                lora_model_strength=0.7,
                lora_clip_strength=0.6,
                use_environment=False,
            )
        self.assertEqual(workflow["10"]["inputs"]["lora_name"], "explicit.safetensors")
        self.assertEqual(workflow["5"]["inputs"]["model"], ["10", 0])
        self.assertEqual(workflow["9"]["inputs"]["model"], ["10", 0])

    def test_frozen_recipe_refuses_ambient_custom_workflow(self):
        backend = FrozenBackend("http://127.0.0.1:8188")
        with patch.dict(os.environ, {"EVAVO_COMFYUI_WORKFLOW": "ambient-workflow.json"}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "COMFYUI_FROZEN_RECIPE_AMBIENT_WORKFLOW"):
                backend.build_txt2img_workflow(
                    "frozen workflow",
                    seed=1337,
                    quality_profile="quality",
                    use_environment=False,
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
