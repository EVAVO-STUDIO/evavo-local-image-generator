"""Fast local tests for EVAVO benchmark diagnostics and review report generation."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from evavo_local_image_generator.quality_metrics import image_quality_diagnostics


ROOT = Path(__file__).resolve().parent


def _load_report_module():
    path = ROOT / "quality-report.py"
    spec = importlib.util.spec_from_file_location("evavo_quality_report", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class QualityReportTests(unittest.TestCase):
    def _fixture_image(self, root: Path, name: str = "fixture.png") -> Path:
        # Deterministic horizontal/vertical gradient with enough structure to
        # exercise entropy, clipping, saturation and detail diagnostics.
        x = np.linspace(0, 255, 64, dtype=np.uint8)
        y = np.linspace(255, 0, 64, dtype=np.uint8)
        red = np.tile(x, (64, 1))
        green = np.tile(y[:, None], (1, 64))
        blue = np.full((64, 64), 96, dtype=np.uint8)
        rgb = np.stack([red, green, blue], axis=2)
        path = root / name
        Image.fromarray(rgb, mode="RGB").save(path)
        return path

    def test_image_diagnostics_are_finite_and_dimensionally_correct(self):
        with tempfile.TemporaryDirectory() as value:
            path = self._fixture_image(Path(value))
            metrics = image_quality_diagnostics(path)
            self.assertEqual((metrics["width"], metrics["height"]), (64, 64))
            self.assertAlmostEqual(metrics["megapixels"], 0.004096, places=6)
            self.assertGreater(metrics["file_bytes"], 0)
            self.assertGreater(metrics["luminance_std"], 0)
            self.assertGreater(metrics["luminance_entropy_bits"], 0)
            self.assertGreater(metrics["local_detail_energy"], 0)
            self.assertGreaterEqual(metrics["near_black_fraction"], 0)
            self.assertLessEqual(metrics["near_black_fraction"], 1)
            self.assertGreaterEqual(metrics["near_white_fraction"], 0)
            self.assertLessEqual(metrics["near_white_fraction"], 1)

    def test_report_builds_json_csv_and_html_from_benchmark_manifest(self):
        module = _load_report_module()
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            image = self._fixture_image(root)
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "results": [
                            {
                                "prompt_id": "product",
                                "profile": "hero",
                                "seed": 1337,
                                "status": "completed",
                                "elapsed_s": 8.0,
                                "render_passes": 2,
                                "expected_output_width": 64,
                                "expected_output_height": 64,
                                "outputs": [{"path": str(image), "width": 64, "height": 64}],
                            }
                        ],
                        "failures": [],
                    }
                ),
                encoding="utf-8",
            )

            result = module.build_report(manifest)
            self.assertTrue(result["ok"])
            self.assertEqual(result["image_outputs"], 1)
            self.assertEqual(result["diagnostics_failures"], 0)

            metrics = root / "quality_metrics.json"
            review = root / "human_review.csv"
            report = root / "report.html"
            self.assertTrue(metrics.is_file())
            self.assertTrue(review.is_file())
            self.assertTrue(report.is_file())

            metrics_payload = json.loads(metrics.read_text(encoding="utf-8"))
            row = metrics_payload["rows"][0]
            self.assertEqual(row["profile"], "hero")
            self.assertEqual(row["render_passes"], 2)
            self.assertAlmostEqual(row["seconds_per_megapixel"], 8.0 / 0.004096, places=3)

            review_text = review.read_text(encoding="utf-8-sig")
            self.assertIn("production_usability", review_text)
            self.assertIn("artifact_freedom", review_text)
            html_text = report.read_text(encoding="utf-8")
            self.assertIn("Same-prompt, same-seed comparison", html_text)
            self.assertIn("hero", html_text)
            self.assertIn("Technical metrics are diagnostics only", html_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
