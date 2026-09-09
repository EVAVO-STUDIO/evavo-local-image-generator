#!/usr/bin/env python3
"""Compare two controlled EVAVO GPU performance evidence files.

The comparison refuses mismatched workloads so a runtime migration cannot look
faster merely because checkpoint, prompt, seed, repeat count or GPU changed.
It reports descriptive deltas only and never promotes a runtime/profile.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


def _read(path_value: str | Path) -> tuple[Path, dict[str, Any]]:
    path = Path(path_value).expanduser().resolve()
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read performance evidence {path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError(f"unsupported performance evidence schema: {path}")
    if not isinstance(payload.get("profile_summary"), dict):
        raise ValueError(f"performance evidence has no profile_summary: {path}")
    return path, payload


def _gpu_identity(payload: dict[str, Any]) -> tuple[Any, Any, Any]:
    gpu = payload.get("gpu") if isinstance(payload.get("gpu"), dict) else {}
    return gpu.get("uuid"), gpu.get("name"), gpu.get("memory_total_mib")


def compatibility_errors(left: dict[str, Any], right: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    checks = (
        ("checkpoint", left.get("checkpoint"), right.get("checkpoint")),
        ("prompt_id", left.get("prompt_id"), right.get("prompt_id")),
        ("prompt_sha256", left.get("prompt_sha256"), right.get("prompt_sha256")),
        ("seed", left.get("seed"), right.get("seed")),
        ("repeats", left.get("repeats"), right.get("repeats")),
        ("profiles", left.get("profiles"), right.get("profiles")),
    )
    for label, a, b in checks:
        if a != b:
            errors.append(f"{label} mismatch: {a!r} != {b!r}")
    left_corpus = left.get("prompt_corpus") if isinstance(left.get("prompt_corpus"), dict) else {}
    right_corpus = right.get("prompt_corpus") if isinstance(right.get("prompt_corpus"), dict) else {}
    if left_corpus.get("sha256") != right_corpus.get("sha256"):
        errors.append("prompt corpus SHA-256 mismatch")
    if _gpu_identity(left) != _gpu_identity(right):
        errors.append(f"GPU identity mismatch: {_gpu_identity(left)!r} != {_gpu_identity(right)!r}")
    return errors


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _delta(before: Any, after: Any) -> dict[str, float | None]:
    a = _number(before)
    b = _number(after)
    if a is None or b is None:
        return {"before": a, "after": b, "delta": None, "delta_pct": None}
    pct = ((b - a) / a * 100.0) if a != 0 else None
    return {
        "before": round(a, 6),
        "after": round(b, 6),
        "delta": round(b - a, 6),
        "delta_pct": round(pct, 6) if pct is not None else None,
    }


def compare(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    errors = compatibility_errors(left, right)
    if errors:
        raise ValueError("benchmark workloads are not comparable: " + " | ".join(errors))

    left_summary = left["profile_summary"]
    right_summary = right["profile_summary"]
    profiles = list(left.get("profiles") or sorted(left_summary))
    profile_results: dict[str, Any] = {}
    for profile in profiles:
        a = left_summary.get(profile)
        b = right_summary.get(profile)
        if not isinstance(a, dict) or not isinstance(b, dict):
            raise ValueError(f"profile summary missing for {profile}")
        profile_results[profile] = {
            "median_elapsed_s": _delta(a.get("median_elapsed_s"), b.get("median_elapsed_s")),
            "median_seconds_per_megapixel": _delta(a.get("median_seconds_per_megapixel"), b.get("median_seconds_per_megapixel")),
            "median_images_per_hour": _delta(a.get("median_images_per_hour"), b.get("median_images_per_hour")),
            "peak_memory_used_mib": _delta(a.get("peak_memory_used_mib"), b.get("peak_memory_used_mib")),
            "mean_gpu_util_pct": _delta(a.get("mean_gpu_util_pct"), b.get("mean_gpu_util_pct")),
            "peak_temperature_c": _delta(a.get("peak_temperature_c"), b.get("peak_temperature_c")),
            "peak_power_w": _delta(a.get("peak_power_w"), b.get("peak_power_w")),
        }

    return {
        "ok": True,
        "comparable": True,
        "left_endpoint": left.get("endpoint"),
        "right_endpoint": right.get("endpoint"),
        "checkpoint": left.get("checkpoint"),
        "prompt_id": left.get("prompt_id"),
        "prompt_sha256": left.get("prompt_sha256"),
        "seed": left.get("seed"),
        "repeats": left.get("repeats"),
        "gpu": left.get("gpu"),
        "profiles": profile_results,
        "interpretation": {
            "timing": "Negative elapsed/seconds-per-megapixel delta means the right runtime was faster.",
            "throughput": "Positive images-per-hour delta means the right runtime had higher throughput.",
            "memory": "Negative peak-memory delta means the right runtime used less peak VRAM.",
            "quality": "Performance deltas do not establish visual quality or authorize runtime/profile promotion.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare two controlled EVAVO GPU performance evidence files")
    parser.add_argument("left")
    parser.add_argument("right")
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    try:
        left_path, left = _read(args.left)
        right_path, right = _read(args.right)
        result = compare(left, right)
    except ValueError as exc:
        print(json.dumps({"ok": False, "comparable": False, "error": str(exc)}, indent=2, ensure_ascii=False))
        return 2
    result["left"] = str(left_path)
    result["right"] = str(right_path)
    if args.output:
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        result["output"] = str(output)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
