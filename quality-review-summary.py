#!/usr/bin/env python3
"""Summarize completed EVAVO human image-quality review sheets.

This tool aggregates explicit human scores. It does not use technical image
metrics as a proxy for aesthetics and it never mutates production defaults.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict


SCORE_COLUMNS = (
    "prompt_adherence",
    "composition",
    "detail",
    "anatomy_geometry",
    "materials_texture",
    "lighting_color",
    "artifact_freedom",
    "production_usability",
)


def _score(value: Any, *, row_number: int, column: str) -> float:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"row {row_number}: {column} is blank")
    try:
        number = float(text)
    except ValueError as exc:
        raise ValueError(f"row {row_number}: {column} must be a number from 1 to 5") from exc
    if not math.isfinite(number) or not 1.0 <= number <= 5.0:
        raise ValueError(f"row {row_number}: {column} must be between 1 and 5")
    return number


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, path)


def _pair_key(row: Dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("prompt_id", "")),
        str(row.get("seed", "")),
        str(row.get("output_index", "0")),
    )


def summarize_review(review_path: str | Path, *, baseline: str = "quality") -> Dict[str, Any]:
    source = Path(review_path).expanduser().resolve(strict=True)
    if not source.is_file():
        raise ValueError(f"review path is not an ordinary file: {source}")

    with source.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        required = {"prompt_id", "profile", "seed", "output_index", *SCORE_COLUMNS}
        missing = sorted(required.difference(fieldnames))
        if missing:
            raise ValueError(f"review CSV is missing required columns: {', '.join(missing)}")
        raw_rows = list(reader)

    if not raw_rows:
        raise ValueError("review CSV contains no image rows")

    rows: list[Dict[str, Any]] = []
    incomplete: list[Dict[str, Any]] = []
    invalid: list[Dict[str, Any]] = []
    for row_number, raw in enumerate(raw_rows, start=2):
        profile = str(raw.get("profile", "")).strip()
        if not profile:
            invalid.append({"row": row_number, "error": "profile is blank"})
            continue
        parsed: Dict[str, float] = {}
        row_failed = False
        for column in SCORE_COLUMNS:
            value = str(raw.get(column, "") or "").strip()
            if not value:
                incomplete.append({"row": row_number, "profile": profile, "column": column})
                row_failed = True
                continue
            try:
                parsed[column] = _score(value, row_number=row_number, column=column)
            except ValueError as exc:
                invalid.append({"row": row_number, "profile": profile, "column": column, "error": str(exc)})
                row_failed = True
        if row_failed:
            continue
        overall = statistics.fmean(parsed.values())
        rows.append(
            {
                **raw,
                "profile": profile,
                "scores": parsed,
                "overall_human_score": round(overall, 6),
            }
        )

    if invalid:
        first = invalid[0]["error"]
        raise ValueError(f"review CSV contains invalid scores: {first}")

    review_complete = not incomplete and len(rows) == len(raw_rows)
    if not rows:
        return {
            "schema_version": 1,
            "source_review": str(source),
            "review_complete": False,
            "rows_total": len(raw_rows),
            "rows_scored": 0,
            "incomplete": incomplete,
            "profiles": {},
            "baseline": baseline,
            "paired_comparisons": {},
        }

    grouped: dict[str, list[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["profile"]].append(row)

    profiles: Dict[str, Any] = {}
    for profile, profile_rows in sorted(grouped.items()):
        column_means = {
            column: round(statistics.fmean(row["scores"][column] for row in profile_rows), 6)
            for column in SCORE_COLUMNS
        }
        profiles[profile] = {
            "rows": len(profile_rows),
            "overall_human_score": round(
                statistics.fmean(row["overall_human_score"] for row in profile_rows),
                6,
            ),
            "dimensions": column_means,
        }

    baseline_rows = {
        _pair_key(row): row
        for row in rows
        if row["profile"] == baseline
    }
    paired: Dict[str, Any] = {}
    for profile, profile_rows in sorted(grouped.items()):
        if profile == baseline:
            continue
        comparisons = []
        for row in profile_rows:
            baseline_row = baseline_rows.get(_pair_key(row))
            if baseline_row is None:
                continue
            comparisons.append(
                {
                    "overall": row["overall_human_score"] - baseline_row["overall_human_score"],
                    "production_usability": row["scores"]["production_usability"] - baseline_row["scores"]["production_usability"],
                    "artifact_freedom": row["scores"]["artifact_freedom"] - baseline_row["scores"]["artifact_freedom"],
                }
            )
        if not comparisons:
            paired[profile] = {"pairs": 0, "note": "no exact prompt/seed/output pairs with baseline"}
            continue
        overall_deltas = [item["overall"] for item in comparisons]
        usability_deltas = [item["production_usability"] for item in comparisons]
        artifact_deltas = [item["artifact_freedom"] for item in comparisons]
        paired[profile] = {
            "pairs": len(comparisons),
            "overall_delta_mean": round(statistics.fmean(overall_deltas), 6),
            "production_usability_delta_mean": round(statistics.fmean(usability_deltas), 6),
            "artifact_freedom_delta_mean": round(statistics.fmean(artifact_deltas), 6),
            "overall_wins": sum(value > 0 for value in overall_deltas),
            "overall_ties": sum(value == 0 for value in overall_deltas),
            "overall_losses": sum(value < 0 for value in overall_deltas),
        }

    ranking = [
        {
            "profile": profile,
            "overall_human_score": data["overall_human_score"],
            "production_usability": data["dimensions"]["production_usability"],
            "artifact_freedom": data["dimensions"]["artifact_freedom"],
        }
        for profile, data in profiles.items()
    ]
    ranking.sort(
        key=lambda item: (
            item["production_usability"],
            item["artifact_freedom"],
            item["overall_human_score"],
        ),
        reverse=True,
    )

    return {
        "schema_version": 1,
        "source_review": str(source),
        "review_complete": review_complete,
        "rows_total": len(raw_rows),
        "rows_scored": len(rows),
        "incomplete": incomplete,
        "score_scale": "1-5; higher is better",
        "scoring_dimensions": list(SCORE_COLUMNS),
        "aggregation_note": (
            "Ranking is descriptive aggregation of human scores only. It does not automatically change production defaults. "
            "Paired deltas compare exact prompt/seed/output matches against the selected baseline."
        ),
        "baseline": baseline,
        "baseline_present": baseline in profiles,
        "profiles": profiles,
        "paired_comparisons": paired,
        "descriptive_ranking": ranking,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize a completed EVAVO human quality review CSV")
    parser.add_argument("--review", required=True)
    parser.add_argument("--baseline", default="quality")
    parser.add_argument("--output", default=None)
    parser.add_argument("--allow-incomplete", action="store_true")
    args = parser.parse_args()

    try:
        summary = summarize_review(args.review, baseline=args.baseline)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    output = Path(args.output).expanduser().resolve() if args.output else Path(args.review).expanduser().resolve().parent / "human_review_summary.json"
    _write_json(output, summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Summary: {output}")

    if not summary["review_complete"] and not args.allow_incomplete:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
