"""Offline tests for the frozen production batch-plan entrypoint."""

from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent


def _module():
    path = ROOT / "run-batch-plan.py"
    source = path.read_text(encoding="utf-8-sig")
    compile(source, str(path), "exec", dont_inherit=True)
    spec = importlib.util.spec_from_file_location("evavo_run_batch_plan", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load run-batch-plan.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FrozenBatchPlanTests(unittest.TestCase):
    def test_environment_mask_is_temporary_and_complete(self):
        module = _module()
        env = {
            "EVAVO_IMAGE_CFG": "9.5",
            "EVAVO_IMAGE_LORA": "ambient.safetensors",
            "EVAVO_COMFYUI_WORKFLOW": "ambient.json",
        }
        with patch.dict(os.environ, env, clear=False):
            with module._frozen_image_environment() as masked:
                self.assertEqual(set(masked), set(env))
                for key in env:
                    self.assertNotIn(key, os.environ)
            for key, value in env.items():
                self.assertEqual(os.environ.get(key), value)

    def test_freeze_recipes_requires_explicit_checkpoint(self):
        module = _module()
        validated = {
            "items": [
                {"id": "one", "generation_options": {"quality_profile": "quality"}},
                {"id": "two", "generation_options": {"checkpoint": "sd_xl_base_1.0.safetensors"}},
            ]
        }
        with self.assertRaisesRegex(ValueError, "explicit checkpoint"):
            module._freeze_recipes(validated)

    def test_freeze_recipes_injects_environment_policy(self):
        module = _module()
        validated = {
            "items": [
                {
                    "id": "hero",
                    "generation_options": {
                        "checkpoint": "sd_xl_base_1.0.safetensors",
                        "quality_profile": "hero",
                        "seed": 1337,
                    },
                }
            ]
        }
        module._freeze_recipes(validated)
        options = validated["items"][0]["generation_options"]
        self.assertIs(options["use_environment"], False)
        self.assertEqual(options["quality_profile"], "hero")
        self.assertEqual(options["seed"], 1337)

    def test_example_plan_validates_under_polluted_environment(self):
        module = _module()
        engine = module._engine()
        path = ROOT / "examples" / "batch-plan-mixed-quality-v1.json"
        plan_path, _, payload = engine._read_plan(path)
        with patch.dict(
            os.environ,
            {
                "EVAVO_IMAGE_WIDTH": "640",
                "EVAVO_IMAGE_CFG": "12",
                "EVAVO_IMAGE_LORA": "ambient.safetensors",
                "EVAVO_COMFYUI_WORKFLOW": "ambient.json",
            },
            clear=False,
        ):
            with module._frozen_image_environment():
                validated = engine.validate_plan(payload, plan_path=plan_path)
                module._freeze_recipes(validated)
        self.assertEqual(len(validated["items"]), 3)
        self.assertTrue(all(item["generation_options"]["use_environment"] is False for item in validated["items"]))
        self.assertTrue(all(item["generation_options"]["checkpoint"] == "sd_xl_base_1.0.safetensors" for item in validated["items"]))

    def test_output_subdir_escape_is_rejected(self):
        module = _module()
        engine = module._engine()
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            with self.assertRaisesRegex(ValueError, "unsafe output_subdir"):
                engine._confined_output(root.resolve(), "../escape")


if __name__ == "__main__":
    unittest.main(verbosity=2)
