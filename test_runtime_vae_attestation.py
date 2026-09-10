"""Offline tests for VAE runtime/model attestation."""

from __future__ import annotations

import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def _load_module():
    path = ROOT / "runtime-snapshot.py"
    spec = importlib.util.spec_from_file_location("evavo_runtime_vae_attestation", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RuntimeVaeAttestationTests(unittest.TestCase):
    def test_manifest_recipe_collects_unique_external_vaes(self):
        module = _load_module()
        recipe = module._manifest_recipe(
            {
                "checkpoint": "base.safetensors",
                "resolved_vaes": ["vae-a.safetensors", "taesdxl"],
                "results": [
                    {"status": "completed", "vae": {"name": "vae-a.safetensors"}},
                    {"status": "completed", "vae": None},
                ],
            }
        )
        self.assertEqual([item["name"] for item in recipe["vaes"]], ["vae-a.safetensors", "taesdxl"])

    def test_file_backed_vae_is_hashed(self):
        module = _load_module()
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            vae = root / "models" / "vae" / "vae-a.safetensors"
            vae.parent.mkdir(parents=True)
            vae.write_bytes(b"vae-bytes")
            cache = root / "cache.json"
            receipt = module._attest_vae("vae-a.safetensors", root, [], cache)
            self.assertTrue(receipt["complete"])
            self.assertEqual(receipt["kind"], "file")
            self.assertEqual(receipt["sha256"], hashlib.sha256(b"vae-bytes").hexdigest())

    def test_approximate_vae_hashes_encoder_and_decoder_components(self):
        module = _load_module()
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            approx = root / "models" / "vae_approx"
            approx.mkdir(parents=True)
            (approx / "taesdxl_encoder.safetensors").write_bytes(b"enc")
            (approx / "taesdxl_decoder.safetensors").write_bytes(b"dec")
            receipt = module._attest_vae("taesdxl", root, [], root / "cache.json")
            self.assertTrue(receipt["complete"])
            self.assertEqual(receipt["kind"], "approximate")
            self.assertEqual(len(receipt["components"]), 2)
            self.assertEqual(len(receipt["components_sha256"]), 64)

    def test_incomplete_approximate_vae_is_not_attested(self):
        module = _load_module()
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            approx = root / "models" / "vae_approx"
            approx.mkdir(parents=True)
            (approx / "taesdxl_encoder.safetensors").write_bytes(b"enc")
            receipt = module._attest_vae("taesdxl", root, [], root / "cache.json")
            self.assertFalse(receipt["complete"])
            self.assertEqual(receipt["kind"], "unknown")

    def test_pixel_space_is_identified_as_intrinsic_not_fake_model_hash(self):
        module = _load_module()
        with tempfile.TemporaryDirectory() as value:
            receipt = module._attest_vae("pixel_space", Path(value), [], Path(value) / "cache.json")
            self.assertTrue(receipt["complete"])
            self.assertEqual(receipt["kind"], "intrinsic")
            self.assertNotIn("sha256", receipt)


if __name__ == "__main__":
    unittest.main(verbosity=2)
