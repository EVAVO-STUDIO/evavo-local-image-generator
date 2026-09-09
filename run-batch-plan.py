#!/usr/bin/env python3
"""Production entrypoint for deterministic EVAVO image batch plans.

`batch-plan.py` owns parsing/execution primitives. This entrypoint adds the
production reproducibility boundary: ambient image/workflow overrides are
masked for the whole run, every item requires an explicit checkpoint, and the
backend is told not to inherit EVAVO_IMAGE_* configuration.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parent

AMBIENT_IMAGE_KEYS = (
    "EVAVO_IMAGE_QUALITY_PROFILE",
    "EVAVO_IMAGE_WIDTH",
    "EVAVO_IMAGE_HEIGHT",
    "EVAVO_IMAGE_STEPS",
    "EVAVO_IMAGE_CFG",
    "EVAVO_IMAGE_SAMPLER",
    "EVAVO_IMAGE_SCHEDULER",
    "EVAVO_IMAGE_DENOISE",
    "EVAVO_IMAGE_UPSCALE_FACTOR",
    "EVAVO_IMAGE_SECOND_STEPS",
    "EVAVO_IMAGE_SECOND_CFG",
    "EVAVO_IMAGE_SECOND_SAMPLER",
    "EVAVO_IMAGE_SECOND_SCHEDULER",
    "EVAVO_IMAGE_SECOND_DENOISE",
    "EVAVO_IMAGE_LATENT_UPSCALE_METHOD",
    "EVAVO_IMAGE_LORA",
    "EVAVO_IMAGE_LORA_MODEL_STRENGTH",
    "EVAVO_IMAGE_LORA_CLIP_STRENGTH",
    "EVAVO_UPGRADE_LEGACY_IMAGE_DEFAULTS",
    "EVAVO_COMFYUI_WORKFLOW",
)


def _engine():
    path = ROOT / "batch-plan.py"
    spec = importlib.util.spec_from_file_location("evavo_batch_plan_engine", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load batch-plan.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextlib.contextmanager
def _frozen_image_environment() -> Iterator[dict[str, str]]:
    previous = {key: os.environ[key] for key in AMBIENT_IMAGE_KEYS if key in os.environ}
    try:
        for key in AMBIENT_IMAGE_KEYS:
            os.environ.pop(key, None)
        yield previous
    finally:
        for key in AMBIENT_IMAGE_KEYS:
            os.environ.pop(key, None)
        os.environ.update(previous)


def _freeze_recipes(validated: dict) -> None:
    missing_checkpoint: list[str] = []
    for entry in validated["items"]:
        options = entry["generation_options"]
        checkpoint = str(options.get("checkpoint", "")).strip()
        if not checkpoint:
            missing_checkpoint.append(entry["id"])
        options["use_environment"] = False
    if missing_checkpoint:
        raise ValueError(
            "production batch plans require an explicit checkpoint in defaults or every item; missing: "
            + ", ".join(missing_checkpoint)
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate or execute a frozen EVAVO production batch plan")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--endpoint", default="", help="Override endpoint in the plan")
    parser.add_argument("--concurrency", type=int, default=None, help="Override plan concurrency (1..8)")
    parser.add_argument("--manifest", default="")
    parser.add_argument("--queue-timeout", type=float, default=30.0)
    parser.add_argument("--allow-prompt-lint-errors", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.queue_timeout <= 0:
        parser.error("--queue-timeout must be greater than zero")

    engine = _engine()
    try:
        plan_path, raw, payload = engine._read_plan(args.plan)
        with _frozen_image_environment() as masked:
            validated = engine.validate_plan(
                payload,
                plan_path=plan_path,
                allow_lint_errors=args.allow_prompt_lint_errors,
                concurrency_override=args.concurrency,
                endpoint_override=args.endpoint,
            )
            _freeze_recipes(validated)
            plan_sha256 = hashlib.sha256(raw).hexdigest()
            public = {
                "ok": True,
                "plan": str(plan_path),
                "plan_sha256": plan_sha256,
                "schema": str(engine.SCHEMA_PATH),
                "environment_policy": {
                    "use_environment": False,
                    "masked_keys_present_before_run": sorted(masked),
                    "explicit_checkpoint_required": True,
                },
                **validated,
            }
            if args.dry_run:
                print(json.dumps(public, indent=2, ensure_ascii=False))
                return 0

            manifest = engine._manifest_path(args.manifest, plan_path)
            code, result = asyncio.run(
                engine.execute(
                    validated,
                    plan_path=plan_path,
                    plan_sha256=plan_sha256,
                    manifest_path=manifest,
                    queue_timeout=args.queue_timeout,
                )
            )
    except (ValueError, RuntimeError, OSError) as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error_code": "FROZEN_BATCH_PLAN_ERROR",
                    "message": str(exc),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 2

    result["environment_policy"] = {
        "use_environment": False,
        "explicit_checkpoint_required": True,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
