"""Offline tests for quality-first batch generation helpers."""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _module():
    path = ROOT / "generate-batch.py"
    source = path.read_text(encoding="utf-8-sig")
    compile(source, str(path), "exec", dont_inherit=True)
    spec = importlib.util.spec_from_file_location("evavo_generate_batch_quality", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load generate-batch.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _args(**overrides):
    values = {
        "negative_prompt": "warped geometry, text, watermark",
        "quality_profile": "hero",
        "width": None,
        "height": None,
        "steps": None,
        "cfg_scale": None,
        "sampler": None,
        "scheduler": None,
        "denoise": None,
        "upscale_factor": None,
        "second_pass_steps": None,
        "second_pass_cfg": None,
        "second_pass_sampler": None,
        "second_pass_scheduler": None,
        "second_pass_denoise": None,
        "latent_upscale_method": None,
        "lora": "detail-style.safetensors",
        "lora_model_strength": 0.7,
        "lora_clip_strength": 0.6,
        "checkpoint": "sd_xl_base_1.0.safetensors",
        "workflow": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class BatchQualityContractTests(unittest.TestCase):
    def test_generation_options_forward_negative_hero_lora_and_checkpoint(self):
        module = _module()
        options = module._generation_options(_args())
        self.assertEqual(options["negative_prompt"], "warped geometry, text, watermark")
        self.assertEqual(options["quality_profile"], "hero")
        self.assertEqual(options["lora_name"], "detail-style.safetensors")
        self.assertEqual(options["lora_model_strength"], 0.7)
        self.assertEqual(options["lora_clip_strength"], 0.6)
        self.assertEqual(options["checkpoint"], "sd_xl_base_1.0.safetensors")

    def test_seed_strategies_are_deterministic(self):
        module = _module()
        self.assertEqual([module._seed_for_index(1337, "same", i) for i in range(3)], [1337, 1337, 1337])
        self.assertEqual([module._seed_for_index(1337, "increment", i) for i in range(3)], [1337, 1338, 1339])
        self.assertIsNone(module._seed_for_index(None, "increment", 0))

    def test_seed_overflow_fails_closed(self):
        module = _module()
        with self.assertRaisesRegex(ValueError, "63-bit"):
            module._seed_for_index((2**63) - 1, "increment", 1)

    def test_custom_workflow_rejects_automatic_hero_and_lora(self):
        module = _module()
        with self.assertRaisesRegex(ValueError, "two-pass"):
            module._validate_quality_options(_args(workflow="workflow.json", lora=None, lora_model_strength=None, lora_clip_strength=None))
        with self.assertRaisesRegex(ValueError, "LoRA"):
            module._validate_quality_options(_args(workflow="workflow.json", quality_profile="quality"))

    def test_batch_manifest_records_results_atomically(self):
        module = _module()
        with tempfile.TemporaryDirectory() as value:
            path = Path(value) / "run.json"
            store = module.BatchRunStore(
                path,
                {
                    "schema_version": 1,
                    "items": [{"index": 0, "status": "pending", "task_id": None, "result": None}],
                },
            )
            result = {
                "status": "completed",
                "task_id": "prompt-123",
                "seed": 1337,
                "quality_profile": "hero",
            }
            asyncio.run(store.record(0, result))
            asyncio.run(store.finish([result]))
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["items"][0]["status"], "completed")
            self.assertEqual(payload["items"][0]["result"]["seed"], 1337)
            self.assertTrue(payload["summary"]["ok"])
            self.assertEqual(payload["summary"]["completed"], 1)

    def test_task_receipt_keeps_prompt_and_generation_fingerprint(self):
        module = _module()
        receipt = module._receipt(
            {
                "seed": 1337,
                "quality_profile": "hero",
                "workflow_sha256": "a" * 64,
                "workflow_node_count": 10,
                "output_width": 1536,
                "output_height": 1536,
                "lora": {"name": "style.safetensors", "model_strength": 0.7},
                "prompt_quality": {"prompt_sha256": "b" * 64, "warning_count": 1},
            }
        )
        self.assertEqual(receipt["seed"], 1337)
        self.assertEqual(receipt["prompt_sha256"], "b" * 64)
        self.assertEqual(receipt["workflow_sha256"], "a" * 64)
        self.assertEqual(receipt["output_width"], 1536)


if __name__ == "__main__":
    unittest.main(verbosity=2)
