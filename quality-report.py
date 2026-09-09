#!/usr/bin/env python3
"""Build technical diagnostics and a human-review report from a quality benchmark manifest."""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import os
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable

from evavo_local_image_generator.quality_metrics import image_quality_diagnostics


HUMAN_COLUMNS = (
    "prompt_adherence",
    "composition",
    "detail",
    "anatomy_geometry",
    "materials_texture",
    "lighting_color",
    "artifact_freedom",
    "production_usability",
    "notes",
)


def _load_manifest(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise ValueError(f"manifest does not exist: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read manifest {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("manifest root must be a JSON object")
    results = payload.get("results")
    if not isinstance(results, list):
        raise ValueError("manifest results must be a list")
    return payload


def _resolve_output_path(manifest_dir: Path, raw: Any) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("benchmark output path is missing")
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = manifest_dir / candidate
    return candidate.resolve(strict=True)


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _relative_href(path: Path, report_dir: Path) -> str:
    try:
        relative = os.path.relpath(path, report_dir)
    except ValueError:
        return path.as_uri()
    return Path(relative).as_posix()


def _write_json(path: Path, payload: Any) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, path)


def _format_metric(value: Any, digits: int = 3) -> str:
    number = _safe_float(value)
    if number is None:
        return "—"
    return f"{number:.{digits}f}"


def build_report(manifest_path: str | Path) -> Dict[str, Any]:
    manifest_file = Path(manifest_path).expanduser().resolve()
    manifest = _load_manifest(manifest_file)
    report_dir = manifest_file.parent

    rows: list[Dict[str, Any]] = []
    diagnostics_failures: list[Dict[str, Any]] = []

    for result in manifest.get("results", []):
        if not isinstance(result, dict) or result.get("status") != "completed":
            continue
        outputs = result.get("outputs")
        if not isinstance(outputs, list):
            continue
        elapsed = _safe_float(result.get("elapsed_s"))
        for output_index, output in enumerate(outputs):
            if not isinstance(output, dict):
                continue
            try:
                image_path = _resolve_output_path(report_dir, output.get("path"))
                metrics = image_quality_diagnostics(image_path)
            except Exception as exc:
                diagnostics_failures.append(
                    {
                        "prompt_id": result.get("prompt_id"),
                        "profile": result.get("profile"),
                        "seed": result.get("seed"),
                        "output_index": output_index,
                        "path": output.get("path"),
                        "error": str(exc),
                    }
                )
                continue

            seconds_per_mp = None
            if elapsed is not None and metrics["megapixels"] > 0:
                seconds_per_mp = elapsed / metrics["megapixels"]

            rows.append(
                {
                    "prompt_id": str(result.get("prompt_id", "")),
                    "profile": str(result.get("profile", "")),
                    "seed": result.get("seed"),
                    "output_index": output_index,
                    "path": str(image_path),
                    "relative_path": _relative_href(image_path, report_dir),
                    "elapsed_s": elapsed,
                    "seconds_per_megapixel": round(seconds_per_mp, 6) if seconds_per_mp is not None else None,
                    "render_passes": result.get("render_passes"),
                    "expected_output_width": result.get("expected_output_width"),
                    "expected_output_height": result.get("expected_output_height"),
                    **metrics,
                }
            )

    if not rows:
        detail = "; ".join(item["error"] for item in diagnostics_failures[:3])
        raise ValueError(f"manifest contains no decodable completed image outputs{': ' + detail if detail else ''}")

    by_profile: dict[str, list[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_profile[row["profile"]].append(row)

    profile_summary: Dict[str, Any] = {}
    for profile, profile_rows in sorted(by_profile.items()):
        elapsed_values = [row["elapsed_s"] for row in profile_rows if row["elapsed_s"] is not None]
        sec_mp_values = [row["seconds_per_megapixel"] for row in profile_rows if row["seconds_per_megapixel"] is not None]
        profile_summary[profile] = {
            "outputs": len(profile_rows),
            "median_elapsed_s": round(statistics.median(elapsed_values), 6) if elapsed_values else None,
            "mean_elapsed_s": round(statistics.fmean(elapsed_values), 6) if elapsed_values else None,
            "median_seconds_per_megapixel": round(statistics.median(sec_mp_values), 6) if sec_mp_values else None,
            "mean_megapixels": round(statistics.fmean(row["megapixels"] for row in profile_rows), 6),
            "mean_luminance": round(statistics.fmean(row["luminance_mean"] for row in profile_rows), 6),
            "mean_contrast": round(statistics.fmean(row["luminance_std"] for row in profile_rows), 6),
            "mean_detail_energy": round(statistics.fmean(row["local_detail_energy"] for row in profile_rows), 6),
            "mean_entropy_bits": round(statistics.fmean(row["luminance_entropy_bits"] for row in profile_rows), 6),
        }

    metrics_payload = {
        "schema_version": 1,
        "source_manifest": str(manifest_file),
        "diagnostic_warning": (
            "Technical metrics are descriptive diagnostics, not aesthetic quality scores. "
            "Human review remains authoritative for visual quality and production usability."
        ),
        "rows": rows,
        "profile_summary": profile_summary,
        "diagnostics_failures": diagnostics_failures,
    }
    metrics_path = report_dir / "quality_metrics.json"
    _write_json(metrics_path, metrics_payload)

    review_path = report_dir / "human_review.csv"
    base_columns = [
        "prompt_id",
        "profile",
        "seed",
        "output_index",
        "path",
        "elapsed_s",
        "seconds_per_megapixel",
        "render_passes",
        "width",
        "height",
        "megapixels",
        "luminance_mean",
        "luminance_std",
        "near_black_fraction",
        "near_white_fraction",
        "saturation_proxy_mean",
        "luminance_entropy_bits",
        "local_detail_energy",
    ]
    with review_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=[*base_columns, *HUMAN_COLUMNS], extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, **{column: "" for column in HUMAN_COLUMNS}})

    grouped: dict[tuple[str, Any], list[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["prompt_id"], row["seed"])].append(row)

    cards: list[str] = []
    for (prompt_id, seed), group in sorted(grouped.items(), key=lambda item: (str(item[0][0]), str(item[0][1]))):
        group_cards: list[str] = []
        for row in sorted(group, key=lambda item: item["profile"]):
            title = html.escape(row["profile"])
            href = html.escape(row["relative_path"], quote=True)
            dimensions = f"{row['width']}×{row['height']}"
            passes = row.get("render_passes") or "—"
            group_cards.append(
                f"""
                <article class="card">
                  <h3>{title}</h3>
                  <a href="{href}"><img src="{href}" loading="lazy" alt="{title} {html.escape(prompt_id)} seed {html.escape(str(seed))}"></a>
                  <dl>
                    <dt>Output</dt><dd>{dimensions} · {row['megapixels']:.2f} MP · {passes} pass(es)</dd>
                    <dt>Time</dt><dd>{_format_metric(row['elapsed_s'], 2)} s · {_format_metric(row['seconds_per_megapixel'], 2)} s/MP</dd>
                    <dt>Luma</dt><dd>{_format_metric(row['luminance_mean'])} mean · {_format_metric(row['luminance_std'])} contrast</dd>
                    <dt>Clipping</dt><dd>{_format_metric(row['near_black_fraction'] * 100, 2)}% black · {_format_metric(row['near_white_fraction'] * 100, 2)}% white</dd>
                    <dt>Colour</dt><dd>{_format_metric(row['saturation_proxy_mean'])} saturation proxy</dd>
                    <dt>Structure</dt><dd>{_format_metric(row['luminance_entropy_bits'])} bits entropy · {_format_metric(row['local_detail_energy'])} detail energy</dd>
                  </dl>
                </article>
                """
            )
        cards.append(
            f"<section><h2>{html.escape(prompt_id)} · seed {html.escape(str(seed))}</h2><div class='grid'>{''.join(group_cards)}</div></section>"
        )

    summary_rows = "".join(
        "<tr>"
        f"<td>{html.escape(profile)}</td>"
        f"<td>{summary['outputs']}</td>"
        f"<td>{_format_metric(summary['median_elapsed_s'], 2)}</td>"
        f"<td>{_format_metric(summary['median_seconds_per_megapixel'], 2)}</td>"
        f"<td>{_format_metric(summary['mean_megapixels'], 2)}</td>"
        f"<td>{_format_metric(summary['mean_contrast'])}</td>"
        f"<td>{_format_metric(summary['mean_detail_energy'])}</td>"
        "</tr>"
        for profile, summary in profile_summary.items()
    )

    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>EVAVO Quality Benchmark Review</title>
<style>
:root {{ color-scheme: dark; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }}
body {{ margin: 0; background: #0b0b0d; color: #f4f4f5; }}
main {{ max-width: 1600px; margin: auto; padding: 28px; }}
h1 {{ margin-bottom: 6px; }} .lede {{ color: #a1a1aa; max-width: 980px; }}
section {{ margin-top: 36px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 18px; align-items: start; }}
.card {{ background: #141417; border: 1px solid #27272a; border-radius: 12px; padding: 12px; }}
.card h3 {{ margin: 2px 0 10px; }}
.card img {{ width: 100%; height: auto; display: block; border-radius: 8px; background: #09090b; }}
dl {{ display: grid; grid-template-columns: 82px 1fr; gap: 6px 10px; font-size: 13px; }}
dt {{ color: #a1a1aa; }} dd {{ margin: 0; }}
table {{ border-collapse: collapse; width: 100%; overflow-x: auto; display: block; }}
th, td {{ padding: 9px 12px; border-bottom: 1px solid #27272a; text-align: right; white-space: nowrap; }}
th:first-child, td:first-child {{ text-align: left; }}
code {{ color: #fca5a5; }}
</style>
</head>
<body><main>
<h1>EVAVO Quality Benchmark Review</h1>
<p class="lede">Same-prompt, same-seed comparison. Technical metrics are diagnostics only. Do not choose a production profile from entropy, edge energy, file size, or timing alone; inspect composition, prompt adherence, anatomy/geometry, materials, lighting and artifact rate at fit-to-screen and 100% zoom, then complete <code>human_review.csv</code>.</p>
<section><h2>Profile diagnostics</h2>
<table><thead><tr><th>Profile</th><th>Outputs</th><th>Median s</th><th>Median s/MP</th><th>Mean MP</th><th>Mean contrast</th><th>Mean detail energy</th></tr></thead><tbody>{summary_rows}</tbody></table>
</section>
{''.join(cards)}
</main></body></html>
"""
    html_path = report_dir / "report.html"
    temp_html = html_path.with_suffix(".html.tmp")
    temp_html.write_text(document, encoding="utf-8")
    os.replace(temp_html, html_path)

    return {
        "ok": not diagnostics_failures,
        "manifest": str(manifest_file),
        "metrics": str(metrics_path),
        "human_review": str(review_path),
        "html_report": str(html_path),
        "image_outputs": len(rows),
        "diagnostics_failures": len(diagnostics_failures),
        "profiles": profile_summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate technical diagnostics and human-review files for an EVAVO quality benchmark")
    parser.add_argument("--manifest", required=True, help="Path to quality-benchmark manifest.json")
    args = parser.parse_args()
    try:
        summary = build_report(args.manifest)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
