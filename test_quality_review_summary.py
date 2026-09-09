"""Regression tests for EVAVO human quality review aggregation."""

from __future__ import annotations

import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SCORES = (
    "prompt_adherence",
    "composition",
    "detail",
    "anatomy_geometry",
    "materials_texture",
    "lighting_color",
    "artifact_freedom",
    "production_usability",
)


def _load_module():
    path = ROOT / "quality-review-summary.py"
    spec = importlib.util.spec_from_file_location("evavo_quality_review_summary", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class QualityReviewSummaryTests(unittest.TestCase):
    def _write_review(self, path: Path, rows):
        fields = ["prompt_id", "profile", "seed", "output_index", *SCORES, "notes"]
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def _row(prompt, profile, seed, score):
        return {
            "prompt_id": prompt,
            "profile": profile,
            "seed": seed,
            "output_index": 0,
            **{column: score for column in SCORES},
            "notes": "",
        }

    def test_complete_review_produces_paired_baseline_deltas(self):
        module = _load_module()
        with tempfile.TemporaryDirectory() as value:
            path = Path(value) / "human_review.csv"
            rows = [
                self._row("product", "quality", 1337, 4),
                self._row("product", "hero", 1337, 5),
                self._row("portrait", "quality", 1337, 4),
                self._row("portrait", "hero", 1337, 4),
            ]
            self._write_review(path, rows)
            summary = module.summarize_review(path, baseline="quality")

            self.assertTrue(summary["review_complete"])
            self.assertTrue(summary["baseline_present"])
            self.assertEqual(summary["rows_total"], 4)
            self.assertEqual(summary["rows_scored"], 4)
            self.assertEqual(summary["profiles"]["quality"]["overall_human_score"], 4.0)
            self.assertEqual(summary["profiles"]["hero"]["overall_human_score"], 4.5)
            paired = summary["paired_comparisons"]["hero"]
            self.assertEqual(paired["pairs"], 2)
            self.assertEqual(paired["overall_wins"], 1)
            self.assertEqual(paired["overall_ties"], 1)
            self.assertEqual(paired["overall_losses"], 0)
            self.assertEqual(paired["overall_delta_mean"], 0.5)
            self.assertEqual(summary["descriptive_ranking"][0]["profile"], "hero")

    def test_blank_score_marks_review_incomplete_without_inventing_value(self):
        module = _load_module()
        with tempfile.TemporaryDirectory() as value:
            path = Path(value) / "human_review.csv"
            row = self._row("product", "quality", 1337, 4)
            row["artifact_freedom"] = ""
            self._write_review(path, [row])
            summary = module.summarize_review(path, baseline="quality")
            self.assertFalse(summary["review_complete"])
            self.assertEqual(summary["rows_scored"], 0)
            self.assertEqual(summary["incomplete"][0]["column"], "artifact_freedom")

    def test_out_of_range_score_is_rejected(self):
        module = _load_module()
        with tempfile.TemporaryDirectory() as value:
            path = Path(value) / "human_review.csv"
            row = self._row("product", "quality", 1337, 4)
            row["composition"] = 6
            self._write_review(path, [row])
            with self.assertRaisesRegex(ValueError, "between 1 and 5"):
                module.summarize_review(path, baseline="quality")


if __name__ == "__main__":
    unittest.main(verbosity=2)
