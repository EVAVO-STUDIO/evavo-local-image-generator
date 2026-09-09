#!/usr/bin/env python3
"""Execute a versioned EVAVO image batch plan with per-item quality recipes.

The plan runner is quality-first and fail-closed: the whole plan is validated,
prompts are compiled/linted, custom workflows are preflighted, and output paths
are confined before any GPU task is queued. Its manifest remains compatible
with batch-resume.py.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import math
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from evavo_operations import DEFAULT_ENDPOINT, now_iso
from evavo_local_image_generator.prompt_quality import compile_prompt, lint_prompt
from evavo_local_image_generator.quality_profiles import profile_names, resolve_quality_settings

ROOT = Path(__file__).resolve().parent
SCHEMA_PATH = ROOT / "config" / "batch-plan-v1.schema.json"
DEFAULT_OUTPUT_ROOT = ROOT / ".evavo" / "batch-plan-outputs"
DEFAULT_MANIFEST_ROOT = ROOT / ".evavo" / "batch-runs"
MAX_ITEMS = 1000
MAX_CONCURRENCY = 8
MAX_WAIT_TIMEOUT = 86400.0

OPTION_KEYS = {
    "negative_prompt",
    "quality_profile",
    "width",
    "height",
    "steps",
    "cfg_scale",
    "sampler_name",
    "scheduler",
    "denoise",
    "upscale_factor",
    "second_pass_steps",
    "second_pass_cfg_scale",
    "second_pass_sampler_name",
    "second_pass_scheduler",
    "second_pass_denoise",
    "latent_upscale_method",
    "checkpoint",
    "lora_name",
    "lora_model_strength",
    "lora_clip_strength",
    "seed",
    "workflow_path",
}


def _batch_module():
    path = ROOT / "generate-batch.py"
    spec = importlib.util.spec_from_file_location("evavo_batch_plan_source", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load generate-batch.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_plan(path_value: str | Path) -> tuple[Path, bytes, Dict[str, Any]]:
    path = Path(path_value).expanduser().resolve()
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read batch plan {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("batch plan root must be a JSON object")
    return path, raw, payload


def _finite(value: Any, name: str, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number") from exc
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise ValueError(f"{name} must be finite and between {minimum:g} and {maximum:g}")
    return number


def _integer(value: Any, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if number != value and not isinstance(value, str):
        raise ValueError(f"{name} must be an integer")
    if not minimum <= number <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return number


def _options(value: Any, *, label: str) -> Dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    unknown = sorted(set(value) - OPTION_KEYS)
    if unknown:
        raise ValueError(f"{label} contains unsupported option(s): {', '.join(unknown)}")
    options = dict(value)

    if "quality_profile" in options:
        name = str(options["quality_profile"]).strip()
        if name not in {*profile_names(), "custom"}:
            raise ValueError(f"{label}.quality_profile is unknown: {name}")
        options["quality_profile"] = name
    for key in ("width", "height"):
        if key in options:
            options[key] = _integer(options[key], f"{label}.{key}", 64, 4096)
    if "steps" in options:
        options["steps"] = _integer(options["steps"], f"{label}.steps", 1, 200)
    if "second_pass_steps" in options:
        options["second_pass_steps"] = _integer(options["second_pass_steps"], f"{label}.second_pass_steps", 0, 100)
    if "seed" in options:
        options["seed"] = _integer(options["seed"], f"{label}.seed", 0, (2**63) - 1)
    for key, minimum, maximum in (
        ("cfg_scale", 0.0, 100.0),
        ("denoise", 0.0, 1.0),
        ("upscale_factor", 1.0, 4.0),
        ("second_pass_cfg_scale", 0.0, 100.0),
        ("second_pass_denoise", 0.0, 1.0),
        ("lora_model_strength", -4.0, 4.0),
        ("lora_clip_strength", -4.0, 4.0),
    ):
        if key in options:
            options[key] = _finite(options[key], f"{label}.{key}", minimum, maximum)
    for key in (
        "negative_prompt",
        "sampler_name",
        "scheduler",
        "second_pass_sampler_name",
        "second_pass_scheduler",
        "latent_upscale_method",
        "checkpoint",
        "lora_name",
        "workflow_path",
    ):
        if key in options:
            text = str(options[key]).strip()
            if not text and key != "negative_prompt":
                raise ValueError(f"{label}.{key} must not be empty")
            options[key] = text
    return options


def _validate_quality_recipe(options: Dict[str, Any], *, label: str) -> None:
    try:
        settings = resolve_quality_settings(
            quality_profile=options.get("quality_profile"),
            width=options.get("width"),
            height=options.get("height"),
            steps=options.get("steps"),
            cfg_scale=options.get("cfg_scale"),
            sampler_name=options.get("sampler_name"),
            scheduler=options.get("scheduler"),
            denoise=options.get("denoise"),
            upscale_factor=options.get("upscale_factor"),
            second_pass_steps=options.get("second_pass_steps"),
            second_pass_cfg_scale=options.get("second_pass_cfg_scale"),
            second_pass_sampler_name=options.get("second_pass_sampler_name"),
            second_pass_scheduler=options.get("second_pass_scheduler"),
            second_pass_denoise=options.get("second_pass_denoise"),
            latent_upscale_method=options.get("latent_upscale_method"),
        )
    except ValueError as exc:
        raise ValueError(f"{label}: invalid quality recipe: {exc}") from exc

    workflow = options.get("workflow_path")
    if workflow and settings.second_pass_enabled:
        raise ValueError(f"{label}: custom workflows cannot use automatic hero/two-pass expansion")
    if workflow and options.get("lora_name"):
        raise ValueError(f"{label}: custom workflows cannot use automatic LoRA insertion")


def _confined_output(root: Path, subdir: str) -> Path:
    relative = Path(str(subdir).strip())
    if not str(relative) or relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"unsafe output_subdir: {subdir!r}")
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"output_subdir escapes output root: {subdir!r}") from exc
    return candidate


def _resolve_workflow(plan_dir: Path, value: str) -> str:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = plan_dir / candidate
    resolved = candidate.resolve()
    if not resolved.is_file() or resolved.is_symlink():
        raise ValueError(f"custom workflow is missing or unsafe: {resolved}")
    return str(resolved)


def _compile_item(
    item: Dict[str, Any],
    *,
    index: int,
    defaults: Dict[str, Any],
    plan_dir: Path,
    allow_lint_errors: bool,
) -> Dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError(f"items[{index}] must be an object")
    allowed = {"id", "prompt", "prompt_spec", "options", "output_subdir"}
    unknown = sorted(set(item) - allowed)
    if unknown:
        raise ValueError(f"items[{index}] contains unsupported field(s): {', '.join(unknown)}")

    item_id = str(item.get("id", "")).strip()
    if not item_id or len(item_id) > 128 or not item_id[0].isalnum() or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for ch in item_id):
        raise ValueError(f"items[{index}].id must match ^[A-Za-z0-9][A-Za-z0-9._-]*$")
    has_prompt = isinstance(item.get("prompt"), str) and bool(str(item.get("prompt")).strip())
    has_spec = isinstance(item.get("prompt_spec"), dict)
    if has_prompt == has_spec:
        raise ValueError(f"items[{index}] must contain exactly one of prompt or prompt_spec")

    item_options = _options(item.get("options"), label=f"items[{index}].options")
    merged = {**defaults, **item_options}
    if "workflow_path" in merged:
        merged["workflow_path"] = _resolve_workflow(plan_dir, merged["workflow_path"])

    if has_spec:
        compiled = compile_prompt(item["prompt_spec"])
        compiled_negative = compiled["negative_prompt"]
        if compiled_negative and "negative_prompt" in item_options:
            raise ValueError(
                f"items[{index}] defines negative direction in both prompt_spec and options.negative_prompt"
            )
        if compiled_negative and "negative_prompt" not in merged:
            merged["negative_prompt"] = compiled_negative
        prompt = compiled["prompt"]
        lint = lint_prompt(prompt, str(merged.get("negative_prompt", "")))
        source = "prompt_spec"
    else:
        prompt = str(item["prompt"]).strip()
        lint = lint_prompt(prompt, str(merged.get("negative_prompt", "")))
        source = "prompt"

    if not lint["ok"] and not allow_lint_errors:
        raise ValueError(f"items[{index}] prompt lint failed: {lint['issues']}")
    prompt = lint["prompt"]
    merged["negative_prompt"] = lint["negative_prompt"]
    _validate_quality_recipe(merged, label=f"items[{index}]")

    return {
        "id": item_id,
        "prompt": prompt,
        "prompt_source": source,
        "prompt_quality": lint,
        "generation_options": merged,
        "output_subdir": str(item.get("output_subdir") or item_id),
    }


def validate_plan(
    payload: Dict[str, Any],
    *,
    plan_path: Path,
    allow_lint_errors: bool = False,
    concurrency_override: int | None = None,
    endpoint_override: str = "",
) -> Dict[str, Any]:
    allowed_root = {
        "schema_version", "project", "endpoint", "concurrency", "wait",
        "wait_timeout", "output_dir", "defaults", "items",
    }
    unknown = sorted(set(payload) - allowed_root)
    if unknown:
        raise ValueError("batch plan contains unsupported root field(s): " + ", ".join(unknown))
    if payload.get("schema_version") != 1:
        raise ValueError("batch plan schema_version must be 1")
    project = str(payload.get("project", "")).strip()
    if not project or len(project) > 128:
        raise ValueError("project must be 1..128 characters")
    items = payload.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_ITEMS:
        raise ValueError(f"items must contain between 1 and {MAX_ITEMS} entries")

    default_options = _options(payload.get("defaults"), label="defaults")
    if "workflow_path" in default_options:
        default_options["workflow_path"] = _resolve_workflow(plan_path.parent, default_options["workflow_path"])
    _validate_quality_recipe(default_options, label="defaults")

    concurrency_raw = concurrency_override if concurrency_override is not None else payload.get("concurrency", 1)
    concurrency = _integer(concurrency_raw, "concurrency", 1, MAX_CONCURRENCY)
    wait = payload.get("wait", True)
    if not isinstance(wait, bool):
        raise ValueError("wait must be true or false")
    wait_timeout = _finite(payload.get("wait_timeout", 900.0), "wait_timeout", 0.001, MAX_WAIT_TIMEOUT)
    endpoint = str(endpoint_override or payload.get("endpoint") or DEFAULT_ENDPOINT).strip().rstrip("/")
    if not endpoint:
        raise ValueError("endpoint must not be empty")

    output_value = payload.get("output_dir")
    if output_value:
        output_root = Path(str(output_value)).expanduser()
        if not output_root.is_absolute():
            output_root = plan_path.parent / output_root
        output_root = output_root.resolve()
    else:
        stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
        output_root = (DEFAULT_OUTPUT_ROOT / f"{stamp}-{uuid.uuid4().hex[:8]}").resolve()

    compiled: list[Dict[str, Any]] = []
    ids: set[str] = set()
    for index, item in enumerate(items):
        entry = _compile_item(
            item,
            index=index,
            defaults=default_options,
            plan_dir=plan_path.parent,
            allow_lint_errors=allow_lint_errors,
        )
        if entry["id"] in ids:
            raise ValueError(f"duplicate item id: {entry['id']}")
        ids.add(entry["id"])
        entry["output_dir"] = str(_confined_output(output_root, entry["output_subdir"]))
        compiled.append(entry)

    return {
        "project": project,
        "endpoint": endpoint,
        "concurrency": concurrency,
        "wait": wait,
        "wait_timeout": wait_timeout,
        "output_root": str(output_root),
        "defaults": default_options,
        "items": compiled,
    }


def _manifest_path(value: str, plan_path: Path) -> Path:
    if value:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = plan_path.parent / path
        return path.resolve()
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    return (DEFAULT_MANIFEST_ROOT / f"{stamp}-plan-{uuid.uuid4().hex[:8]}.json").resolve()


async def execute(
    validated: Dict[str, Any],
    *,
    plan_path: Path,
    plan_sha256: str,
    manifest_path: Path,
    queue_timeout: float,
) -> tuple[int, Dict[str, Any]]:
    batch = _batch_module()
    try:
        health = await batch.preflight(validated["endpoint"])
    except RuntimeError as exc:
        result = {"ok": False, "error_code": "PREFLIGHT_FAILED", "message": str(exc)}
        return 3, result

    workflow_checks: Dict[str, Any] = {}
    for entry in validated["items"]:
        workflow = entry["generation_options"].get("workflow_path")
        if not workflow or workflow in workflow_checks:
            continue
        if health.get("mode") != "native-comfyui":
            return 3, {
                "ok": False,
                "error_code": "CUSTOM_WORKFLOW_REQUIRES_NATIVE",
                "message": "custom workflow plan items require native ComfyUI",
            }
        try:
            workflow_checks[workflow] = await batch.preflight_custom_workflow(
                validated["endpoint"], workflow, entry["prompt"]
            )
        except Exception as exc:
            return 3, {
                "ok": False,
                "error_code": "WORKFLOW_PREFLIGHT_FAILED",
                "workflow_path": workflow,
                "message": str(exc),
            }

    manifest_items = []
    for index, entry in enumerate(validated["items"]):
        manifest_items.append(
            {
                "index": index,
                "id": entry["id"],
                "prompt": entry["prompt"],
                "prompt_source": entry["prompt_source"],
                "prompt_sha256": entry["prompt_quality"]["prompt_sha256"],
                "prompt_warnings": entry["prompt_quality"]["issues"],
                "generation_options": entry["generation_options"],
                "output_dir": entry["output_dir"],
                "status": "pending",
                "task_id": None,
                "result": None,
            }
        )

    store = batch.BatchRunStore(
        manifest_path,
        {
            "schema_version": 1,
            "batch_id": f"batch-plan-{uuid.uuid4().hex}",
            "batch_plan": {
                "source": str(plan_path),
                "sha256": plan_sha256,
                "schema": str(SCHEMA_PATH),
                "schema_version": 1,
            },
            "started_at": now_iso(),
            "endpoint": validated["endpoint"],
            "project_name": validated["project"],
            "concurrency": validated["concurrency"],
            "wait": validated["wait"],
            "wait_timeout": validated["wait_timeout"],
            "output_root": validated["output_root"],
            "workflow_preflight": workflow_checks,
            "items": manifest_items,
        },
    )

    semaphore = asyncio.Semaphore(validated["concurrency"])
    tasks = []
    for index, entry in enumerate(validated["items"]):
        options = dict(entry["generation_options"])
        workflow = options.pop("workflow_path", None)
        tasks.append(
            batch.queue_generation(
                entry["prompt"],
                validated["project"],
                validated["endpoint"],
                semaphore,
                queue_timeout,
                wait=validated["wait"],
                wait_timeout=validated["wait_timeout"],
                output_dir=entry["output_dir"],
                workflow_path=workflow,
                workflow_preflight_already_done=bool(workflow and workflow in workflow_checks),
                generation_options=options,
                prompt_quality=entry["prompt_quality"],
                manifest_index=index,
                run_store=store,
            )
        )
    results = await asyncio.gather(*tasks)
    await store.finish(results)
    try:
        batch.persist_results(results)
    except Exception as exc:
        store.payload["tracking_warning"] = str(exc)
        await asyncio.to_thread(batch._write_json_atomic, store.path, store.payload)

    accepted = sum(result.get("status") in {"queued", "completed"} for result in results)
    summary = {
        "ok": accepted == len(results),
        "accepted": accepted,
        "completed": sum(result.get("status") == "completed" for result in results),
        "queued": sum(result.get("status") == "queued" for result in results),
        "failed": sum(result.get("status") == "failed" for result in results),
        "total": len(results),
        "manifest": str(manifest_path),
        "output_root": validated["output_root"],
        "results": results,
    }
    return (0 if summary["ok"] else 1), summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate or execute an EVAVO image batch plan")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--endpoint", default="", help="Override endpoint in the plan")
    parser.add_argument("--concurrency", type=int, default=None, help="Override plan concurrency (1..8)")
    parser.add_argument("--manifest", default="")
    parser.add_argument("--queue-timeout", type=float, default=30.0)
    parser.add_argument("--allow-prompt-lint-errors", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Validate and print the resolved plan without queueing")
    args = parser.parse_args()
    if args.queue_timeout <= 0:
        parser.error("--queue-timeout must be greater than zero")

    try:
        plan_path, raw, payload = _read_plan(args.plan)
        validated = validate_plan(
            payload,
            plan_path=plan_path,
            allow_lint_errors=args.allow_prompt_lint_errors,
            concurrency_override=args.concurrency,
            endpoint_override=args.endpoint,
        )
    except ValueError as exc:
        print(json.dumps({"ok": False, "error_code": "INVALID_BATCH_PLAN", "message": str(exc)}, indent=2, ensure_ascii=False))
        return 2

    plan_sha256 = hashlib.sha256(raw).hexdigest()
    public_plan = {
        "ok": True,
        "plan": str(plan_path),
        "plan_sha256": plan_sha256,
        "schema": str(SCHEMA_PATH),
        **validated,
    }
    if args.dry_run:
        print(json.dumps(public_plan, indent=2, ensure_ascii=False))
        return 0

    manifest = _manifest_path(args.manifest, plan_path)
    try:
        code, result = asyncio.run(
            execute(
                validated,
                plan_path=plan_path,
                plan_sha256=plan_sha256,
                manifest_path=manifest,
                queue_timeout=args.queue_timeout,
            )
        )
    except (RuntimeError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error_code": "BATCH_PLAN_EXECUTION_ERROR", "message": str(exc), "manifest": str(manifest)}, indent=2, ensure_ascii=False))
        return 3
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
