#!/usr/bin/env python3
"""Run an isolated fixed-seed LoRA strength sweep and build a review package."""

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
from typing import Any

from evavo_local_image_generator.backends import ComfyUIBackend


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _strengths(value: str) -> list[float]:
    result: list[float] = []
    for raw in _csv(value):
        try:
            number = float(raw)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"invalid LoRA strength {raw!r}") from exc
        if not -4.0 <= number <= 4.0:
            raise argparse.ArgumentTypeError("LoRA strengths must be between -4 and 4")
        result.append(number)
    if not result:
        raise argparse.ArgumentTypeError("at least one LoRA strength is required")
    return result


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare one LoRA at fixed strengths against the same unmodified base render")
    parser.add_argument("--lora", required=True, help="Exact ComfyUI LoRA inventory name")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--negative", default="")
    parser.add_argument("--endpoint", default=os.getenv("COMFYUI_ENDPOINT", "http://127.0.0.1:8188"))
    parser.add_argument("--checkpoint", default=os.getenv("EVAVO_COMFYUI_CHECKPOINT"))
    parser.add_argument("--profile", default="quality", help="Use quality for efficient sweeps; hero can be tested after strength selection")
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--strengths", type=_strengths, default=_strengths("0,0.5,0.7,0.9"))
    parser.add_argument("--clip-strength", type=float, default=None, help="Fixed CLIP strength; default matches each model strength")
    parser.add_argument("--output", default=str(Path(".evavo") / "quality-results" / "lora-sweeps"))
    parser.add_argument("--timeout", type=float, default=900.0)
    args = parser.parse_args()

    backend = ComfyUIBackend(args.endpoint)
    try:
        health = backend.health()
        inventory = backend.sampling_inventory()
    except Exception as exc:
        print(f"ERROR: ComfyUI is not ready: {exc}", file=sys.stderr)
        return 3

    loras = inventory.get("loras") if isinstance(inventory, dict) else None
    if isinstance(loras, list) and loras and args.lora not in loras:
        print(f"ERROR: LoRA {args.lora!r} is not in the active ComfyUI inventory", file=sys.stderr)
        return 4

    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    safe_name = Path(args.lora).stem.replace(" ", "_")[:80] or "lora"
    run_dir = Path(args.output).expanduser().resolve() / f"{stamp}-{safe_name}"
    run_dir.mkdir(parents=True, exist_ok=False)
    manifest: dict[str, Any] = {
        "schema_version": 2,
        "benchmark_type": "lora_strength_sweep",
        "started_at": datetime.now().astimezone().isoformat(),
        "endpoint": backend.endpoint,
        "health": health,
        "lora_name": args.lora,
        "quality_profile": args.profile,
        "checkpoint": args.checkpoint,
        "prompt": args.prompt,
        "negative_prompt": args.negative,
        "seed": args.seed,
        "strengths": args.strengths,
        "results": [],
        "failures": [],
    }
    _write_json(run_dir / "manifest.json", manifest)

    for index, strength in enumerate(args.strengths, 1):
        base = abs(strength) < 1e-12
        label = "base" if base else f"lora_{strength:+.2f}".replace("+", "p").replace("-", "m").replace(".", "p")
        print(f"[{index}/{len(args.strengths)}] {label} | seed {args.seed}")
        started = time.perf_counter()
        try:
            kwargs: dict[str, Any] = {
                "project_name": f"lora-sweep/{safe_name}/{label}/{args.seed}",
                "negative_prompt": args.negative,
                "seed": args.seed,
                "checkpoint": args.checkpoint,
                "quality_profile": args.profile,
            }
            if not base:
                kwargs.update(
                    lora_name=args.lora,
                    lora_model_strength=strength,
                    lora_clip_strength=args.clip_strength if args.clip_strength is not None else strength,
                )
            queued = backend.queue_image(args.prompt, **kwargs)
            target = run_dir / "images" / label
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
                raise RuntimeError("LoRA sweep render produced no downloadable outputs")
            manifest["results"].append(
                {
                    "prompt_id": "lora_sweep",
                    "profile": label,
                    "seed": args.seed,
                    "status": "completed",
                    "elapsed_s": round(elapsed, 3),
                    "render_passes": queued.get("render_passes"),
                    "expected_output_width": queued.get("output_width"),
                    "expected_output_height": queued.get("output_height"),
                    "quality": queued.get("quality"),
                    "lora": queued.get("lora"),
                    "outputs": outputs,
                }
            )
        except Exception as exc:
            failure = {"profile": label, "seed": args.seed, "strength": strength, "status": "failed", "error": str(exc)}
            manifest["failures"].append(failure)
            print(f"  FAIL: {exc}", file=sys.stderr)
        _write_json(run_dir / "manifest.json", manifest)

    manifest["finished_at"] = datetime.now().astimezone().isoformat()
    manifest["ok"] = not manifest["failures"] and len(manifest["results"]) == len(args.strengths)
    _write_json(run_dir / "manifest.json", manifest)
    print(str(run_dir / "manifest.json"))
    return 0 if manifest["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
