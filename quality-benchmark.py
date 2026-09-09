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
from evavo_local_image_generator.quality_profiles import profile_names


PROMPTS = {
    "product": {
        "prompt": (
            "Minimal black anodized aluminium desk speaker on a matte charcoal surface, three-quarter front angle, "
            "soft neutral seamless background, large diffused key light with narrow edge light, precise machined edges "
            "and fine metal grain, clean commercial product photography, accurate geometry, natural contact shadow, no branding"
        ),
        "negative": "warped product, duplicate product, floating object, incorrect perspective, melted edges, fake label, text, logo, watermark, excessive bloom",
    },
    "portrait": {
        "prompt": (
            "Studio portrait of a weathered shipwright in his late fifties, calm direct expression, chest-up three-quarter framing, "
            "dark timber workshop behind him, large soft window key light from camera left, subtle warm practical rim light, "
            "85mm portrait-lens perspective, realistic skin texture, natural grey hair detail, coherent hands, restrained cinematic color grade"
        ),
        "negative": "waxy skin, plastic skin, crossed eyes, asymmetrical pupils, malformed hands, extra fingers, duplicate face, blurry, oversharpened, watermark, text",
    },
    "landscape": {
        "prompt": (
            "Remote temperate coastline just after a storm, wet black rocks and tidal pools in the foreground, wind-bent grass "
            "and a narrow track through the midground, layered sea cliffs fading into rain haze, broken cloud with low late-afternoon light, "
            "eye-level 35mm landscape perspective, realistic wet stone and vegetation detail, controlled dynamic range"
        ),
        "negative": "muddy detail, smeared foliage, repeated rocks, impossible horizon, oversaturated sky, haloing, blurry, watermark, text",
    },
    "interior": {
        "prompt": (
            "Late Victorian reading room, fixed eye-level camera facing the long wall, broad clear floor lane in the lower third, "
            "dark oak shelves and worn leather chairs, overcast daylight through tall sash windows with restrained gas-lamp warmth, "
            "quiet dusty atmosphere, documentary architectural photography, straight verticals, coherent scale"
        ),
        "negative": "fisheye, extreme perspective, warped walls, floating furniture, duplicate doors, modern fixtures, blurry, text, watermark",
    },
    "game_art": {
        "prompt": (
            "1871 riverfront ship chandlery interior, fixed front-on side-stage camera with a broad horizontal gameplay lane, "
            "shop counter and merchant as the main midground silhouette, readable shelves, repair bench and exit zones, "
            "humid rain-darkened daylight with restrained lamp glow, black-and-white engraved DOS-era game art with dense hatching "
            "and hard silhouettes, historically coherent materials, uncluttered lower-third gameplay lane"
        ),
        "negative": "modern signage, electric lights, plastic, flat modern UI, photorealism, fantasy decoration, extreme perspective, isometric view, cluttered floor, watermark, text",
    },
}


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
    parser.add_argument("--seeds", default="1337")
    parser.add_argument("--checkpoint", default=os.getenv("EVAVO_COMFYUI_CHECKPOINT"))
    parser.add_argument("--output", default=str(Path(".evavo") / "quality-results"))
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--dry-run", action="store_true", help="Validate selections and print plan without rendering")
    args = parser.parse_args()

    profiles = parse_csv(args.profiles)
    invalid_profiles = [name for name in profiles if name not in profile_names() and name != "custom"]
    if invalid_profiles:
        parser.error(f"unknown profiles: {', '.join(invalid_profiles)}; available: {', '.join(profile_names())}")
    prompt_ids = parse_csv(args.prompts)
    invalid_prompts = [name for name in prompt_ids if name not in PROMPTS]
    if invalid_prompts:
        parser.error(f"unknown prompts: {', '.join(invalid_prompts)}; available: {', '.join(sorted(PROMPTS))}")
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
    if args.dry_run:
        print(json.dumps({"ok": True, "render_count": len(plan), "plan": plan}, indent=2))
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
        "schema_version": 2,
        "started_at": datetime.now().astimezone().isoformat(),
        "endpoint": backend.endpoint,
        "health": health,
        "sampling_inventory": sampling,
        "checkpoint": args.checkpoint,
        "plan": plan,
        "results": [],
        "failures": [],
    }
    write_json(run_dir / "manifest.json", manifest)

    for index, item in enumerate(plan, 1):
        prompt_spec = PROMPTS[item["prompt_id"]]
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

            result = {
                **item,
                "status": "completed",
                "elapsed_s": round(elapsed, 3),
                "quality": queued.get("quality"),
                "quality_applied": queued.get("quality_applied"),
                "render_passes": queued.get("render_passes"),
                "expected_output_width": expected_width,
                "expected_output_height": expected_height,
                "dimension_checked": dimension_checked,
                "dimension_ok": dimension_ok,
                "prompt_id_native": queued["task_id"],
                "outputs": outputs,
            }
            manifest["results"].append(result)
        except Exception as exc:
            failure = {**item, "status": "failed", "error": str(exc)}
            manifest["failures"].append(failure)
            print(f"  FAIL: {exc}", file=sys.stderr)
        write_json(run_dir / "manifest.json", manifest)

    manifest["finished_at"] = datetime.now().astimezone().isoformat()
    manifest["ok"] = not manifest["failures"] and len(manifest["results"]) == len(plan)
    write_json(run_dir / "manifest.json", manifest)

    print(f"\nQuality benchmark manifest: {run_dir / 'manifest.json'}")
    print(f"Completed: {len(manifest['results'])}/{len(plan)}")
    return 0 if manifest["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
