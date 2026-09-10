"""Contract tests for quality controls exposed by EVAVO-GATEWAY.py."""

from __future__ import annotations

import asyncio
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent


def _load_gateway(temp_root: Path):
    path = ROOT / "EVAVO-GATEWAY.py"
    env = {
        "EVAVO_GATEWAY_STATE_DIR": str(temp_root / "state"),
        "EVAVO_GATEWAY_TASK_FILE": str(temp_root / "state" / "tasks.json"),
        "EVAVO_GATEWAY_RESULT_DIR": str(temp_root / "results"),
        "COMFYUI_ENDPOINT": "http://127.0.0.1:8188",
        "EVAVO_COMFYUI_ENDPOINT": "http://127.0.0.1:8188",
    }
    spec = importlib.util.spec_from_file_location("evavo_gateway_quality_contract", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(os.environ, env, clear=False):
        spec.loader.exec_module(module)
    return module


class GatewayQualityContractTests(unittest.TestCase):
    def test_generation_request_preserves_additive_quality_fields(self):
        with tempfile.TemporaryDirectory() as value:
            module = _load_gateway(Path(value))
            request = module.GenerationRequest(
                prompt="gateway quality regression",
                quality_profile="hero",
                lora_name="detail-style.safetensors",
                lora_model_strength=0.7,
                lora_clip_strength=0.6,
                vae_name="sdxl-vae-fp16-fix.safetensors",
                use_environment=False,
            )
            payload = request.model_dump()
            self.assertEqual(payload["quality_profile"], "hero")
            self.assertEqual(payload["lora_name"], "detail-style.safetensors")
            self.assertEqual(payload["lora_model_strength"], 0.7)
            self.assertEqual(payload["lora_clip_strength"], 0.6)
            self.assertEqual(payload["vae_name"], "sdxl-vae-fp16-fix.safetensors")
            self.assertIs(payload["use_environment"], False)

    def test_image_queue_kwargs_forwards_complete_hero_lora_vae_recipe(self):
        with tempfile.TemporaryDirectory() as value:
            module = _load_gateway(Path(value))
            request = {
                "project_name": "gateway-contract",
                "negative_prompt": "artifacts",
                "width": 1024,
                "height": 1024,
                "steps": 36,
                "cfg_scale": 6.5,
                "seed": 1337,
                "checkpoint": "sd_xl_base_1.0.safetensors",
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
                "vae_name": "sdxl-vae-fp16-fix.safetensors",
                "use_environment": False,
            }
            kwargs = module._image_queue_kwargs(request, None)
            for key, expected in request.items():
                self.assertEqual(kwargs[key], expected, f"gateway dropped {key}")
            self.assertIsNone(kwargs["workflow_path"])

    def test_image_receipt_fields_retains_reproducibility_and_quality_metadata(self):
        with tempfile.TemporaryDirectory() as value:
            module = _load_gateway(Path(value))
            queued = {
                "checkpoint": "sd_xl_base_1.0.safetensors",
                "seed": 1337,
                "workflow_sha256": "a" * 64,
                "workflow_node_count": 11,
                "quality_profile": "hero",
                "quality": {"name": "hero", "output_width": 1536, "output_height": 1536},
                "quality_applied": True,
                "render_passes": 2,
                "output_width": 1536,
                "output_height": 1536,
                "lora": {"name": "detail-style.safetensors", "model_strength": 0.7, "clip_strength": 0.6},
                "vae": {"name": "sdxl-vae-fp16-fix.safetensors"},
                "use_environment": False,
            }
            receipt = module._image_receipt_fields(queued)
            self.assertEqual(receipt, queued)

    def test_public_task_exposes_quality_receipt_but_hides_internal_request_and_paths(self):
        with tempfile.TemporaryDirectory() as value:
            module = _load_gateway(Path(value))
            task = {
                "task_id": "img_1",
                "status": "completed",
                "request": {"prompt": "secret internal copy"},
                "result_paths": ["C:/private/result.png"],
                "backend_task_id": "native-id",
                "seed": 1337,
                "workflow_sha256": "b" * 64,
                "quality_profile": "hero",
                "render_passes": 2,
                "output_width": 1536,
                "output_height": 1536,
                "vae": {"name": "sdxl-vae-fp16-fix.safetensors"},
                "use_environment": False,
            }
            public = module._public_task(task)
            self.assertNotIn("request", public)
            self.assertNotIn("result_paths", public)
            self.assertNotIn("backend_task_id", public)
            self.assertEqual(public["seed"], 1337)
            self.assertEqual(public["quality_profile"], "hero")
            self.assertEqual(public["vae"]["name"], "sdxl-vae-fp16-fix.safetensors")
            self.assertIs(public["use_environment"], False)
            self.assertTrue(public["result_ready"])

    def test_task_store_accepts_additive_quality_metadata_without_schema_migration(self):
        with tempfile.TemporaryDirectory() as value:
            module = _load_gateway(Path(value))
            store = module.TaskStore(Path(value) / "standalone-tasks.json")

            async def exercise():
                created = await store.create(
                    "img",
                    {
                        "type": "image",
                        "status": "queued",
                        "progress": 0,
                        "prompt": "store quality metadata",
                    },
                )
                task_id = created["task_id"]
                updated = await store.update(
                    task_id,
                    seed=1337,
                    workflow_sha256="c" * 64,
                    quality_profile="hero",
                    render_passes=2,
                    output_width=1536,
                    output_height=1536,
                    lora={"name": "detail-style.safetensors"},
                    vae={"name": "sdxl-vae-fp16-fix.safetensors"},
                    use_environment=False,
                )
                loaded = await store.get(task_id)
                return updated, loaded

            updated, loaded = asyncio.run(exercise())
            self.assertEqual(updated["quality_profile"], "hero")
            self.assertEqual(loaded["workflow_sha256"], "c" * 64)
            self.assertEqual(loaded["lora"]["name"], "detail-style.safetensors")
            self.assertEqual(loaded["vae"]["name"], "sdxl-vae-fp16-fix.safetensors")
            self.assertIs(loaded["use_environment"], False)

    def test_gateway_version_and_capabilities_advertise_additive_quality_surface(self):
        source = (ROOT / "EVAVO-GATEWAY.py").read_text(encoding="utf-8-sig")
        self.assertIn('version="2.7.0"', source)
        self.assertIn('"quality_profiles": profile_names()', source)
        self.assertIn('"per_request_quality": True', source)
        self.assertIn('"frozen_recipe": True', source)
        self.assertIn('"hero_two_pass": True', source)
        self.assertIn('"lora": True', source)
        self.assertIn('"vae_override": True', source)
        self.assertIn('"workflow_sha256"', source)
        self.assertIn('"vae"', source)
        self.assertIn('"use_environment"', source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
