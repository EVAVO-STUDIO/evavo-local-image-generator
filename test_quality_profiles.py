"""Offline regression tests for EVAVO production image quality profiles."""

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

    def test_detail_profile_uses_higher_quality_budget(self):
        backend = StubQualityBackend("http://127.0.0.1:8188")
        workflow = backend.build_txt2img_workflow("detail regression", seed=1337, quality_profile="detail")
        sampler = workflow["5"]["inputs"]
        self.assertEqual(sampler["steps"], 42)
        self.assertEqual(sampler["cfg"], 6.0)
        self.assertEqual(sampler["sampler_name"], "dpmpp_3m_sde")
        self.assertEqual(sampler["scheduler"], "karras")

    def test_sampler_falls_back_to_available_quality_option(self):
        self.assertEqual(
            StubQualityBackend._choose_available("missing", ["euler", "dpmpp_2m"], StubQualityBackend._SAMPLER_FALLBACKS),
            "dpmpp_2m",
        )

    def test_sdxl_buckets_include_square_and_wide_native_sizes(self):
        buckets = recommended_sdxl_dimensions()
        self.assertEqual(buckets["1:1"], (1024, 1024))
        self.assertEqual(buckets["wide"], (1344, 768))
        self.assertEqual(buckets["portrait_wide"], (768, 1344))


if __name__ == "__main__":
    unittest.main(verbosity=2)
