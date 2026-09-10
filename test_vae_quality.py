"""Offline regressions for explicit VAE quality overrides."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from evavo_local_image_generator.backends import QualityComfyUIBackend


class VaeStubBackend(QualityComfyUIBackend):
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
            return ["style.safetensors"]
        if node_class == "VAELoader" and input_name == "vae_name":
            return ["sdxl-vae-fp16-fix.safetensors", "taesdxl"]
        return []


class VaeQualityTests(unittest.TestCase):
    def test_inventory_reports_live_vae_choices(self):
        backend = VaeStubBackend("http://127.0.0.1:8188")
        inventory = backend.sampling_inventory()
        self.assertEqual(inventory["vaes"], ["sdxl-vae-fp16-fix.safetensors", "taesdxl"])

    def test_external_vae_changes_decode_only(self):
        backend = VaeStubBackend("http://127.0.0.1:8188")
        workflow = backend.build_txt2img_workflow(
            "VAE decode regression",
            seed=1337,
            quality_profile="quality",
            vae_name="sdxl-vae-fp16-fix.safetensors",
        )
        self.assertEqual(workflow["11"]["class_type"], "VAELoader")
        self.assertEqual(workflow["11"]["inputs"]["vae_name"], "sdxl-vae-fp16-fix.safetensors")
        self.assertEqual(workflow["6"]["inputs"]["vae"], ["11", 0])
        self.assertEqual(workflow["5"]["inputs"]["model"], ["1", 0])
        self.assertEqual(workflow["2"]["inputs"]["clip"], ["1", 1])
        self.assertEqual(workflow["3"]["inputs"]["clip"], ["1", 1])

    def test_external_vae_works_with_hero_and_lora(self):
        backend = VaeStubBackend("http://127.0.0.1:8188")
        workflow = backend.build_txt2img_workflow(
            "VAE hero LoRA regression",
            seed=1337,
            quality_profile="hero",
            lora_name="style.safetensors",
            vae_name="sdxl-vae-fp16-fix.safetensors",
        )
        self.assertEqual(workflow["9"]["inputs"]["model"], ["10", 0])
        self.assertEqual(workflow["6"]["inputs"]["samples"], ["9", 0])
        self.assertEqual(workflow["6"]["inputs"]["vae"], ["11", 0])
        self.assertEqual(len(workflow), 11)

    def test_missing_vae_is_rejected_against_live_inventory(self):
        backend = VaeStubBackend("http://127.0.0.1:8188")
        with self.assertRaisesRegex(RuntimeError, "COMFYUI_VAE_NOT_FOUND"):
            backend.build_txt2img_workflow("missing VAE", vae_name="missing.safetensors")

    def test_vae_refuses_arbitrary_custom_workflow_topology(self):
        backend = VaeStubBackend("http://127.0.0.1:8188")
        with self.assertRaisesRegex(RuntimeError, "COMFYUI_VAE_CUSTOM_WORKFLOW_UNSUPPORTED"):
            backend.build_txt2img_workflow(
                "custom VAE regression",
                vae_name="sdxl-vae-fp16-fix.safetensors",
                workflow_path="does-not-need-to-exist.json",
            )

    def test_frozen_generation_does_not_inherit_ambient_vae(self):
        backend = VaeStubBackend("http://127.0.0.1:8188")
        with patch.dict(os.environ, {"EVAVO_IMAGE_VAE": "sdxl-vae-fp16-fix.safetensors"}, clear=False):
            workflow = backend.build_txt2img_workflow(
                "frozen VAE regression",
                seed=1337,
                quality_profile="quality",
                use_environment=False,
            )
        self.assertNotIn("11", workflow)
        self.assertEqual(workflow["6"]["inputs"]["vae"], ["1", 2])

    def test_explicit_vae_still_applies_in_frozen_mode(self):
        backend = VaeStubBackend("http://127.0.0.1:8188")
        with patch.dict(os.environ, {"EVAVO_IMAGE_VAE": "taesdxl"}, clear=False):
            workflow = backend.build_txt2img_workflow(
                "explicit frozen VAE regression",
                seed=1337,
                quality_profile="quality",
                vae_name="sdxl-vae-fp16-fix.safetensors",
                use_environment=False,
            )
        self.assertEqual(workflow["11"]["inputs"]["vae_name"], "sdxl-vae-fp16-fix.safetensors")


if __name__ == "__main__":
    unittest.main(verbosity=2)
