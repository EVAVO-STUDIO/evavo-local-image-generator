#!/usr/bin/env python3
"""Concurrent batch image queueing for the EVAVO local image generator."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List

from evavo_operations import DEFAULT_ENDPOINT, TaskTracker, now_iso, request_json, validate_health

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


async def preflight(endpoint: str, timeout: float = 5.0) -> Dict[str, Any]:
    """Require the expected EVAVO service before queueing work."""
    payload = await asyncio.to_thread(request_json, f"{endpoint}/system", timeout=timeout)
    return validate_health(payload)


async def queue_generation(
    prompt: str,
    project_name: str,
    endpoint: str,
    semaphore: asyncio.Semaphore,
    timeout: float,
) -> Dict[str, Any]:
    """Queue one prompt through the wrapper without blocking the event loop."""
    async with semaphore:
        payload = json.dumps({"prompt": prompt, "project_name": project_name}, ensure_ascii=False)
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
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            try:
                process.kill()  # type: ignore[possibly-undefined]
                await process.wait()  # type: ignore[possibly-undefined]
            except Exception:
                pass
            return _failure(prompt, project_name, "WRAPPER_TIMEOUT", f"wrapper exceeded {timeout:.1f}s timeout")
        except FileNotFoundError as exc:
            return _failure(prompt, project_name, "WRAPPER_NOT_FOUND", str(exc))
        except OSError as exc:
            return _failure(prompt, project_name, "PROCESS_ERROR", str(exc))

        text = stdout.decode("utf-8", errors="replace").strip()
        err_text = stderr.decode("utf-8", errors="replace").strip()
        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            return _failure(
                prompt,
                project_name,
                "INVALID_WRAPPER_JSON",
                (text or err_text or "wrapper returned no JSON")[:500],
            )
        if not isinstance(result, dict):
            return _failure(prompt, project_name, "INVALID_WRAPPER_RESPONSE", "wrapper JSON root was not an object")
        if process.returncode != 0 or result.get("status") != "queued":
            code = str(result.get("error_code") or f"WRAPPER_EXIT_{process.returncode}")
            message = str(result.get("message") or err_text or "generation was not queued")
            failed = _failure(prompt, project_name, code, message)
            if isinstance(result.get("task_id"), str) and result["task_id"]:
                failed["task_id"] = result["task_id"]
            return failed
        task_id = result.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            return _failure(prompt, project_name, "MISSING_TASK_ID", "wrapper returned queued status without a task_id")
        result.update({"prompt": prompt, "project_name": project_name})
        return result


async def batch_generate(
    prompts: List[str],
    project_name: str,
    endpoint: str,
    concurrency: int,
    timeout: float,
) -> List[Dict[str, Any]]:
    semaphore = asyncio.Semaphore(concurrency)
    tasks = [queue_generation(prompt, project_name, endpoint, semaphore, timeout) for prompt in prompts]
    return await asyncio.gather(*tasks)


def persist_results(results: List[Dict[str, Any]]) -> None:
    tracker = TaskTracker()
    for result in results:
        tracker.add_task(
            str(result["task_id"]),
            str(result.get("prompt", "")),
            str(result.get("status", "unknown")),
            project_name=str(result.get("project_name", "batch_gen")),
            error_code=result.get("error_code"),
            error_message=result.get("message"),
        )


def display_results(results: List[Dict[str, Any]]) -> None:
    print("\n" + "=" * 112)
    print(f"BATCH GENERATION RESULTS ({now_iso()})")
    print("=" * 112)
    print(f"{'#':<4} {'Status':<10} {'Task ID':<38} {'Project':<18} {'Prompt':<34}")
    print("-" * 112)
    for index, result in enumerate(results, 1):
        status = str(result.get("status", "unknown"))[:10]
        task_id = str(result.get("task_id", "N/A"))[:38]
        project = str(result.get("project_name", ""))[:18]
        prompt = str(result.get("prompt", "")).replace("\n", " ")[:34]
        print(f"{index:<4} {status:<10} {task_id:<38} {project:<18} {prompt:<34}")
        if result.get("status") == "failed":
            print(f"     -> {result.get('error_code', 'ERROR')}: {result.get('message', '')}")
    print("=" * 112)


async def async_main(args: argparse.Namespace, prompts: List[str]) -> int:
    endpoint = args.endpoint.rstrip("/")
    if not args.skip_preflight:
        try:
            health = await preflight(endpoint)
            if not args.json:
                print(f"Preflight OK: {health.get('service')} ({health.get('mode', 'unknown')}) at {endpoint}")
        except RuntimeError as exc:
            if args.json:
                print(json.dumps({"ok": False, "status": "failed", "error_code": "PREFLIGHT_FAILED", "message": str(exc)}, ensure_ascii=False))
            else:
                print(f"ERROR: EVAVO service preflight failed: {exc}", file=sys.stderr)
                print("Start it with START-EVAVO-SERVICES.bat, then retry.", file=sys.stderr)
            return 3

    results = await batch_generate(prompts, args.project, endpoint, args.concurrency, args.timeout)
    try:
        persist_results(results)
    except Exception as exc:
        if not args.json:
            print(f"WARNING: generation results were produced but task history could not be saved: {exc}", file=sys.stderr)
        for result in results:
            result["tracking_warning"] = str(exc)

    successful = sum(1 for result in results if result.get("status") == "queued")
    if args.json:
        print(json.dumps({"ok": successful == len(results), "queued": successful, "total": len(results), "results": results}, ensure_ascii=False, indent=2))
    else:
        display_results(results)
        print(f"\n{successful}/{len(results)} tasks queued successfully")
        print("Task history: task_history.json")
    return 0 if successful == len(results) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch image generation for EVAVO")
    parser.add_argument("--prompts", nargs="+", help="Prompts to queue")
    parser.add_argument("--project", default="batch_gen", help="Project name")
    parser.add_argument("--examples", action="store_true", help="Use built-in examples")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="EVAVO service base URL")
    parser.add_argument("--concurrency", type=int, default=4, help="Maximum wrapper processes in flight (default: 4)")
    parser.add_argument("--timeout", type=float, default=30.0, help="Per-request wrapper timeout in seconds")
    parser.add_argument("--skip-preflight", action="store_true", help="Skip service identity/readiness preflight")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()

    if args.concurrency < 1 or args.concurrency > 64:
        parser.error("--concurrency must be between 1 and 64")
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")

    if args.prompts:
        prompts = args.prompts
    elif args.examples or len(sys.argv) == 1:
        prompts = EXAMPLE_PROMPTS
    else:
        parser.error("provide --prompts or --examples")

    return asyncio.run(async_main(args, prompts))


if __name__ == "__main__":
    raise SystemExit(main())
