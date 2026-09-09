"""Offline tests for controlled EVAVO performance comparisons."""

from __future__ import annotations

import importlib.util
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _module():
    path = ROOT / "compare-performance.py"
    source = path.read_text(encoding="utf-8-sig")
    compile(source, str(path), "exec", dont_inherit=True)
    spec = importlib.util.spec_from_file_location("evavo_compare_performance", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load compare-performance.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fixture() -> dict:
    return {
        "schema_version": 1,
        "endpoint": "http://127.0.0.1:8188",
        "checkpoint": "sd_xl_base_1.0.safetensors",
        "prompt_id": "product",
        "prompt_sha256": "a" * 64,
        "prompt_corpus": {"sha256": "b" * 64},
        "seed": 1337,
        "repeats": 3,
        "profiles": ["quality", "hero"],
        "gpu": {"uuid": "GPU-fixture", "name": "RTX 4080", "memory_total_mib": 12282.0},
        "profile_summary": {
            "quality": {
                "median_elapsed_s": 10.0,
                "median_seconds_per_megapixel": 9.5,
                "median_images_per_hour": 360.0,
                "peak_memory_used_mib": 7000.0,
                "mean_gpu_util_pct": 90.0,
                "peak_temperature_c": 66.0,
                "peak_power_w": 250.0,
            },
            "hero": {
                "median_elapsed_s": 20.0,
                "median_seconds_per_megapixel": 8.5,
                "median_images_per_hour": 180.0,
                "peak_memory_used_mib": 10500.0,
                "mean_gpu_util_pct": 96.0,
                "peak_temperature_c": 72.0,
                "peak_power_w": 285.0,
            },
        },
    }


class ComparePerformanceTests(unittest.TestCase):
    def test_identical_workloads_are_comparable_and_report_deltas(self):
        module = _module()
        left = _fixture()
        right = deepcopy(left)
        right["endpoint"] = "http://127.0.0.1:8189"
        right["profile_summary"]["quality"]["median_elapsed_s"] = 9.0
        right["profile_summary"]["quality"]["peak_memory_used_mib"] = 6800.0
        result = module.compare(left, right)
        self.assertTrue(result["comparable"])
        elapsed = result["profiles"]["quality"]["median_elapsed_s"]
        self.assertEqual(elapsed["delta"], -1.0)
        self.assertEqual(elapsed["delta_pct"], -10.0)
        memory = result["profiles"]["quality"]["peak_memory_used_mib"]
        self.assertEqual(memory["delta"], -200.0)
        self.assertIn("do not establish visual quality", result["interpretation"]["quality"])

    def test_checkpoint_mismatch_fails_closed(self):
        module = _module()
        left = _fixture()
        right = deepcopy(left)
        right["checkpoint"] = "different.safetensors"
        with self.assertRaisesRegex(ValueError, "checkpoint mismatch"):
            module.compare(left, right)

    def test_prompt_fingerprint_mismatch_fails_closed(self):
        module = _module()
        left = _fixture()
        right = deepcopy(left)
        right["prompt_sha256"] = "c" * 64
        with self.assertRaisesRegex(ValueError, "prompt_sha256 mismatch"):
            module.compare(left, right)

    def test_gpu_identity_mismatch_fails_closed(self):
        module = _module()
        left = _fixture()
        right = deepcopy(left)
        right["gpu"]["uuid"] = "GPU-other"
        with self.assertRaisesRegex(ValueError, "GPU identity mismatch"):
            module.compare(left, right)

    def test_profile_order_or_set_mismatch_fails_closed(self):
        module = _module()
        left = _fixture()
        right = deepcopy(left)
        right["profiles"] = ["hero", "quality"]
        with self.assertRaisesRegex(ValueError, "profiles mismatch"):
            module.compare(left, right)


if __name__ == "__main__":
    unittest.main(verbosity=2)
