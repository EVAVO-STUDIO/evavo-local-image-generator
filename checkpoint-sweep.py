#!/usr/bin/env python3
"""Compare explicit ComfyUI checkpoints with fixed EVAVO prompts and seeds.

This tool intentionally requires an explicit checkpoint list. It does not assume
that every file visible to ComfyUI is architecturally compatible with the same
SDXL workflow, and it never promotes a checkpoint automatically.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import struct
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from evavo_local_image_generator.backends import ComfyUIBackend
from evavo_local_image_generator.prompt_quality import load_prompt_corpus
from evavo_local_image_generator.quality_profiles import profile_names

ROOT = Path(__file__).resolve().parent
DEFAULT_CORPUS = ROOT / "config" / "quality-golden-prompts-v1.json"


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _png_dimensions(path: Path) -> tuple[int | None, int | None]:
    try:
        with path.open("rb") as handle:
            head = handle.read(24)
        if head.startswith(b"\x89PNG\r\n\x1a\n") and len(head) >= 24:
            return struct.unpack(">II", head[16:24])
    except OSError:
        pass
    return None, None


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, path)


def _checkpoint_label(checkpoint: str, used: set[str]) -> str:
    stem = Path(checkpoint.replace("\\", "/")).stem
    clean = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")[:72] or "checkpoint"
    label = clean
    if label in used:
        suffix = hashlib.sha256(checkpoint.encode("utf-8")).hexdigest()[:8]
        label = f"{clean[:63]}-{suffix}"
    used.add(label)
    return label


def _resolve_checkpoint_names(requested: list[str], available: list[str]) -> list[dict[str, str]]:
    """Resolve requested checkpoints to exact live inventory names, case-insensitively.

    Basename-only requests are accepted only when unambiguous. This keeps Windows
    usage convenient without silently choosing between two nested models that
    share the same filename.
    """
    normalized: dict[str, str] = {value.replace("\\", "/").lower(): value for value in available}
    basenames: dict[str, list[str]] = {}
    for value in available:
        basenames.setdefault(Path(value.replace("\\", "/")).name.lower(), []).append(value)

    resolved: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in requested:
        key = raw.replace("\\", "/").lower()
        exact = normalized.get(key)
        if exact is None:
            matches = basenames.get(Path(key).name, [])
            if len(matches) == 1:
                exact = matches[0]
            elif len(matches) > 1:
                raise ValueError(
                    f"checkpoint {raw!r} is ambiguous; use one exact inventory path: {', '.join(matches)}"
                )
        if exact is None:
            raise ValueError(f"checkpoint {raw!r} is not in the active ComfyUI inventory")
        dedupe_key = exact.replace("\\", "/").lower()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        resolved.append({"requested": raw, "checkpoint": exact})
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare explicit local checkpoints using fixed prompts and seeds")
    parser.add_argument("--checkpoints", required=True, help="Comma-separated exact ComfyUI checkpoint names")
    parser.add_argument("--endpoint", default=os.getenv("COMFYUI_ENDPOINT", "http://127.0.0.1:8188"))
    parser.add_argument("--profile", default="quality")
    parser.add_argument("--prompts", default="product,portrait,interior,game_art")
    parser.add_argument("--prompt-corpus", default=str(DEFAULT_CORPUS))
    parser.add_argument("--seeds", default="1337")
    parser.add_argument("--timeout", type=float, default=1200.0)
    parser.add_argument("--output", default=str(Path(".evavo") / "quality-results" / "checkpoint-sweeps"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    checkpoint_requests = _csv(args.checkpoints)
    if not 2 <= len(checkpoint_requests) <= 12:
        parser.error("--checkpoints must contain between 2 and 12 checkpoint names")
    if args.profile not in profile_names():
        parser.error(f"unknown profile {args.profile!r}; available: {', '.join(profile_names())}")
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")

    try:
        corpus = load_prompt_corpus(args.prompt_corpus)
    except ValueError as exc:
        parser.error(str(exc))
    prompts = corpus["prompts"]
    prompt_ids = _csv(args.prompts)
    invalid_prompts = [value for value in prompt_ids if value not in prompts]
    if invalid_prompts:
        parser.error(f"unknown prompt ids: {', '.join(invalid_prompts)}")
    if not prompt_ids:
        parser.error("at least one prompt is required")
    try:
        seeds = [int(value) for value in _csv(args.seeds)]
    except ValueError as exc:
        parser.error(f"--seeds must contain integers: {exc}")
    if not 1 <= len(seeds) <= 8:
        parser.error("--seeds must contain between 1 and 8 values")
    if any(seed < 0 or seed > (2**63 - 1) for seed in seeds):
        parser.error("seeds must be between 0 and 2^63-1")

    backend = ComfyUIBackend(args.endpoint)
    try:
        health = backend.health()
        available = backend.checkpoints()
        sampling = backend.sampling_inventory()
        resolved_checkpoints = _resolve_checkpoint_names(checkpoint_requests, available)
    except (RuntimeError, ValueError) as exc:
        print(f"ERROR: checkpoint preflight failed: {exc}", file=sys.stderr)
        return 3

    used_labels: set[str] = set()
    for item in resolved_checkpoints:
        item["label"] = _checkpoint_label(item["checkpoint"], used_labels)

    plan = [
        {
            "checkpoint": checkpoint["checkpoint"],
            "checkpoint_label": checkpoint["label"],
            "prompt_id": prompt_id,
            "seed": seed,
        }
        for checkpoint in resolved_checkpoints
        for prompt_id in prompt_ids
        for seed in seeds
    ]
    if args.dry_run:
        print(
            json.dumps(
                {
                    "ok": True,
                    "environment_mode": "frozen",
                    "profile": args.profile,
                    "prompt_corpus_sha256": corpus["sha256"],
                    "resolved_checkpoints": resolved_checkpoints,
                    "render_count": len(plan),
                    "plan": plan,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    run_dir = Path(args.output).expanduser().resolve() / f"{stamp}-{args.profile}"
    run_dir.mkdir(parents=True, exist_ok=False)
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "benchmark_type": "checkpoint_quality_sweep",
        "started_at": datetime.now().astimezone().isoformat(),
        "endpoint": backend.endpoint,
        "environment_mode": "frozen",
        "environment_policy": "ambient EVAVO_IMAGE_* profile/LoRA/workflow overrides are ignored",
        "profile": args.profile,
        "health": health,
        "sampling_inventory": sampling,
        "available_checkpoint_count": len(available),
        "resolved_checkpoints": resolved_checkpoints,
        "prompt_corpus": {
            "version": corpus.get("prompt_set_version"),
            "source": corpus["source"],
            "sha256": corpus["sha256"],
        },
        "plan": plan,
        "results": [],
        "failures": [],
        "promotion_policy": "evidence only; no checkpoint is promoted automatically",
    }
    _write_json(run_dir / "manifest.json", manifest)

    for index, item in enumerate(plan, 1):
        prompt_spec = prompts[item["prompt_id"]]
        print(
            f"[{index}/{len(plan)}] {item['checkpoint_label']} | "
            f"{item['prompt_id']} | seed {item['seed']} | {args.profile}"
        )
        started = time.perf_counter()
        try:
            queued = backend.queue_image(
                prompt_spec["prompt"],
                negative_prompt=prompt_spec["negative"],
                project_name=(
                    f"checkpoint-sweep/{item['checkpoint_label']}/"
                    f"{item['prompt_id']}/{item['seed']}"
                ),
                seed=item["seed"],
                checkpoint=item["checkpoint"],
                quality_profile=args.profile,
                lora_name="",
                use_environment=False,
            )
            if queued.get("checkpoint") != item["checkpoint"]:
                raise RuntimeError(
                    f"CHECKPOINT_SWEEP_SELECTION_MISMATCH:requested {item['checkpoint']!r}, "
                    f"backend reported {queued.get('checkpoint')!r}"
                )
            if queued.get("lora") is not None:
                raise RuntimeError("CHECKPOINT_SWEEP_AMBIENT_LORA_LEAK:controlled sweep unexpectedly applied a LoRA")
            if int(queued.get("seed")) != int(item["seed"]):
                raise RuntimeError(
                    f"CHECKPOINT_SWEEP_SEED_MISMATCH:requested {item['seed']}, submitted {queued.get('seed')}"
                )

            target = (
                run_dir / "images" / item["checkpoint_label"] /
                item["prompt_id"] / str(item["seed"])
            )
            files = backend.wait_and_download(queued["task_id"], target, timeout=args.timeout)
            elapsed = time.perf_counter() - started
            outputs = []
            for value in files:
                path = Path(value)
                width, height = _png_dimensions(path)
                outputs.append(
                    {
                        "path": str(path),
                        "bytes": path.stat().st_size,
                        "sha256": _sha256(path),
                        "width": width,
                        "height": height,
                    }
                )
            if not outputs:
                raise RuntimeError("checkpoint sweep render produced no downloadable output")
            expected_width = queued.get("output_width")
            expected_height = queued.get("output_height")
            if expected_width and expected_height:
                actual = {(output.get("width"), output.get("height")) for output in outputs}
                if actual != {(expected_width, expected_height)}:
                    raise RuntimeError(
                        f"CHECKPOINT_SWEEP_OUTPUT_DIMENSION_MISMATCH:expected "
                        f"{expected_width}x{expected_height}, got {sorted(actual)}"
                    )

            manifest["results"].append(
                {
                    "prompt_id": item["prompt_id"],
                    # quality-report groups by this field, so use a stable
                    # checkpoint label rather than the common sampling profile.
                    "profile": item["checkpoint_label"],
                    "sampling_profile": args.profile,
                    "checkpoint": item["checkpoint"],
                    "checkpoint_label": item["checkpoint_label"],
                    "seed": item["seed"],
                    "submitted_seed": queued.get("seed"),
                    "status": "completed",
                    "elapsed_s": round(elapsed, 4),
                    "prompt_sha256": prompt_spec["lint"]["prompt_sha256"],
                    "prompt_warning_count": prompt_spec["lint"]["warning_count"],
                    "review_focus": prompt_spec.get("review_focus", []),
                    "workflow_sha256": queued.get("workflow_sha256"),
                    "workflow_node_count": queued.get("workflow_node_count"),
                    "quality": queued.get("quality"),
                    "quality_applied": queued.get("quality_applied"),
                    "render_passes": queued.get("render_passes"),
                    "expected_output_width": expected_width,
                    "expected_output_height": expected_height,
                    "lora": queued.get("lora"),
                    "outputs": outputs,
                }
            )
        except Exception as exc:
            manifest["failures"].append({**item, "status": "failed", "error": str(exc)})
            print(f"  FAIL: {exc}", file=sys.stderr)
        _write_json(run_dir / "manifest.json", manifest)

    manifest["finished_at"] = datetime.now().astimezone().isoformat()
    manifest["ok"] = not manifest["failures"] and len(manifest["results"]) == len(plan)
    _write_json(run_dir / "manifest.json", manifest)
    print(f"Checkpoint sweep manifest: {run_dir / 'manifest.json'}")
    print(f"Completed: {len(manifest['results'])}/{len(plan)}")
    return 0 if manifest["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
