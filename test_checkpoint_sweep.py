"""Offline contract tests for checkpoint quality comparisons."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def _load_module():
    path = ROOT / "checkpoint-sweep.py"
    spec = importlib.util.spec_from_file_location("evavo_checkpoint_sweep", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CheckpointSweepTests(unittest.TestCase):
    def test_exact_and_unique_basename_resolution(self):
        module = _load_module()
        available = [
            "sd_xl_base_1.0.safetensors",
            "realistic/dream-model.safetensors",
        ]
        resolved = module._resolve_checkpoint_names(
            ["sd_xl_base_1.0.safetensors", "dream-model.safetensors"],
            available,
        )
        self.assertEqual(
            [item["checkpoint"] for item in resolved],
            ["sd_xl_base_1.0.safetensors", "realistic/dream-model.safetensors"],
        )

    def test_ambiguous_basename_is_rejected(self):
        module = _load_module()
        available = ["a/model.safetensors", "b/model.safetensors"]
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            module._resolve_checkpoint_names(["model.safetensors"], available)

    def test_missing_checkpoint_is_rejected_before_render(self):
        module = _load_module()
        with self.assertRaisesRegex(ValueError, "not in the active ComfyUI inventory"):
            module._resolve_checkpoint_names(["missing.safetensors"], ["base.safetensors"])

    def test_labels_are_stable_and_collision_safe(self):
        module = _load_module()
        used: set[str] = set()
        first = module._checkpoint_label("folder-a/model.safetensors", used)
        second = module._checkpoint_label("folder-b/model.safetensors", used)
        self.assertEqual(first, "model")
        self.assertNotEqual(first, second)
        self.assertTrue(second.startswith("model-"))

    def test_sweep_is_frozen_and_non_promoting(self):
        source = (ROOT / "checkpoint-sweep.py").read_text(encoding="utf-8-sig")
        self.assertIn("use_environment=False", source)
        self.assertIn('lora_name=""', source)
        self.assertIn("CHECKPOINT_SWEEP_AMBIENT_LORA_LEAK", source)
        self.assertIn("no checkpoint is promoted automatically", source)
        self.assertNotIn("set_default_checkpoint", source)

    def test_sweep_uses_versioned_golden_corpus(self):
        source = (ROOT / "checkpoint-sweep.py").read_text(encoding="utf-8-sig")
        self.assertIn("quality-golden-prompts-v1.json", source)
        self.assertIn("load_prompt_corpus", source)
        self.assertIn("prompt_sha256", source)
        self.assertIn("review_focus", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
