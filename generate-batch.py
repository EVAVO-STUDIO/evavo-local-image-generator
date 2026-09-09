#!/usr/bin/env python3
"""Quality-first batch image generation for EVAVO mock or native ComfyUI.

Batch jobs preserve the same quality/profile/LoRA controls as single-image
calls and write an atomic run manifest so the requested recipe and per-task
receipts are durable even when console output is lost.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import sys
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from evavo_operations import DEFAULT_ENDPOINT, TaskTracker, now_iso, request_json, validate_health
from evavo_local_image_generator.backends import ComfyUIBackend
from evavo_local_image_generator.prompt_quality import lint_prompt
from evavo_local_image_generator.quality_profiles import profile_names, resolve_quality_settings

ROOT = Path(__file__).resolve().parent
WRAPPER = ROOT / "evavo-wrapper.py"
BATCH_RUN_DIR = ROOT / ".evavo" / "batch-runs"

EXAMPLE_PROMPTS = [
    "A serene landscape with mountains and a sunset",
    "A futuristic cyberpunk city with neon lights",
    "An underwater scene with coral and tropical fish",
    "A cozy cabin in a snowy forest",
    "An abstract digital art piece with geometric shapes",
]

RECEIPT_FIELDS = (
    "seed",
    "workflow_sha256",
    "workflow_node_count",
    "checkpoint",
    "quality_profile",
    "quality",
    "quality_applied",
    "render_passes",
    "output_width",
    "output_height",
    "lora",
)


def _failure(prompt: str, project: str, code: str, message: str) -> Dict[str, Any]:
    return {
        "ok": False,
        "status": "failed",
        "task_id": f"local_failed_{uuid.uuid4().hex}",
        "prompt": prompt,
        "project_name": project,
        "error_code": code,
        "message": message,
        "timestamp": now_iso(),
    }


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


class BatchRunStore:
    """Small process-local writer for one atomic batch evidence manifest."""

    def __init__(self, path: Path, payload: Dict[str, Any]):
        self.path = path
        self.payload = payload
        self._lock = asyncio.Lock()
        _write_json_atomic(self.path, self.payload)

    async def record(self, index: int, result: Dict[str, Any]) -> None:
        async with self._lock:
            item = self.payload["items"][index]
            item["status"] = str(result.get("status", "unknown"))
            item["task_id"] = result.get("task_id")
            item["result"] = result
            item["updated_at"] = now_iso()
            await asyncio.to_thread(_write_json_atomic, self.path, self.payload)

    async def finish(self, results: List[Dict[str, Any]]) -> None:
        async with self._lock:
            accepted = sum(1 for result in results if result.get("status") in {"queued", "completed"})
            self.payload["finished_at"] = now_iso()
            self.payload["summary"] = {
                "ok": accepted == len(results),
                "accepted": accepted,
                "queued": sum(1 for result in results if result.get("status") == "queued"),
                "completed": sum(1 for result in results if result.get("status") == "completed"),
                "failed": sum(1 for result in results if result.get("status") == "failed"),
                "total": len(results),
            }
            await asyncio.to_thread(_write_json_atomic, self.path, self.payload)


async def preflight(endpoint: str, timeout: float = 5.0) -> Dict[str, Any]:
    try:
        payload = await asyncio.to_thread(request_json, f"{endpoint}/system", timeout=timeout)
        health = validate_health(payload)
        return {"service": health.get("service"), "mode": health.get("mode", "mock")}
    except RuntimeError as evavo_error:
        try:
            native = await asyncio.to_thread(ComfyUIBackend(endpoint).health)
            return {"service": "ComfyUI", "mode": "native-comfyui", **native}
        except RuntimeError as native_error:
            raise RuntimeError(f"BACKEND_UNAVAILABLE:EVAVO={evavo_error}; ComfyUI={native_error}") from native_error


async def preflight_custom_workflow(endpoint: str, workflow_path: str, sample_prompt: str) -> Dict[str, Any]:
    """Render and validate a custom workflow once before a CLI batch queues work."""
    backend = ComfyUIBackend(endpoint)
    path = str(Path(workflow_path).expanduser().resolve())
    workflow = await asyncio.to_thread(
        backend.build_txt2img_workflow,
        sample_prompt,
        negative_prompt="",
        width=1024,
        height=1024,
        steps=4,
        cfg_scale=7.0,
        seed=1,
        workflow_path=path,
        filename_prefix="EVAVO/batch-preflight",
    )
    result = await asyncio.to_thread(backend.preflight_workflow, workflow)
    return {"workflow_path": path, **result}


def _receipt(result: Dict[str, Any]) -> Dict[str, Any]:
    receipt = {key: result[key] for key in RECEIPT_FIELDS if key in result and result[key] is not None}
    prompt_quality = result.get("prompt_quality")
    if isinstance(prompt_quality, dict):
        receipt["prompt_sha256"] = prompt_quality.get("prompt_sha256")
        receipt["prompt_warning_count"] = prompt_quality.get("warning_count")
    return receipt


def _generation_options(args: argparse.Namespace) -> Dict[str, Any]:
    mapping = {
        "quality_profile": args.quality_profile,
        "width": args.width,
        "height": args.height,
        "steps": args.steps,
        "cfg_scale": args.cfg_scale,
        "sampler_name": args.sampler,
        "scheduler": args.scheduler,
        "denoise": args.denoise,
        "upscale_factor": args.upscale_factor,
        "second_pass_steps": args.second_pass_steps,
        "second_pass_cfg_scale": args.second_pass_cfg,
        "second_pass_sampler_name": args.second_pass_sampler,
        "second_pass_scheduler": args.second_pass_scheduler,
        "second_pass_denoise": args.second_pass_denoise,
        "latent_upscale_method": args.latent_upscale_method,
        "lora_name": args.lora,
        "lora_model_strength": args.lora_model_strength,
        "lora_clip_strength": args.lora_clip_strength,
        "checkpoint": args.checkpoint,
    }
    return {key: value for key, value in mapping.items() if value is not None}


def _validate_quality_options(args: argparse.Namespace) -> None:
    try:
        settings = resolve_quality_settings(
            quality_profile=args.quality_profile,
            width=args.width,
            height=args.height,
            steps=args.steps,
            cfg_scale=args.cfg_scale,
            sampler_name=args.sampler,
            scheduler=args.scheduler,
            denoise=args.denoise,
            upscale_factor=args.upscale_factor,
            second_pass_steps=args.second_pass_steps,
            second_pass_cfg_scale=args.second_pass_cfg,
            second_pass_sampler_name=args.second_pass_sampler,
            second_pass_scheduler=args.second_pass_scheduler,
            second_pass_denoise=args.second_pass_denoise,
            latent_upscale_method=args.latent_upscale_method,
        )
    except ValueError as exc:
        raise ValueError(f"invalid quality settings: {exc}") from exc

    if args.workflow and settings.second_pass_enabled:
        raise ValueError("custom workflow batches cannot use automatic two-pass/hero expansion; encode that pass in the custom workflow")
    if args.workflow and (args.lora or os.getenv("EVAVO_IMAGE_LORA")):
        raise ValueError("custom workflow batches cannot use automatic LoRA insertion; encode LoraLoader in the custom workflow")
    for name, value in (
        ("lora_model_strength", args.lora_model_strength),
        ("lora_clip_strength", args.lora_clip_strength),
    ):
        if value is not None and (not math.isfinite(value) or not -4.0 <= value <= 4.0):
            raise ValueError(f"{name} must be finite and between -4 and 4")


def _seed_for_index(base_seed: int | None, strategy: str, index: int) -> int | None:
    if base_seed is None:
        return None
    value = base_seed if strategy == "same" else base_seed + index
    if value > (2**63 - 1):
        raise ValueError("incremented seed exceeds signed 63-bit safety range")
    return value


async def queue_generation(
    prompt: str,
    project_name: str,
    endpoint: str,
    semaphore: asyncio.Semaphore,
    timeout: float,
    *,
    wait: bool = False,
    wait_timeout: float = 600.0,
    output_dir: str | None = None,
    workflow_path: str | None = None,
    workflow_preflight_already_done: bool = False,
    generation_options: Dict[str, Any] | None = None,
    prompt_quality: Dict[str, Any] | None = None,
    manifest_index: int | None = None,
    run_store: BatchRunStore | None = None,
) -> Dict[str, Any]:
    async with semaphore:
        request_payload: Dict[str, Any] = {"prompt": prompt, "project_name": project_name}
        if generation_options:
            request_payload.update(generation_options)
        if wait:
            request_payload.update({"wait": True, "wait_timeout": wait_timeout})
        if output_dir:
            request_payload["output_dir"] = output_dir
        if workflow_path:
            request_payload["workflow_path"] = workflow_path
        payload = json.dumps(request_payload, ensure_ascii=False, allow_nan=False)
        process = None
        process_timeout = max(timeout, wait_timeout + 30.0) if wait else timeout
        child_env = None
        if workflow_path and workflow_preflight_already_done:
            child_env = os.environ.copy()
            child_env["EVAVO_PREFLIGHT_CUSTOM_WORKFLOW"] = "0"
        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                str(WRAPPER),
                "generate_image",
                payload,
                "--endpoint",
                endpoint,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(ROOT),
                env=child_env,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=process_timeout)
        except asyncio.TimeoutError:
            if process is not None:
                try:
                    process.kill()
                    await process.wait()
                except Exception:
                    pass
            result = _failure(prompt, project_name, "WRAPPER_TIMEOUT", f"wrapper exceeded {process_timeout:.1f}s timeout")
            if prompt_quality:
                result["prompt_quality"] = prompt_quality
            if run_store is not None and manifest_index is not None:
                await run_store.record(manifest_index, result)
            return result
        except FileNotFoundError as exc:
            result = _failure(prompt, project_name, "WRAPPER_NOT_FOUND", str(exc))
            if prompt_quality:
                result["prompt_quality"] = prompt_quality
            if run_store is not None and manifest_index is not None:
                await run_store.record(manifest_index, result)
            return result
        except OSError as exc:
            result = _failure(prompt, project_name, "PROCESS_ERROR", str(exc))
            if prompt_quality:
                result["prompt_quality"] = prompt_quality
            if run_store is not None and manifest_index is not None:
                await run_store.record(manifest_index, result)
            return result

        text = stdout.decode("utf-8", errors="replace").strip()
        err_text = stderr.decode("utf-8", errors="replace").strip()
        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            result = _failure(prompt, project_name, "INVALID_WRAPPER_JSON", (text or err_text or "wrapper returned no JSON")[:500])
        if not isinstance(result, dict):
            result = _failure(prompt, project_name, "INVALID_WRAPPER_RESPONSE", "wrapper JSON root was not an object")
        accepted = result.get("status") in {"queued", "completed"}
        if process.returncode != 0 or not accepted:
            code = str(result.get("error_code") or f"WRAPPER_EXIT_{process.returncode}")
            message = str(result.get("message") or err_text or "generation was not accepted")
            failed = _failure(prompt, project_name, code, message)
            if isinstance(result.get("task_id"), str) and result["task_id"]:
                failed["task_id"] = result["task_id"]
            result = failed
        else:
            task_id = result.get("task_id")
            if not isinstance(task_id, str) or not task_id:
                result = _failure(prompt, project_name, "MISSING_TASK_ID", "wrapper returned success without a task_id")
            else:
                result.update({"prompt": prompt, "project_name": project_name})
                if workflow_path:
                    result["workflow_path"] = workflow_path
        if prompt_quality:
            result["prompt_quality"] = prompt_quality
        if run_store is not None and manifest_index is not None:
            await run_store.record(manifest_index, result)
        return result


async def batch_generate(
    prompts: List[str],
    prompt_quality: List[Dict[str, Any]],
    project_name: str,
    endpoint: str,
    concurrency: int,
    timeout: float,
    *,
    wait: bool = False,
    wait_timeout: float = 600.0,
    output_dir: str | None = None,
    workflow_path: str | None = None,
    workflow_preflight_already_done: bool = False,
    generation_options: Dict[str, Any] | None = None,
    base_seed: int | None = None,
    seed_strategy: str = "increment",
    run_store: BatchRunStore | None = None,
) -> List[Dict[str, Any]]:
    semaphore = asyncio.Semaphore(concurrency)
    tasks = []
    for index, prompt in enumerate(prompts):
        options = dict(generation_options or {})
        seed = _seed_for_index(base_seed, seed_strategy, index)
        if seed is not None:
            options["seed"] = seed
        tasks.append(
            queue_generation(
                prompt,
                project_name,
                endpoint,
                semaphore,
                timeout,
                wait=wait,
                wait_timeout=wait_timeout,
                output_dir=output_dir,
                workflow_path=workflow_path,
                workflow_preflight_already_done=workflow_preflight_already_done,
                generation_options=options,
                prompt_quality=prompt_quality[index],
                manifest_index=index,
                run_store=run_store,
            )
        )
    return await asyncio.gather(*tasks)


def persist_results(results: List[Dict[str, Any]]) -> None:
    tracker = TaskTracker()
    for result in results:
        downloaded = result.get("downloaded_files")
        output_uris = [str(item) for item in downloaded] if isinstance(downloaded, list) else None
        tracker.add_task(
            str(result["task_id"]),
            str(result.get("prompt", "")),
            str(result.get("status", "unknown")),
            project_name=str(result.get("project_name", "batch_gen")),
            error_code=result.get("error_code"),
            error_message=result.get("message"),
            backend_mode=result.get("backend_mode"),
            checkpoint=result.get("checkpoint"),
            workflow_path=result.get("workflow_path"),
            output_dir=result.get("output_dir"),
            output_uris=output_uris,
            generation_receipt=_receipt(result),
        )


def display_results(results: List[Dict[str, Any]]) -> None:
    print("\n" + "=" * 132)
    print(f"BATCH GENERATION RESULTS ({now_iso()})")
    print("=" * 132)
    print(f"{'#':<4} {'Status':<10} {'Task ID':<34} {'Profile':<12} {'Seed':<12} {'Project':<16} {'Prompt':<30}")
    print("-" * 132)
    for index, result in enumerate(results, 1):
        status = str(result.get("status", "unknown"))[:10]
        task_id = str(result.get("task_id", "N/A"))[:34]
        profile = str(result.get("quality_profile", ""))[:12]
        seed = str(result.get("seed", ""))[:12]
        project = str(result.get("project_name", ""))[:16]
        prompt = str(result.get("prompt", "")).replace("\n", " ")[:30]
        print(f"{index:<4} {status:<10} {task_id:<34} {profile:<12} {seed:<12} {project:<16} {prompt:<30}")
        if result.get("status") == "failed":
            print(f"     -> {result.get('error_code', 'ERROR')}: {result.get('message', '')}")
        downloaded = result.get("downloaded_files")
        if isinstance(downloaded, list):
            for filename in downloaded:
                print(f"     -> output: {filename}")
    print("=" * 132)


def _manifest_path(value: str | None) -> Path:
    if value:
        candidate = Path(value).expanduser()
        return candidate.resolve()
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    return (BATCH_RUN_DIR / f"{stamp}-{uuid.uuid4().hex[:8]}.json").resolve()


async def async_main(args: argparse.Namespace, prompts: List[str]) -> int:
    endpoint = args.endpoint.rstrip("/")

    linted = [lint_prompt(prompt, args.negative_prompt or "") for prompt in prompts]
    lint_errors = [
        {"index": index, "prompt": prompts[index], "issues": value["issues"]}
        for index, value in enumerate(linted)
        if not value["ok"]
    ]
    if lint_errors and not args.allow_prompt_lint_errors:
        message = "prompt lint failed before queueing any task"
        if args.json:
            print(json.dumps({"ok": False, "status": "failed", "error_code": "PROMPT_LINT_FAILED", "message": message, "prompts": lint_errors}, ensure_ascii=False, indent=2))
        else:
            print(f"ERROR: {message}", file=sys.stderr)
            for item in lint_errors:
                print(f"  prompt {item['index'] + 1}: {item['issues']}", file=sys.stderr)
        return 2
    normalized_prompts = [value["prompt"] for value in linted]

    try:
        _validate_quality_options(args)
        generation_options = _generation_options(args)
        if args.seed is not None and not 0 <= args.seed <= (2**63 - 1):
            raise ValueError("--seed must be between 0 and 2^63-1")
        for index in range(len(normalized_prompts)):
            _seed_for_index(args.seed, args.seed_strategy, index)
    except ValueError as exc:
        if args.json:
            print(json.dumps({"ok": False, "status": "failed", "error_code": "INVALID_QUALITY_OPTIONS", "message": str(exc)}, ensure_ascii=False))
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    manifest_path = _manifest_path(args.manifest)
    plan_items = []
    for index, prompt in enumerate(normalized_prompts):
        options = dict(generation_options)
        planned_seed = _seed_for_index(args.seed, args.seed_strategy, index)
        if planned_seed is not None:
            options["seed"] = planned_seed
        plan_items.append(
            {
                "index": index,
                "prompt": prompt,
                "prompt_sha256": linted[index]["prompt_sha256"],
                "prompt_warnings": linted[index]["issues"],
                "generation_options": options,
                "status": "pending",
                "task_id": None,
                "result": None,
            }
        )
    run_store = BatchRunStore(
        manifest_path,
        {
            "schema_version": 1,
            "batch_id": f"batch-{uuid.uuid4().hex}",
            "started_at": now_iso(),
            "endpoint": endpoint,
            "project_name": args.project,
            "concurrency": args.concurrency,
            "wait": bool(args.wait),
            "wait_timeout": args.wait_timeout,
            "workflow_path": str(Path(args.workflow).expanduser().resolve()) if args.workflow else None,
            "seed_strategy": args.seed_strategy if args.seed is not None else None,
            "base_seed": args.seed,
            "generation_options": generation_options,
            "items": plan_items,
        },
    )

    health: Dict[str, Any] | None = None
    if not args.skip_preflight:
        try:
            health = await preflight(endpoint)
            run_store.payload["preflight"] = health
            await asyncio.to_thread(_write_json_atomic, run_store.path, run_store.payload)
            if not args.json:
                print(f"Preflight OK: {health.get('service')} ({health.get('mode', 'unknown')}) at {endpoint}")
        except RuntimeError as exc:
            run_store.payload["preflight"] = {"ok": False, "error": str(exc)}
            run_store.payload["finished_at"] = now_iso()
            await asyncio.to_thread(_write_json_atomic, run_store.path, run_store.payload)
            if args.json:
                print(json.dumps({"ok": False, "status": "failed", "error_code": "PREFLIGHT_FAILED", "message": str(exc), "manifest": str(manifest_path)}, ensure_ascii=False))
            else:
                print(f"ERROR: generation backend preflight failed: {exc}", file=sys.stderr)
                print("Start ComfyUI or run: python evavo.py start", file=sys.stderr)
                print(f"Batch manifest: {manifest_path}", file=sys.stderr)
            return 3

    workflow_preflight_done = False
    if args.workflow and not args.skip_workflow_preflight:
        if health is None:
            try:
                health = await preflight(endpoint)
            except RuntimeError as exc:
                message = f"custom workflow requires a healthy native ComfyUI backend: {exc}"
                if args.json:
                    print(json.dumps({"ok": False, "status": "failed", "error_code": "WORKFLOW_PREFLIGHT_FAILED", "message": message, "manifest": str(manifest_path)}, ensure_ascii=False))
                else:
                    print(f"ERROR: {message}", file=sys.stderr)
                return 3
        if health.get("mode") != "native-comfyui":
            message = f"custom ComfyUI workflows require native ComfyUI; active backend mode is {health.get('mode', 'unknown')}"
            if args.json:
                print(json.dumps({"ok": False, "status": "failed", "error_code": "CUSTOM_WORKFLOW_REQUIRES_NATIVE", "message": message, "manifest": str(manifest_path)}, ensure_ascii=False))
            else:
                print(f"ERROR: {message}", file=sys.stderr)
            return 3
        try:
            workflow_check = await preflight_custom_workflow(endpoint, args.workflow, normalized_prompts[0])
            workflow_preflight_done = True
            run_store.payload["workflow_preflight"] = workflow_check
            await asyncio.to_thread(_write_json_atomic, run_store.path, run_store.payload)
            if not args.json:
                classes = ", ".join(workflow_check.get("node_classes", []))
                print(f"Workflow preflight OK: {workflow_check['workflow_path']} ({workflow_check.get('node_count', 0)} nodes; {classes})")
        except (RuntimeError, OSError, ValueError) as exc:
            if args.json:
                print(json.dumps({"ok": False, "status": "failed", "error_code": "WORKFLOW_PREFLIGHT_FAILED", "message": str(exc), "workflow_path": str(Path(args.workflow).expanduser()), "manifest": str(manifest_path)}, ensure_ascii=False))
            else:
                print(f"ERROR: custom workflow preflight failed before queueing any task: {exc}", file=sys.stderr)
            return 3

    if args.concurrency > 1 and args.wait and not args.json:
        print("NOTE: quality-first EVAVO defaults to concurrency=1. Higher concurrency is explicit and may increase VRAM/offload pressure on a 12 GB GPU.")

    results = await batch_generate(
        normalized_prompts,
        linted,
        args.project,
        endpoint,
        args.concurrency,
        args.timeout,
        wait=args.wait,
        wait_timeout=args.wait_timeout,
        output_dir=args.output_dir,
        workflow_path=args.workflow,
        workflow_preflight_already_done=workflow_preflight_done,
        generation_options=generation_options,
        base_seed=args.seed,
        seed_strategy=args.seed_strategy,
        run_store=run_store,
    )
    await run_store.finish(results)
    try:
        persist_results(results)
    except Exception as exc:
        if not args.json:
            print(f"WARNING: generation results were produced but task history could not be saved: {exc}", file=sys.stderr)
        for result in results:
            result["tracking_warning"] = str(exc)

    accepted = sum(1 for result in results if result.get("status") in {"queued", "completed"})
    queued = sum(1 for result in results if result.get("status") == "queued")
    completed = sum(1 for result in results if result.get("status") == "completed")
    if args.json:
        print(json.dumps({"ok": accepted == len(results), "accepted": accepted, "queued": queued, "completed": completed, "total": len(results), "manifest": str(manifest_path), "results": results}, ensure_ascii=False, indent=2))
    else:
        display_results(results)
        print(f"\n{accepted}/{len(results)} tasks accepted ({completed} completed, {queued} queued)")
        print(f"Batch manifest: {manifest_path}")
        print("Task history: task_history.json")
    return 0 if accepted == len(results) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch image generation for EVAVO")
    parser.add_argument("--prompts", nargs="+", help="Prompts to generate")
    parser.add_argument("--negative-prompt", default="", help="Negative prompt applied to every batch item")
    parser.add_argument("--project", default="batch_gen", help="Project name")
    parser.add_argument("--examples", action="store_true", help="Use built-in examples")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="EVAVO or native ComfyUI base URL")
    parser.add_argument(
        "--concurrency",
        type=int,
        default=int(os.getenv("EVAVO_BATCH_CONCURRENCY", "1")),
        help="Maximum wrapper processes in flight (quality-first default: 1; override only after VRAM benchmarking)",
    )
    parser.add_argument("--timeout", type=float, default=30.0, help="Queue request timeout in seconds")
    parser.add_argument("--wait", action="store_true", help="Wait for native ComfyUI outputs and download them")
    parser.add_argument("--wait-timeout", type=float, default=600.0, help="Maximum render wait per image in seconds")
    parser.add_argument("--output-dir", help="Directory for downloaded native ComfyUI outputs")
    parser.add_argument("--manifest", help="Optional batch manifest path; defaults under .evavo/batch-runs")
    parser.add_argument("--workflow", help="Custom ComfyUI API-format workflow JSON template")
    parser.add_argument("--skip-preflight", action="store_true", help="Skip backend identity/readiness preflight")
    parser.add_argument("--skip-workflow-preflight", action="store_true", help="Skip one-time custom workflow compatibility preflight")
    parser.add_argument("--allow-prompt-lint-errors", action="store_true", help="Queue prompts even when the conservative structural linter finds a contradiction")

    parser.add_argument("--quality-profile", choices=[*profile_names(), "custom"], help="Image quality profile, e.g. quality or hero")
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--steps", type=int)
    parser.add_argument("--cfg-scale", type=float)
    parser.add_argument("--sampler")
    parser.add_argument("--scheduler")
    parser.add_argument("--denoise", type=float)
    parser.add_argument("--upscale-factor", type=float)
    parser.add_argument("--second-pass-steps", type=int)
    parser.add_argument("--second-pass-cfg", type=float)
    parser.add_argument("--second-pass-sampler")
    parser.add_argument("--second-pass-scheduler")
    parser.add_argument("--second-pass-denoise", type=float)
    parser.add_argument("--latent-upscale-method")
    parser.add_argument("--checkpoint")
    parser.add_argument("--lora")
    parser.add_argument("--lora-model-strength", type=float)
    parser.add_argument("--lora-clip-strength", type=float)
    parser.add_argument("--seed", type=int, help="Base deterministic seed. Omit for a random seed per render.")
    parser.add_argument("--seed-strategy", choices=["same", "increment"], default="increment", help="When --seed is set, reuse it or increment once per prompt")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()

    if args.concurrency < 1 or args.concurrency > 64:
        parser.error("--concurrency must be between 1 and 64")
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")
    if args.wait_timeout <= 0:
        parser.error("--wait-timeout must be greater than zero")
    if args.prompts:
        prompts = args.prompts
    elif args.examples or len(sys.argv) == 1:
        prompts = EXAMPLE_PROMPTS
    else:
        parser.error("provide --prompts or --examples")
    return asyncio.run(async_main(args, prompts))


if __name__ == "__main__":
    raise SystemExit(main())
