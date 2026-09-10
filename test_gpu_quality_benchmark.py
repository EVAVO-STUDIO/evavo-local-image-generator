"""Offline tests for GPU quality benchmark telemetry and summaries."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def _load_module():
    path = ROOT / "gpu-quality-benchmark.py"
    spec = importlib.util.spec_from_file_location("evavo_gpu_quality_benchmark", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GpuQualityBenchmarkTests(unittest.TestCase):
    def test_gpu_sample_summary_tracks_peak_pressure(self):
        module = _load_module()
        samples = [
            {
                "name": "RTX test",
                "driver_version": "999.1",
                "memory_total_mib": 12000.0,
                "memory_used_mib": 1000.0,
                "memory_free_mib": 11000.0,
                "utilization_gpu_pct": 10.0,
                "power_draw_w": 50.0,
                "temperature_c": 40.0,
            },
            {
                "name": "RTX test",
                "driver_version": "999.1",
                "memory_total_mib": 12000.0,
                "memory_used_mib": 9500.0,
                "memory_free_mib": 2500.0,
                "utilization_gpu_pct": 98.0,
                "power_draw_w": 285.0,
                "temperature_c": 72.0,
            },
            {
                "name": "RTX test",
                "driver_version": "999.1",
                "memory_total_mib": 12000.0,
                "memory_used_mib": 1200.0,
                "memory_free_mib": 10800.0,
                "utilization_gpu_pct": 8.0,
                "power_draw_w": 45.0,
                "temperature_c": 43.0,
            },
        ]
        summary = module.summarize_gpu_samples(samples)
        self.assertTrue(summary["available"])
        self.assertEqual(summary["sample_count"], 3)
        self.assertEqual(summary["memory_used_peak_mib"], 9500.0)
        self.assertEqual(summary["memory_free_min_mib"], 2500.0)
        self.assertEqual(summary["utilization_peak_pct"], 98.0)
        self.assertEqual(summary["power_peak_w"], 285.0)
        self.assertEqual(summary["temperature_peak_c"], 72.0)

    def test_performance_summary_compares_cost_to_quality_baseline(self):
        module = _load_module()
        results = [
            {
                "profile": "quality",
                "status": "completed",
                "elapsed_s": 10.0,
                "seconds_per_megapixel": 9.5,
                "render_passes": 1,
                "expected_output_width": 1024,
                "expected_output_height": 1024,
                "gpu": {"memory_used_peak_mib": 8000.0},
            },
            {
                "profile": "quality",
                "status": "completed",
                "elapsed_s": 12.0,
                "seconds_per_megapixel": 11.4,
                "render_passes": 1,
                "expected_output_width": 1024,
                "expected_output_height": 1024,
                "gpu": {"memory_used_peak_mib": 8200.0},
            },
            {
                "profile": "hero",
                "status": "completed",
                "elapsed_s": 22.0,
                "seconds_per_megapixel": 9.3,
                "render_passes": 2,
                "expected_output_width": 1536,
                "expected_output_height": 1536,
                "gpu": {"memory_used_peak_mib": 10400.0},
            },
        ]
        summary = module.performance_summary(results)
        self.assertEqual(summary["quality"]["median_elapsed_s"], 11.0)
        self.assertEqual(summary["quality"]["time_ratio_vs_quality"], 1.0)
        self.assertEqual(summary["hero"]["time_ratio_vs_quality"], 2.0)
        self.assertEqual(summary["hero"]["render_passes"], 2)
        self.assertEqual(summary["hero"]["output_width"], 1536)

    def test_benchmark_is_frozen_and_does_not_auto_promote(self):
        source = (ROOT / "gpu-quality-benchmark.py").read_text(encoding="utf-8-sig")
        self.assertIn("use_environment=False", source)
        self.assertIn("GPU_BENCHMARK_AMBIENT_LORA_LEAK", source)
        self.assertIn("Throughput and VRAM evidence do not measure visual quality", source)
        self.assertNotIn("set_default_profile", source)
        self.assertNotIn("EVAVO_IMAGE_QUALITY_PROFILE =", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
