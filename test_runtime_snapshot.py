"""Offline tests for runtime/model attestation helpers."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def _load_module():
    path = ROOT / "runtime-snapshot.py"
    spec = importlib.util.spec_from_file_location("evavo_runtime_snapshot", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RuntimeSnapshotTests(unittest.TestCase):
    def test_manifest_recipe_resolves_checkpoint_and_unique_loras(self):
        module = _load_module()
        manifest = {
            "checkpoint": None,
            "results": [
                {
                    "status": "completed",
                    "checkpoint": "sd_xl_base_1.0.safetensors",
                    "lora": {"name": "style.safetensors", "model_strength": 0.7, "clip_strength": 0.7},
                },
                {
                    "status": "completed",
                    "checkpoint": "sd_xl_base_1.0.safetensors",
                    "lora": {"name": "style.safetensors", "model_strength": 0.9, "clip_strength": 0.9},
                },
            ],
        }
        recipe = module._manifest_recipe(manifest)
        self.assertEqual(recipe["checkpoint"], "sd_xl_base_1.0.safetensors")
        self.assertEqual(len(recipe["loras"]), 1)
        self.assertEqual(recipe["loras"][0]["name"], "style.safetensors")

    def test_named_model_locator_handles_direct_and_nested_models(self):
        module = _load_module()
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            nested = root / "vendor" / "models"
            nested.mkdir(parents=True)
            model = nested / "example.safetensors"
            model.write_bytes(b"model")
            self.assertEqual(module._locate_named_model("example.safetensors", [root]), model.resolve())

    def test_model_sha256_cache_is_bound_to_size_and_mtime(self):
        module = _load_module()
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            model = root / "model.safetensors"
            cache = root / "hash-cache.json"
            model.write_bytes(b"first-model-bytes")
            expected = hashlib.sha256(b"first-model-bytes").hexdigest()
            first = module._sha256_cached(model, cache)
            second = module._sha256_cached(model, cache)
            self.assertEqual(first["sha256"], expected)
            self.assertFalse(first["hash_cache_hit"])
            self.assertTrue(second["hash_cache_hit"])

            model.write_bytes(b"replacement-model-bytes-with-different-size")
            third = module._sha256_cached(model, cache)
            self.assertFalse(third["hash_cache_hit"])
            self.assertNotEqual(third["sha256"], expected)

    def test_loopback_contract_rejects_remote_or_credentialed_endpoint(self):
        module = _load_module()
        self.assertTrue(module._loopback_http("http://127.0.0.1:8188"))
        self.assertTrue(module._loopback_http("http://localhost:8189"))
        self.assertFalse(module._loopback_http("https://127.0.0.1:8188"))
        self.assertFalse(module._loopback_http("http://example.com:8188"))
        self.assertFalse(module._loopback_http("http://user:pass@127.0.0.1:8188"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
