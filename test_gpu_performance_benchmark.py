"""Offline tests for EVAVO GPU performance benchmark helpers."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _module():
    path = ROOT / "gpu-performance-benchmark.py"
    source = path.read_text(encoding="utf-8-sig")
    compile(source, str(path), "exec", dont_inherit=True)
    spec = importlib.util.spec_from_file_location("evavo_gpu_performance_benchmark", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load GPU performance benchmark")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GpuPerformanceBenchmarkTests(unittest.TestCase):
    def test_nvidia_sample_parser_handles_numeric_and_unsupported_fields(self):
        module = _module()
        parsed = module.parse_nvidia_sample("98, 8123, 12282, 67, 247.5")
        self.assertEqual(parsed["gpu_util_pct"], 98.0)
        self.assertEqual(parsed["memory_used_mib"], 8123.0)
        self.assertEqual(parsed["memory_total_mib"], 12282.0)
        self.assertEqual(parsed["temperature_c"], 67.0)
        self.assertEqual(parsed["power_w"], 247.5)

        unsupported = module.parse_nvidia_sample("95, 7000, 12282, 65, [Not Supported]")
        self.assertIsNone(unsupported["power_w"])
        self.assertEqual(unsupported["gpu_util_pct"], 95.0)

    def test_nvidia_sample_parser_rejects_truncated_rows(self):
        module = _module()
        with self.assertRaisesRegex(ValueError, "expected 5"):
            module.parse_nvidia_sample("95, 7000")

    def test_telemetry_summary_reports_peaks_and_memory_percentage(self):
        module = _module()
        samples = [
            module.TelemetrySample(0.0, 20.0, 4000.0, 12000.0, 50.0, 120.0),
            module.TelemetrySample(0.25, 100.0, 9000.0, 12000.0, 70.0, 280.0),
            module.TelemetrySample(0.50, 80.0, 8000.0, 12000.0, 66.0, 250.0),
        ]
        summary = module.summarize_telemetry(samples)
        self.assertEqual(summary["sample_count"], 3)
        self.assertEqual(summary["peak_gpu_util_pct"], 100.0)
        self.assertEqual(summary["peak_memory_used_mib"], 9000.0)
        self.assertEqual(summary["memory_total_mib"], 12000.0)
        self.assertAlmostEqual(summary["peak_memory_util_pct"], 75.0, places=3)
        self.assertEqual(summary["peak_temperature_c"], 70.0)
        self.assertEqual(summary["peak_power_w"], 280.0)

    def test_profile_summary_uses_medians_and_keeps_failures_visible(self):
        module = _module()
        runs = [
            {
                "status": "completed",
                "elapsed_s": 10.0,
                "seconds_per_megapixel": 9.5,
                "images_per_hour": 360.0,
                "telemetry": {
                    "peak_memory_used_mib": 7000.0,
                    "mean_gpu_util_pct": 85.0,
                    "peak_temperature_c": 65.0,
                    "peak_power_w": 240.0,
                },
            },
            {
                "status": "completed",
                "elapsed_s": 14.0,
                "seconds_per_megapixel": 13.5,
                "images_per_hour": 257.14,
                "telemetry": {
                    "peak_memory_used_mib": 8200.0,
                    "mean_gpu_util_pct": 93.0,
                    "peak_temperature_c": 72.0,
                    "peak_power_w": 285.0,
                },
            },
            {"status": "failed", "elapsed_s": 2.0, "telemetry": {"sample_count": 0}},
        ]
        summary = module.summarize_profile(runs)
        self.assertEqual(summary["completed_runs"], 2)
        self.assertEqual(summary["failed_runs"], 1)
        self.assertEqual(summary["median_elapsed_s"], 12.0)
        self.assertEqual(summary["peak_memory_used_mib"], 8200.0)
        self.assertEqual(summary["mean_gpu_util_pct"], 89.0)
        self.assertEqual(summary["peak_temperature_c"], 72.0)
        self.assertEqual(summary["peak_power_w"], 285.0)

    def test_benchmark_is_explicit_checkpoint_frozen_and_sequential(self):
        source = (ROOT / "gpu-performance-benchmark.py").read_text(encoding="utf-8-sig")
        self.assertIn('parser.add_argument("--checkpoint", required=True', source)
        self.assertIn('quality_profile="quality"', source)
        self.assertIn('use_environment=False', source)
        self.assertIn('for repeat in range', source)
        self.assertIn('for profile in profiles', source)
        self.assertNotIn("ThreadPoolExecutor", source)
        self.assertNotIn("--concurrency", source)
        self.assertIn("does not authorize raising batch concurrency", source)

    def test_performance_runner_never_changes_profile_or_concurrency_defaults(self):
        source = (ROOT / "RUN-PERFORMANCE-BENCHMARK.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("test_frozen_quality_environment.py", source)
        self.assertIn("gpu-performance-benchmark.py", source)
        self.assertIn("runtime-snapshot.py", source)
        self.assertIn("does not change image profiles, sampler defaults or batch concurrency", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
