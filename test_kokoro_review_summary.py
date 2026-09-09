"""Offline tests for Kokoro listening-review aggregation."""

from __future__ import annotations

import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCORES = (
    "naturalness_1_5",
    "pronunciation_1_5",
    "pacing_1_5",
    "emotional_fit_1_5",
    "artifact_freedom_1_5",
    "production_usability_1_5",
)


def _module():
    path = ROOT / "kokoro-review-summary.py"
    spec = importlib.util.spec_from_file_location("evavo_kokoro_review_summary", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load Kokoro review summarizer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class KokoroReviewSummaryTests(unittest.TestCase):
    def _write(self, path: Path, rows: list[dict[str, str]]) -> None:
        fields = ["voice", "text_id", *SCORES, "review_notes"]
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def test_complete_review_ranks_by_production_evidence(self):
        module = _module()
        with tempfile.TemporaryDirectory() as value:
            path = Path(value) / "review.csv"
            good = {column: "5" for column in SCORES}
            okay = {column: "4" for column in SCORES}
            self._write(
                path,
                [
                    {"voice": "voice_a", "text_id": "neutral", **good, "review_notes": ""},
                    {"voice": "voice_a", "text_id": "numbers", **good, "review_notes": ""},
                    {"voice": "voice_b", "text_id": "neutral", **okay, "review_notes": ""},
                    {"voice": "voice_b", "text_id": "numbers", **okay, "review_notes": ""},
                ],
            )
            result = module.summarize(path)
            self.assertTrue(result["ok"])
            self.assertEqual(result["evidence_ranking"][0], "voice_a")
            self.assertEqual(result["voices"]["voice_a"]["overall_mean"], 5.0)
            self.assertIn("No default voice", result["promotion_note"])

    def test_incomplete_review_fails_closed(self):
        module = _module()
        with tempfile.TemporaryDirectory() as value:
            path = Path(value) / "review.csv"
            row = {column: "5" for column in SCORES}
            row["pronunciation_1_5"] = ""
            self._write(path, [{"voice": "voice_a", "text_id": "neutral", **row, "review_notes": ""}])
            with self.assertRaisesRegex(ValueError, "incomplete"):
                module.summarize(path)

    def test_out_of_range_review_fails_closed(self):
        module = _module()
        with tempfile.TemporaryDirectory() as value:
            path = Path(value) / "review.csv"
            row = {column: "5" for column in SCORES}
            row["pacing_1_5"] = "6"
            self._write(path, [{"voice": "voice_a", "text_id": "neutral", **row, "review_notes": ""}])
            with self.assertRaisesRegex(ValueError, "between 1 and 5"):
                module.summarize(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
