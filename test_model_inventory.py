"""Offline tests for local model inventory and SafeTensors metadata parsing."""

from __future__ import annotations

import importlib.util
import json
import struct
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def _load_module():
    path = ROOT / "model-inventory.py"
    spec = importlib.util.spec_from_file_location("evavo_model_inventory", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_fake_safetensors(path: Path, metadata: dict[str, str]) -> None:
    header = {
        "__metadata__": metadata,
        "model.diffusion_model.input_blocks.0.0.weight": {
            "dtype": "F16",
            "shape": [1],
            "data_offsets": [0, 2],
        },
    }
    raw = json.dumps(header, separators=(",", ":")).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(struct.pack("<Q", len(raw)) + raw + b"\x00\x00")


class ModelInventoryTests(unittest.TestCase):
    def test_reads_bounded_safetensors_metadata_without_loading_tensors(self):
        module = _load_module()
        with tempfile.TemporaryDirectory() as value:
            path = Path(value) / "models" / "checkpoints" / "test-sdxl.safetensors"
            _write_fake_safetensors(
                path,
                {
                    "modelspec.architecture": "stable-diffusion-xl-v1-base",
                    "modelspec.title": "Test SDXL",
                },
            )
            header = module._safetensors_header(path)
            self.assertTrue(header["ok"])
            self.assertEqual(header["tensor_count"], 1)
            self.assertEqual(header["metadata"]["modelspec.title"], "Test SDXL")
            hint = module._architecture_hint(path.name, header)
            self.assertIn("sdxl", hint["hints"])

    def test_scan_classifies_checkpoint_and_lora_directories(self):
        module = _load_module()
        with tempfile.TemporaryDirectory() as value:
            root = Path(value) / "models"
            checkpoint = root / "checkpoints" / "base.safetensors"
            lora = root / "loras" / "style.safetensors"
            _write_fake_safetensors(checkpoint, {"modelspec.architecture": "stable-diffusion-xl-v1-base"})
            _write_fake_safetensors(lora, {"ss_network_module": "networks.lora", "ss_base_model_version": "sdxl_base_v1-0"})
            models, warnings = module._scan_root(root, include_hash=False)
            self.assertEqual(warnings, [])
            by_name = {item["name"]: item for item in models}
            self.assertEqual(by_name["base.safetensors"]["category"], "checkpoint")
            self.assertEqual(by_name["style.safetensors"]["category"], "lora")
            self.assertIn("lora", by_name["style.safetensors"]["architecture"]["hints"])

    def test_exact_duplicate_detection_requires_hashes(self):
        module = _load_module()
        models = [
            {"name": "a.safetensors", "path": "/a", "bytes": 123, "sha256": "abc"},
            {"name": "b.safetensors", "path": "/b", "bytes": 123, "sha256": "abc"},
        ]
        duplicates = module._duplicates(models, include_hash=True)
        self.assertEqual(len(duplicates), 1)
        self.assertEqual(duplicates[0]["certainty"], "exact")

    def test_metadata_hint_is_not_presented_as_compatibility_certification(self):
        module = _load_module()
        hint = module._architecture_hint("hunyuan3d-dit-v2-0.safetensors", None)
        self.assertIn("hunyuan", hint["hints"])
        self.assertIn("hint only", hint["warning"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
