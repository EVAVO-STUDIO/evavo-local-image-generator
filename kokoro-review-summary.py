#!/usr/bin/env python3
"""Summarize completed Kokoro human listening-review sheets without changing defaults."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

SCORE_COLUMNS = (
    "naturalness_1_5",
    "pronunciation_1_5",
    "pacing_1_5",
    "emotional_fit_1_5",
    "artifact_freedom_1_5",
    "production_usability_1_5",
)


def _score(value: str, column: str, row_number: int) -> float:
    if not value.strip():
        raise ValueError(f"row {row_number}: {column} is incomplete")
    try:
        number = float(value)
    except ValueError as exc:
        raise ValueError(f"row {row_number}: {column} must be a number from 1 to 5") from exc
    if not 1.0 <= number <= 5.0:
        raise ValueError(f"row {row_number}: {column} must be between 1 and 5")
    return number


def summarize(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    with source.open("r", newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("review CSV contains no rows")

    by_voice: dict[str, list[dict[str, float]]] = defaultdict(list)
    for index, row in enumerate(rows, 2):
        voice = str(row.get("voice", "")).strip()
        if not voice:
            raise ValueError(f"row {index}: voice is missing")
        scores = {column: _score(str(row.get(column, "")), column, index) for column in SCORE_COLUMNS}
        scores["overall_mean"] = statistics.fmean(scores.values())
        by_voice[voice].append(scores)

    voices: dict[str, Any] = {}
    for voice, values in sorted(by_voice.items()):
        summary = {
            column: round(statistics.fmean(item[column] for item in values), 4)
            for column in SCORE_COLUMNS
        }
        summary["overall_mean"] = round(statistics.fmean(item["overall_mean"] for item in values), 4)
        summary["samples"] = len(values)
        voices[voice] = summary

    ranking = sorted(
        voices,
        key=lambda voice: (
            voices[voice]["production_usability_1_5"],
            voices[voice]["artifact_freedom_1_5"],
            voices[voice]["pronunciation_1_5"],
            voices[voice]["overall_mean"],
        ),
        reverse=True,
    )
    return {
        "ok": True,
        "source": str(source),
        "sample_count": len(rows),
        "voices": voices,
        "evidence_ranking": ranking,
        "promotion_note": "Evidence only. No default voice was changed automatically.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize a completed Kokoro human review CSV")
    parser.add_argument("--review", required=True)
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    try:
        result = summarize(args.review)
    except (OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    output = Path(args.output).expanduser().resolve() if args.output else Path(args.review).expanduser().resolve().with_name("review-summary.json")
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({**result, "output": str(output)}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
