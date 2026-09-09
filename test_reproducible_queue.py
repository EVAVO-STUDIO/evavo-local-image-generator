"""Fast regressions for reproducible native ComfyUI queue receipts."""

from __future__ import annotations

import unittest

from evavo_local_image_generator.backends import QualityComfyUIBackend


class ReceiptBackend(QualityComfyUIBackend):
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
            return ["detail-style.safetensors"]
        return []

    def preflight_workflow(self, workflow):
        return {"ok": True, "node_count": len(workflow)}

    def _request(self, path, *, method="GET", payload=None, timeout=10.0):
        if path == "/prompt" and method == "POST":
            return {"prompt_id": "receipt-test-prompt"}
        raise AssertionError(f"unexpected request {method} {path}")


class ReproducibleQueueTests(unittest.TestCase):
    def test_unseeded_queue_returns_actual_random_seed_and_workflow_fingerprint(self):
        backend = ReceiptBackend("http://127.0.0.1:8188")
        receipt = backend.queue_image("reproducibility test")
        self.assertIsInstance(receipt["seed"], int)
        self.assertGreaterEqual(receipt["seed"], 0)
        self.assertLess(receipt["seed"], 2**63)
        self.assertEqual(len(receipt["workflow_sha256"]), 64)
        self.assertEqual(receipt["workflow_node_count"], 7)
        self.assertEqual(receipt["checkpoint"], "sd_xl_base_1.0.safetensors")

    def test_same_recipe_and_seed_has_same_workflow_fingerprint(self):
        backend = ReceiptBackend("http://127.0.0.1:8188")
        first = backend.queue_image("same recipe", seed=1337, project_name="same")
        second = backend.queue_image("same recipe", seed=1337, project_name="same")
        self.assertEqual(first["seed"], 1337)
        self.assertEqual(second["seed"], 1337)
        self.assertEqual(first["workflow_sha256"], second["workflow_sha256"])

    def test_seed_change_changes_workflow_fingerprint(self):
        backend = ReceiptBackend("http://127.0.0.1:8188")
        first = backend.queue_image("same recipe", seed=1337, project_name="same")
        second = backend.queue_image("same recipe", seed=424242, project_name="same")
        self.assertNotEqual(first["workflow_sha256"], second["workflow_sha256"])

    def test_lora_and_hero_receipt_records_full_recipe_shape(self):
        backend = ReceiptBackend("http://127.0.0.1:8188")
        receipt = backend.queue_image(
            "hero LoRA recipe",
            seed=1337,
            quality_profile="hero",
            lora_name="detail-style.safetensors",
            lora_model_strength=0.7,
            lora_clip_strength=0.6,
        )
        self.assertEqual(receipt["seed"], 1337)
        self.assertEqual(receipt["render_passes"], 2)
        self.assertEqual((receipt["output_width"], receipt["output_height"]), (1536, 1536))
        self.assertEqual(receipt["workflow_node_count"], 10)
        self.assertEqual(receipt["lora"]["name"], "detail-style.safetensors")
        self.assertEqual(receipt["lora"]["model_strength"], 0.7)
        self.assertEqual(receipt["lora"]["clip_strength"], 0.6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
