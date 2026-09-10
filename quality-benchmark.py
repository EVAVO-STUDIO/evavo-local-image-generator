#!/usr/bin/env python3
"""Deterministic, sequential SDXL quality benchmark for the real EVAVO ComfyUI backend."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from evavo_local_image_generator.backends import ComfyUIBackend
from evavo_local_image_generator.prompt_quality import load_prompt_corpus
from evavo_local_image_generator.quality_profiles import profile_names

ROOT = Path(__file__).resolve().parent
DEFAULT_PROMPT_CORPUS = ROOT / "config" / "quality-golden-prompts-v1.json"


def now_stamp() -> str:
    return datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def image_dimensions(path: Path) -> tuple[int | None, int | None]:
    try:
        with path.open("rb") as handle:
            head = handle.read(32)
        if head.startswith(b"\x89PNG\r\n\x1a\n") and len(head) >= 24:
            return struct.unpack(">II", head[16:24])
    except OSError:
        pass
    return None, None


def parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run same-seed SDXL quality comparisons against native ComfyUI")
    parser.add_argument("--endpoint", default=os.getenv("COMFYUI_ENDPOINT", "http://127.0.0.1:8188"))
    parser.add_argument("--profiles", default="quality,euler_reference,legacy_768_reference")
    parser.add_argument("--prompts", default="product,portrait,landscape,interior")
    parser.add_argument("--prompt-corpus", default=str(DEFAULT_PROMPT_CORPUS))
    parser.add_argument("--seeds", default="1337")
    parser.add_argument("--checkpoint", default=os.getenv("EVAVO_COMFYUI_CHECKPOINT"))
    parser.add_argument("--output", default=str(Path(".evavo") / "quality-results"))
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--dry-run", action="store_true", help="Validate selections and print plan without rendering")
    args = parser.parse_args()

    try:
        corpus = load_prompt_corpus(args.prompt_corpus)
    except ValueError as exc:
        parser.error(str(exc))
    prompts = corpus["prompts"]

    profiles = parse_csv(args.profiles)
    invalid_profiles = [name for name in profiles if name not in profile_names() and name != "custom"]
    if invalid_profiles:
        parser.error(f"unknown profiles: {', '.join(invalid_profiles)}; available: {', '.join(profile_names())}")
    prompt_ids = parse_csv(args.prompts)
    invalid_prompts = [name for name in prompt_ids if name not in prompts]
    if invalid_prompts:
        parser.error(f"unknown prompts: {', '.join(invalid_prompts)}; available: {', '.join(sorted(prompts))}")
    try:
        seeds = [int(value) for value in parse_csv(args.seeds)]
    except ValueError as exc:
        parser.error(f"--seeds must contain integers: {exc}")

    plan = [
        {"prompt_id": prompt_id, "profile": profile, "seed": seed}
        for prompt_id in prompt_ids
        for profile in profiles
        for seed in seeds
    ]
    corpus_receipt = {
        "prompt_set_version": corpus.get("prompt_set_version"),
        "source": corpus["source"],
        "sha256": corpus["sha256"],
    }
    if args.dry_run:
        print(
            json.dumps(
                {
                    "ok": True,
                    "environment_mode": "frozen",
                    "prompt_corpus": corpus_receipt,
                    "render_count": len(plan),
                    "plan": plan,
                },
                indent=2,
            )
        )
        return 0

    backend = ComfyUIBackend(args.endpoint)
    try:
        health = backend.health()
        sampling = backend.sampling_inventory()
    except RuntimeError as exc:
        print(f"ERROR: native ComfyUI is not ready: {exc}", file=sys.stderr)
        return 3

    run_dir = Path(args.output).expanduser().resolve() / now_stamp()
    run_dir.mkdir(parents=True, exist_ok=False)
    manifest: Dict[str, Any] = {
        "schema_version": 5,
        "started_at": datetime.now().astimezone().isoformat(),
        "endpoint": backend.endpoint,
        "environment_mode": "frozen",
        "environment_policy": "EVAVO_IMAGE_* profile/LoRA/workflow overrides are ignored for controlled comparisons",
        "health": health,
        "sampling_inventory": sampling,
        "checkpoint": args.checkpoint,
        "prompt_corpus": corpus_receipt,
        "plan": plan,
        "results": [],
        "failures": [],
    }
    write_json(run_dir / "manifest.json", manifest)

    for index, item in enumerate(plan, 1):
        prompt_spec = prompts[item["prompt_id"]]
        prompt_lint = prompt_spec["lint"]
        project = f"quality-benchmark/{item['prompt_id']}/{item['profile']}/{item['seed']}"
        print(f"[{index}/{len(plan)}] {item['prompt_id']} | {item['profile']} | seed {item['seed']}")
        started = time.perf_counter()
        try:
            queued = backend.queue_image(
                prompt_spec["prompt"],
                negative_prompt=prompt_spec["negative"],
                project_name=project,
                seed=item["seed"],
                checkpoint=args.checkpoint,
                quality_profile=item["profile"],
                use_environment=False,
            )
            target = run_dir / "images" / item["prompt_id"] / item["profile"] / str(item["seed"])
            files = backend.wait_and_download(queued["task_id"], target, timeout=args.timeout)
            elapsed = time.perf_counter() - started
            outputs = []
            for value in files:
                path = Path(value)
                width, height = image_dimensions(path)
                outputs.append(
                    {
                        "path": str(path),
                        "bytes": path.stat().st_size,
                        "sha256": sha256_file(path),
                        "width": width,
                        "height": height,
                    }
                )

            expected_width = queued.get("output_width")
            expected_height = queued.get("output_height")
            dimension_checked = bool(expected_width and expected_height and outputs)
            dimension_ok = True
            if dimension_checked:
                for output in outputs:
                    if output["width"] is None or output["height"] is None:
                        dimension_ok = False
                        break
                    if output["width"] != expected_width or output["height"] != expected_height:
                        dimension_ok = False
                        break
            if dimension_checked and not dimension_ok:
                actual = [(output["width"], output["height"]) for output in outputs]
                raise RuntimeError(
                    f"QUALITY_OUTPUT_DIMENSION_MISMATCH:expected {expected_width}x{expected_height}, got {actual}"
                )

            submitted_seed = queued.get("seed")
            if submitted_seed is not None and int(submitted_seed) != int(item["seed"]):
                raise RuntimeError(
                    f"QUALITY_SEED_MISMATCH:requested {item['seed']}, submitted {submitted_seed}"
                )
            if queued.get("lora") is not None:
                raise RuntimeError("QUALITY_AMBIENT_LORA_LEAK:controlled benchmark unexpectedly applied a LoRA")
            result = {
                **item,
                "status": "completed",
                "elapsed_s": round(elapsed, 3),
                "prompt_sha256": prompt_lint["prompt_sha256"],
                "prompt_warning_count": prompt_lint["warning_count"],
                "review_focus": prompt_spec.get("review_focus", []),
                "submitted_seed": submitted_seed,
                "checkpoint": queued.get("checkpoint"),
                "workflow_sha256": queued.get("workflow_sha256"),
                "workflow_node_count": queued.get("workflow_node_count"),
                "quality": queued.get("quality"),
                "quality_applied": queued.get("quality_applied"),
                "render_passes": queued.get("render_passes"),
                "lora": queued.get("lora"),
                "expected_output_width": expected_width,
                "expected_output_height": expected_height,
                "dimension_checked": dimension_checked,
                "dimension_ok": dimension_ok,
                "prompt_id_native": queued["task_id"],
                "outputs": outputs,
            }
            manifest["results"].append(result)
        except Exception as exc:
            failure = {**item, "prompt_sha256": prompt_lint["prompt_sha256"], "status": "failed", "error": str(exc)}
            manifest["failures"].append(failure)
            print(f"  FAIL: {exc}", file=sys.stderr)
        write_json(run_dir / "manifest.json", manifest)

    manifest["finished_at"] = datetime.now().astimezone().isoformat()
    manifest["ok"] = not manifest["failures"] and len(manifest["results"]) == len(plan)
    write_json(run_dir / "manifest.json", manifest)

    print(f"\nQuality benchmark manifest: {run_dir / 'manifest.json'}")
    print(f"Prompt corpus: {corpus_receipt['prompt_set_version']} {corpus_receipt['sha256']}")
    print("Environment mode: frozen (ambient image profile/LoRA/workflow overrides ignored)")
    print(f"Completed: {len(manifest['results'])}/{len(plan)}")
    return 0 if manifest["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
