#!/usr/bin/env python3
"""Bounded real native-ComfyUI generation proof for workstation setup.

This is the final production readiness gate used by the canonical updater. It
submits the active owner workflow to the real native ComfyUI endpoint, waits for
terminal output, downloads it through /view, and relies on ComfyUIBackend's
atomic image/signature validation before declaring success.

The deterministic EVAVO mock is rejected by ``native_health``; isolated tests
use the native-only simulator contract deliberately.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import time
import uuid
from pathlib import Path
from typing import Any

from evavo_operations import ROOT, TaskTracker
from evavo_local_image_generator.backends import ComfyUIBackend
from evavo_local_image_generator.comfyui_runtime import native_health

DEFAULT_ENDPOINT = (os.getenv("COMFYUI_ENDPOINT") or os.getenv("EVAVO_COMFYUI_ENDPOINT") or "http://127.0.0.1:8188").rstrip("/")
DEFAULT_OUTPUT_DIR = Path(os.getenv("EVAVO_SMOKE_OUTPUT_DIR", str(ROOT / ".evavo" / "setup-smoke"))).expanduser()
DEFAULT_TIMEOUT = 600.0


def _finite_positive(value: Any, *, name: str, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number") from exc
    if not math.isfinite(parsed) or parsed <= 0 or parsed > maximum:
        raise ValueError(f"{name} must be finite, greater than zero and at most {maximum:g}")
    return parsed


def _dimension(value: Any, *, name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if parsed < 64 or parsed > 4096 or parsed % 8:
        raise ValueError(f"{name} must be 64..4096 and divisible by 8")
    return parsed


def _steps(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("steps must be an integer") from exc
    if parsed < 1 or parsed > 50:
        raise ValueError("steps must be between 1 and 50")
    return parsed


def run(
    *,
    endpoint: str,
    prompt: str,
    width: int,
    height: int,
    steps: int,
    cfg_scale: float,
    seed: int,
    timeout: float,
) -> dict[str, Any]:
    endpoint = endpoint.rstrip("/")
    prompt = str(prompt or "").strip()
    if not prompt:
        return {"ok": False, "status": "failed", "error_code": "INVALID_PROMPT", "message": "prompt must be non-empty"}

    started = time.monotonic()
    health = native_health(endpoint)
    if not health:
        return {
            "ok": False,
            "status": "failed",
            "error_code": "NATIVE_COMFYUI_NOT_READY",
            "message": f"native ComfyUI is not ready at {endpoint}",
            "endpoint": endpoint,
        }

    backend = ComfyUIBackend(endpoint)
    output_dir = DEFAULT_OUTPUT_DIR.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    tracker = TaskTracker()
    workflow_path = os.getenv("EVAVO_COMFYUI_WORKFLOW") or None
    checkpoint = os.getenv("EVAVO_COMFYUI_CHECKPOINT") or None
    task_id: str | None = None

    try:
        queued = backend.queue_image(
            prompt,
            project_name="setup-smoke",
            width=width,
            height=height,
            steps=steps,
            cfg_scale=cfg_scale,
            seed=seed,
            checkpoint=checkpoint,
            workflow_path=workflow_path,
        )
        task_id = str(queued["task_id"])
        tracker.add_task(
            task_id,
            prompt,
            "queued",
            project_name="setup-smoke",
            backend_mode="native-comfyui",
            checkpoint=str(queued.get("checkpoint")) if queued.get("checkpoint") else None,
            workflow_path=workflow_path,
            output_dir=str(output_dir),
        )
        downloaded = backend.wait_and_download(task_id, output_dir, timeout=timeout, interval=0.5)
        tracker.update_task(
            task_id,
            "completed",
            backend_mode="native-comfyui",
            output_dir=str(output_dir),
            output_uris=[str(item) for item in downloaded],
        )
    except Exception as exc:
        if task_id:
            try:
                tracker.update_task(
                    task_id,
                    "failed",
                    backend_mode="native-comfyui",
                    output_dir=str(output_dir),
                    error_code="REAL_GENERATION_SMOKE_FAILED",
                    error_message=str(exc),
                )
            except Exception:
                pass
        else:
            failure_id = f"smoke_failed_{uuid.uuid4().hex}"
            try:
                tracker.add_task(
                    failure_id,
                    prompt,
                    "failed",
                    project_name="setup-smoke",
                    backend_mode="native-comfyui",
                    workflow_path=workflow_path,
                    output_dir=str(output_dir),
                    error_code="REAL_GENERATION_SMOKE_FAILED",
                    error_message=str(exc),
                )
            except Exception:
                pass
        return {
            "ok": False,
            "status": "failed",
            "task_id": task_id,
            "error_code": "REAL_GENERATION_SMOKE_FAILED",
            "message": str(exc),
            "endpoint": endpoint,
            "output_dir": str(output_dir),
            "duration_seconds": round(time.monotonic() - started, 3),
        }

    return {
        "ok": True,
        "status": "completed",
        "task_id": task_id,
        "endpoint": endpoint,
        "workflow_path": workflow_path,
        "checkpoint": queued.get("checkpoint"),
        "downloaded_files": downloaded,
        "output_dir": str(output_dir),
        "duration_seconds": round(time.monotonic() - started, 3),
        "proof": "native ComfyUI prompt completed and downloaded image bytes passed EVAVO validation",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one bounded real EVAVO native-ComfyUI generation proof")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--prompt", default="EVAVO native renderer readiness proof, simple neutral geometric composition")
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--height", type=int, default=512)
    parser.add_argument("--steps", type=int, default=2)
    parser.add_argument("--cfg-scale", type=float, default=7.0)
    parser.add_argument("--seed", type=int, default=1871)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        width = _dimension(args.width, name="width")
        height = _dimension(args.height, name="height")
        steps = _steps(args.steps)
        cfg_scale = _finite_positive(args.cfg_scale, name="cfg_scale", maximum=100.0)
        timeout = _finite_positive(args.timeout, name="timeout", maximum=1800.0)
    except ValueError as exc:
        parser.error(str(exc))

    payload = run(
        endpoint=args.endpoint,
        prompt=args.prompt,
        width=width,
        height=height,
        steps=steps,
        cfg_scale=cfg_scale,
        seed=args.seed,
        timeout=timeout,
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
