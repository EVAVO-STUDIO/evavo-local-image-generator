"""Offline regressions for EVAVO production quality profiles and gateway audio fallback."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from evavo_local_image_generator.backends import ComfyUIBackend, QualityComfyUIBackend
from evavo_local_image_generator.quality_profiles import (
    get_quality_profile,
    recommended_sdxl_dimensions,
    resolve_quality_settings,
)
from test_kokoro_gateway_provider import KokoroGatewayProviderContractTests  # noqa: F401


class StubQualityBackend(QualityComfyUIBackend):
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
        return []


class QualityProfileTests(unittest.TestCase):
    def test_package_exports_quality_backend_as_canonical(self):
        self.assertIs(ComfyUIBackend, QualityComfyUIBackend)

    def test_quality_profile_is_sdxl_native_and_quality_first(self):
        profile = get_quality_profile("quality")
        self.assertEqual((profile.width, profile.height), (1024, 1024))
        self.assertEqual(profile.steps, 36)
        self.assertEqual(profile.cfg_scale, 6.5)
        self.assertEqual(profile.sampler_name, "dpmpp_2m_sde")
        self.assertEqual(profile.scheduler, "karras")
        self.assertFalse(profile.second_pass_enabled)
        self.assertEqual(profile.pass_count, 1)
        self.assertEqual((profile.output_width, profile.output_height), (1024, 1024))

    def test_hero_profile_is_explicit_two_pass_1536_path(self):
        profile = get_quality_profile("hero")
        self.assertEqual((profile.width, profile.height), (1024, 1024))
        self.assertEqual(profile.steps, 36)
        self.assertEqual(profile.cfg_scale, 6.5)
        self.assertEqual(profile.upscale_factor, 1.5)
        self.assertEqual(profile.second_pass_steps, 18)
        self.assertEqual(profile.second_pass_cfg_scale, 5.5)
        self.assertEqual(profile.second_pass_denoise, 0.24)
        self.assertEqual(profile.latent_upscale_method, "bislerp")
        self.assertTrue(profile.second_pass_enabled)
        self.assertEqual(profile.pass_count, 2)
        self.assertEqual((profile.output_width, profile.output_height), (1536, 1536))

    def test_legacy_wrapper_default_pair_is_upgraded(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = resolve_quality_settings(steps=24, cfg_scale=7.0)
        self.assertEqual(settings.name, "quality")
        self.assertEqual(settings.steps, 36)
        self.assertEqual(settings.cfg_scale, 6.5)

    def test_custom_profile_can_preserve_intentional_24_7_request(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = resolve_quality_settings(quality_profile="custom", steps=24, cfg_scale=7.0)
        self.assertEqual(settings.name, "custom")
        self.assertEqual(settings.steps, 24)
        self.assertEqual(settings.cfg_scale, 7.0)
        self.assertFalse(settings.second_pass_enabled)

    def test_builtin_workflow_uses_quality_sampler(self):
        backend = StubQualityBackend("http://127.0.0.1:8188")
        workflow = backend.build_txt2img_workflow("quality regression", seed=1337)
        sampler = workflow["5"]["inputs"]
        latent = workflow["4"]["inputs"]
        self.assertEqual((latent["width"], latent["height"]), (1024, 1024))
        self.assertEqual(sampler["steps"], 36)
        self.assertEqual(sampler["cfg"], 6.5)
        self.assertEqual(sampler["sampler_name"], "dpmpp_2m_sde")
        self.assertEqual(sampler["scheduler"], "karras")
        self.assertNotIn("8", workflow)
        self.assertNotIn("9", workflow)
        self.assertEqual(workflow["6"]["inputs"]["samples"], ["5", 0])

    def test_detail_profile_uses_higher_quality_budget(self):
        backend = StubQualityBackend("http://127.0.0.1:8188")
        workflow = backend.build_txt2img_workflow("detail regression", seed=1337, quality_profile="detail")
        sampler = workflow["5"]["inputs"]
        self.assertEqual(sampler["steps"], 42)
        self.assertEqual(sampler["cfg"], 6.0)
        self.assertEqual(sampler["sampler_name"], "dpmpp_3m_sde")
        self.assertEqual(sampler["scheduler"], "karras")

    def test_hero_workflow_appends_latent_upscale_and_low_denoise_second_sampler(self):
        backend = StubQualityBackend("http://127.0.0.1:8188")
        workflow = backend.build_txt2img_workflow("hero regression", seed=1337, quality_profile="hero")

        first = workflow["5"]["inputs"]
        upscale = workflow["8"]
        second = workflow["9"]["inputs"]

        self.assertEqual(first["seed"], 1337)
        self.assertEqual(first["steps"], 36)
        self.assertEqual(first["cfg"], 6.5)
        self.assertEqual(first["denoise"], 1.0)

        self.assertEqual(upscale["class_type"], "LatentUpscale")
        self.assertEqual(upscale["inputs"]["samples"], ["5", 0])
        self.assertEqual(upscale["inputs"]["upscale_method"], "bislerp")
        self.assertEqual((upscale["inputs"]["width"], upscale["inputs"]["height"]), (1536, 1536))
        self.assertEqual(upscale["inputs"]["crop"], "disabled")

        self.assertEqual(second["seed"], 1337)
        self.assertEqual(second["steps"], 18)
        self.assertEqual(second["cfg"], 5.5)
        self.assertEqual(second["sampler_name"], "dpmpp_2m_sde")
        self.assertEqual(second["scheduler"], "karras")
        self.assertEqual(second["denoise"], 0.24)
        self.assertEqual(second["latent_image"], ["8", 0])
        self.assertEqual(workflow["6"]["inputs"]["samples"], ["9", 0])
        self.assertEqual(workflow["7"]["inputs"]["images"], ["6", 0])

    def test_hero_scales_native_wide_bucket_without_changing_aspect(self):
        settings = resolve_quality_settings(quality_profile="hero", width=1344, height=768)
        self.assertEqual((settings.width, settings.height), (1344, 768))
        self.assertEqual((settings.output_width, settings.output_height), (2016, 1152))

    def test_hero_rejects_output_that_exceeds_safety_ceiling(self):
        with self.assertRaisesRegex(ValueError, "exceeds the 4096px safety limit"):
            resolve_quality_settings(quality_profile="hero", width=4096, height=4096)

    def test_hero_refuses_arbitrary_custom_workflow_topology(self):
        backend = StubQualityBackend("http://127.0.0.1:8188")
        with self.assertRaisesRegex(RuntimeError, "COMFYUI_HERO_CUSTOM_WORKFLOW_UNSUPPORTED"):
            backend.build_txt2img_workflow(
                "hero custom workflow regression",
                seed=1337,
                quality_profile="hero",
                workflow_path="does-not-need-to-exist.json",
            )

    def test_sampler_falls_back_to_available_quality_option(self):
        self.assertEqual(
            StubQualityBackend._choose_available("missing", ["euler", "dpmpp_2m"], StubQualityBackend._SAMPLER_FALLBACKS),
            "dpmpp_2m",
        )

    def test_latent_upscale_method_falls_back_to_available_core_option(self):
        self.assertEqual(
            StubQualityBackend._choose_available(
                "missing",
                ["bilinear", "bicubic"],
                StubQualityBackend._LATENT_UPSCALE_FALLBACKS,
            ),
            "bicubic",
        )

    def test_sdxl_buckets_include_square_and_wide_native_sizes(self):
        buckets = recommended_sdxl_dimensions()
        self.assertEqual(buckets["1:1"], (1024, 1024))
        self.assertEqual(buckets["wide"], (1344, 768))
        self.assertEqual(buckets["portrait_wide"], (768, 1344))


if __name__ == "__main__":
    unittest.main(verbosity=2)
