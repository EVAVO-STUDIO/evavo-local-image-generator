#!/usr/bin/env python3
"""Quality-first batch image generation for EVAVO mock or native ComfyUI."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List

from evavo_operations import DEFAULT_ENDPOINT, TaskTracker, now_iso, request_json, validate_health
from evavo_local_image_generator.backends import ComfyUIBackend

ROOT = Path(__file__).resolve().parent
WRAPPER = ROOT / "evavo-wrapper.py"

EXAMPLE_PROMPTS = [
    "A serene landscape with mountains and a sunset",
    "A futuristic cyberpunk city with neon lights",
    "An underwater scene with coral and tropical fish",
    "A cozy cabin in a snowy forest",
    "An abstract digital art piece with geometric shapes",
]


def _failure(prompt: str, project: str, code: str, message: str) -> Dict[str, Any]:
    return {"ok": False, "status": "failed", "task_id": f"local_failed_{uuid.uuid4().hex}", "prompt": prompt, "project_name": project, "error_code": code, "message": message, "timestamp": now_iso()}


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
) -> Dict[str, Any]:
    async with semaphore:
        request_payload: Dict[str, Any] = {"prompt": prompt, "project_name": project_name}
        if wait:
            request_payload.update({"wait": True, "wait_timeout": wait_timeout})
        if output_dir:
            request_payload["output_dir"] = output_dir
        if workflow_path:
            request_payload["workflow_path"] = workflow_path
        payload = json.dumps(request_payload, ensure_ascii=False)
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
            return _failure(prompt, project_name, "WRAPPER_TIMEOUT", f"wrapper exceeded {process_timeout:.1f}s timeout")
        except FileNotFoundError as exc:
            return _failure(prompt, project_name, "WRAPPER_NOT_FOUND", str(exc))
        except OSError as exc:
            return _failure(prompt, project_name, "PROCESS_ERROR", str(exc))

        text = stdout.decode("utf-8", errors="replace").strip()
        err_text = stderr.decode("utf-8", errors="replace").strip()
        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            return _failure(prompt, project_name, "INVALID_WRAPPER_JSON", (text or err_text or "wrapper returned no JSON")[:500])
        if not isinstance(result, dict):
            return _failure(prompt, project_name, "INVALID_WRAPPER_RESPONSE", "wrapper JSON root was not an object")
        accepted = result.get("status") in {"queued", "completed"}
        if process.returncode != 0 or not accepted:
            code = str(result.get("error_code") or f"WRAPPER_EXIT_{process.returncode}")
            message = str(result.get("message") or err_text or "generation was not accepted")
            failed = _failure(prompt, project_name, code, message)
            if isinstance(result.get("task_id"), str) and result["task_id"]:
                failed["task_id"] = result["task_id"]
            return failed
        task_id = result.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            return _failure(prompt, project_name, "MISSING_TASK_ID", "wrapper returned success without a task_id")
        result.update({"prompt": prompt, "project_name": project_name})
        if workflow_path:
            result["workflow_path"] = workflow_path
        return result


async def batch_generate(
    prompts: List[str],
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
) -> List[Dict[str, Any]]:
    semaphore = asyncio.Semaphore(concurrency)
    return await asyncio.gather(
        *(
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
            )
            for prompt in prompts
        )
    )


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
        )


def display_results(results: List[Dict[str, Any]]) -> None:
    print("\n" + "=" * 120)
    print(f"BATCH GENERATION RESULTS ({now_iso()})")
    print("=" * 120)
    print(f"{'#':<4} {'Status':<10} {'Task ID':<38} {'Project':<18} {'Backend':<16} {'Prompt':<28}")
    print("-" * 120)
    for index, result in enumerate(results, 1):
        status = str(result.get("status", "unknown"))[:10]
        task_id = str(result.get("task_id", "N/A"))[:38]
        project = str(result.get("project_name", ""))[:18]
        backend = str(result.get("backend_mode", ""))[:16]
        prompt = str(result.get("prompt", "")).replace("\n", " ")[:28]
        print(f"{index:<4} {status:<10} {task_id:<38} {project:<18} {backend:<16} {prompt:<28}")
        if result.get("status") == "failed":
            print(f"     -> {result.get('error_code', 'ERROR')}: {result.get('message', '')}")
        downloaded = result.get("downloaded_files")
        if isinstance(downloaded, list):
            for filename in downloaded:
                print(f"     -> output: {filename}")
    print("=" * 120)


async def async_main(args: argparse.Namespace, prompts: List[str]) -> int:
    endpoint = args.endpoint.rstrip("/")
    health: Dict[str, Any] | None = None
    if not args.skip_preflight:
        try:
            health = await preflight(endpoint)
            if not args.json:
                print(f"Preflight OK: {health.get('service')} ({health.get('mode', 'unknown')}) at {endpoint}")
        except RuntimeError as exc:
            if args.json:
                print(json.dumps({"ok": False, "status": "failed", "error_code": "PREFLIGHT_FAILED", "message": str(exc)}, ensure_ascii=False))
            else:
                print(f"ERROR: generation backend preflight failed: {exc}", file=sys.stderr)
                print("Start ComfyUI or run: python evavo.py start", file=sys.stderr)
            return 3

    workflow_preflight_done = False
    if args.workflow and not args.skip_workflow_preflight:
        if health is None:
            try:
                health = await preflight(endpoint)
            except RuntimeError as exc:
                message = f"custom workflow requires a healthy native ComfyUI backend: {exc}"
                if args.json:
                    print(json.dumps({"ok": False, "status": "failed", "error_code": "WORKFLOW_PREFLIGHT_FAILED", "message": message}, ensure_ascii=False))
                else:
                    print(f"ERROR: {message}", file=sys.stderr)
                return 3
        if health.get("mode") != "native-comfyui":
            message = f"custom ComfyUI workflows require native ComfyUI; active backend mode is {health.get('mode', 'unknown')}"
            if args.json:
                print(json.dumps({"ok": False, "status": "failed", "error_code": "CUSTOM_WORKFLOW_REQUIRES_NATIVE", "message": message}, ensure_ascii=False))
            else:
                print(f"ERROR: {message}", file=sys.stderr)
            return 3
        try:
            workflow_check = await preflight_custom_workflow(endpoint, args.workflow, prompts[0])
            workflow_preflight_done = True
            if not args.json:
                classes = ", ".join(workflow_check.get("node_classes", []))
                print(f"Workflow preflight OK: {workflow_check['workflow_path']} ({workflow_check.get('node_count', 0)} nodes; {classes})")
        except (RuntimeError, OSError, ValueError) as exc:
            if args.json:
                print(json.dumps({"ok": False, "status": "failed", "error_code": "WORKFLOW_PREFLIGHT_FAILED", "message": str(exc), "workflow_path": str(Path(args.workflow).expanduser())}, ensure_ascii=False))
            else:
                print(f"ERROR: custom workflow preflight failed before queueing any task: {exc}", file=sys.stderr)
            return 3

    if args.concurrency > 1 and args.wait and not args.json:
        print("NOTE: quality-first EVAVO defaults to concurrency=1. Higher concurrency is explicit and may increase VRAM/offload pressure on a 12 GB GPU.")

    results = await batch_generate(
        prompts,
        args.project,
        endpoint,
        args.concurrency,
        args.timeout,
        wait=args.wait,
        wait_timeout=args.wait_timeout,
        output_dir=args.output_dir,
        workflow_path=args.workflow,
        workflow_preflight_already_done=workflow_preflight_done,
    )
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
        print(json.dumps({"ok": accepted == len(results), "accepted": accepted, "queued": queued, "completed": completed, "total": len(results), "results": results}, ensure_ascii=False, indent=2))
    else:
        display_results(results)
        print(f"\n{accepted}/{len(results)} tasks accepted ({completed} completed, {queued} queued)")
        print("Task history: task_history.json")
    return 0 if accepted == len(results) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch image generation for EVAVO")
    parser.add_argument("--prompts", nargs="+", help="Prompts to generate")
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
    parser.add_argument("--workflow", help="Custom ComfyUI API-format workflow JSON template")
    parser.add_argument("--skip-preflight", action="store_true", help="Skip backend identity/readiness preflight")
    parser.add_argument("--skip-workflow-preflight", action="store_true", help="Skip one-time custom workflow compatibility preflight (child wrappers then use their normal per-prompt behavior)")
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
