#!/usr/bin/env python3
"""Compare the checkpoint's baked VAE against explicit live ComfyUI VAEs."""

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


def _label(name: str | None, used: set[str]) -> str:
    if not name:
        value = "checkpoint_vae"
    else:
        stem = Path(name.replace("\\", "/")).stem
        value = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")[:72] or "vae"
    if value in used:
        suffix = hashlib.sha256(str(name).encode("utf-8")).hexdigest()[:8]
        value = f"{value[:63]}-{suffix}"
    used.add(value)
    return value


def _resolve_vaes(requested: list[str], available: list[str]) -> list[str]:
    mapping = {value.lower(): value for value in available}
    resolved: list[str] = []
    for name in requested:
        exact = mapping.get(name.lower())
        if exact is None:
            raise ValueError(f"VAE {name!r} is not in the active ComfyUI VAELoader inventory")
        if exact not in resolved:
            resolved.append(exact)
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare baked checkpoint VAE against explicit external VAEs")
    parser.add_argument("--vaes", required=True, help="Comma-separated exact VAELoader inventory names")
    parser.add_argument("--endpoint", default=os.getenv("COMFYUI_ENDPOINT", "http://127.0.0.1:8188"))
    parser.add_argument("--checkpoint", default=os.getenv("EVAVO_COMFYUI_CHECKPOINT"))
    parser.add_argument("--profile", default="quality")
    parser.add_argument("--prompts", default="product,portrait,landscape,interior")
    parser.add_argument("--prompt-corpus", default=str(DEFAULT_CORPUS))
    parser.add_argument("--seeds", default="1337")
    parser.add_argument("--timeout", type=float, default=1200.0)
    parser.add_argument("--output", default=str(Path(".evavo") / "quality-results" / "vae-sweeps"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    requested_vaes = _csv(args.vaes)
    if not 1 <= len(requested_vaes) <= 8:
        parser.error("--vaes must contain between 1 and 8 VAE names")
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
    try:
        seeds = [int(value) for value in _csv(args.seeds)]
    except ValueError as exc:
        parser.error(f"--seeds must contain integers: {exc}")
    if not seeds or any(seed < 0 or seed > (2**63 - 1) for seed in seeds):
        parser.error("seeds must contain values between 0 and 2^63-1")

    backend = ComfyUIBackend(args.endpoint)
    try:
        health = backend.health()
        sampling = backend.sampling_inventory()
        available_vaes = sampling.get("vaes", []) if isinstance(sampling, dict) else []
        resolved_vaes = _resolve_vaes(requested_vaes, available_vaes)
        checkpoint = backend.choose_checkpoint(args.checkpoint, allow_repair=False)
    except (RuntimeError, ValueError) as exc:
        print(f"ERROR: VAE sweep preflight failed: {exc}", file=sys.stderr)
        return 3

    used: set[str] = set()
    candidates = [{"vae": None, "label": _label(None, used), "source": "checkpoint"}]
    candidates.extend({"vae": value, "label": _label(value, used), "source": "external"} for value in resolved_vaes)
    plan = [
        {"vae": candidate["vae"], "vae_label": candidate["label"], "source": candidate["source"], "prompt_id": prompt_id, "seed": seed}
        for candidate in candidates
        for prompt_id in prompt_ids
        for seed in seeds
    ]

    if args.dry_run:
        print(
            json.dumps(
                {
                    "ok": True,
                    "environment_mode": "frozen",
                    "checkpoint": checkpoint,
                    "profile": args.profile,
                    "resolved_vaes": resolved_vaes,
                    "prompt_corpus_sha256": corpus["sha256"],
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
        "benchmark_type": "vae_decode_sweep",
        "started_at": datetime.now().astimezone().isoformat(),
        "endpoint": backend.endpoint,
        "environment_mode": "frozen",
        "environment_policy": "only the explicit decode VAE varies; ambient image/LoRA/VAE/workflow overrides are ignored",
        "checkpoint": checkpoint,
        "profile": args.profile,
        "resolved_vaes": resolved_vaes,
        "health": health,
        "sampling_inventory": sampling,
        "prompt_corpus": {
            "version": corpus.get("prompt_set_version"),
            "source": corpus["source"],
            "sha256": corpus["sha256"],
        },
        "plan": plan,
        "results": [],
        "failures": [],
        "promotion_policy": "evidence only; the checkpoint VAE remains default until human review justifies an override",
    }
    _write_json(run_dir / "manifest.json", manifest)

    for index, item in enumerate(plan, 1):
        prompt_spec = prompts[item["prompt_id"]]
        print(f"[{index}/{len(plan)}] {item['vae_label']} | {item['prompt_id']} | seed {item['seed']}")
        started = time.perf_counter()
        try:
            queued = backend.queue_image(
                prompt_spec["prompt"],
                negative_prompt=prompt_spec["negative"],
                project_name=f"vae-sweep/{item['vae_label']}/{item['prompt_id']}/{item['seed']}",
                seed=item["seed"],
                checkpoint=checkpoint,
                quality_profile=args.profile,
                lora_name="",
                vae_name=item["vae"] or "",
                use_environment=False,
            )
            if queued.get("checkpoint") != checkpoint:
                raise RuntimeError("VAE_SWEEP_CHECKPOINT_CHANGED:checkpoint differed across decode comparison")
            if queued.get("lora") is not None:
                raise RuntimeError("VAE_SWEEP_AMBIENT_LORA_LEAK:controlled sweep unexpectedly applied a LoRA")
            expected_vae = {"name": item["vae"]} if item["vae"] else None
            if queued.get("vae") != expected_vae:
                raise RuntimeError(f"VAE_SWEEP_SELECTION_MISMATCH:expected {expected_vae}, got {queued.get('vae')}")
            if int(queued.get("seed")) != int(item["seed"]):
                raise RuntimeError("VAE_SWEEP_SEED_MISMATCH:submitted seed differs from plan")

            target = run_dir / "images" / item["vae_label"] / item["prompt_id"] / str(item["seed"])
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
                raise RuntimeError("VAE sweep render produced no downloadable output")
            manifest["results"].append(
                {
                    "prompt_id": item["prompt_id"],
                    "profile": item["vae_label"],
                    "sampling_profile": args.profile,
                    "checkpoint": checkpoint,
                    "vae": queued.get("vae"),
                    "vae_source": item["source"],
                    "seed": item["seed"],
                    "submitted_seed": queued.get("seed"),
                    "status": "completed",
                    "elapsed_s": round(elapsed, 4),
                    "prompt_sha256": prompt_spec["lint"]["prompt_sha256"],
                    "review_focus": prompt_spec.get("review_focus", []),
                    "workflow_sha256": queued.get("workflow_sha256"),
                    "workflow_node_count": queued.get("workflow_node_count"),
                    "quality": queued.get("quality"),
                    "quality_applied": queued.get("quality_applied"),
                    "render_passes": queued.get("render_passes"),
                    "expected_output_width": queued.get("output_width"),
                    "expected_output_height": queued.get("output_height"),
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
    print(f"VAE sweep manifest: {run_dir / 'manifest.json'}")
    print(f"Completed: {len(manifest['results'])}/{len(plan)}")
    return 0 if manifest["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
