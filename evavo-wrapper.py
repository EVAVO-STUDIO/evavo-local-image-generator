#!/usr/bin/env python3
"""Stable machine-readable wrapper for EVAVO mock or native ComfyUI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

from evavo_operations import DEFAULT_ENDPOINT, ROOT, SERVICE_NAME, now_iso, request_json, validate_health
from evavo_local_image_generator.backends import ComfyUIBackend

DEFAULT_OUTPUT_DIR = ROOT / ".evavo" / "outputs"


def error_payload(code: str, message: str) -> Dict[str, Any]:
    return {"ok": False, "status": "failed", "error_code": code, "message": message, "timestamp": now_iso()}


def parse_payload(raw: str) -> Dict[str, Any]:
    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"payload must be valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("payload JSON root must be an object")
    return payload


def detect_backend(endpoint: str) -> Dict[str, Any]:
    endpoint = endpoint.rstrip("/")
    try:
        health = validate_health(request_json(f"{endpoint}/system", timeout=2.0))
        return {"kind": "evavo-service", "mode": health.get("mode", "mock"), "endpoint": endpoint, "health": health}
    except RuntimeError as evavo_error:
        try:
            native = ComfyUIBackend(endpoint).health()
            return {"kind": "native-comfyui", "mode": "native-comfyui", "endpoint": endpoint, "health": native}
        except RuntimeError as native_error:
            raise RuntimeError(f"BACKEND_UNAVAILABLE:EVAVO={evavo_error}; ComfyUI={native_error}") from native_error


def health_check(endpoint: str) -> Dict[str, Any]:
    backend = detect_backend(endpoint)
    health = backend["health"]
    return {
        "ok": True,
        "status": "ready",
        "service": SERVICE_NAME,
        "backend": backend["kind"],
        "mode": backend["mode"],
        "endpoint": backend["endpoint"],
        "protocol_version": health.get("protocol_version"),
        "comfyui_version": health.get("comfyui_version"),
        "devices": health.get("devices", []),
        "timestamp": now_iso(),
    }


def _output_dir(payload: Dict[str, Any]) -> Path:
    raw = payload.get("output_dir")
    return Path(raw).expanduser().resolve() if isinstance(raw, str) and raw.strip() else DEFAULT_OUTPUT_DIR.resolve()


def generate_image(endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    prompt = payload.get("prompt")
    project_name = payload.get("project_name", "batch_gen")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")
    if len(prompt) > 100_000:
        raise ValueError("prompt exceeds 100000 characters")
    if not isinstance(project_name, str) or not project_name.strip():
        raise ValueError("project_name must be a non-empty string")

    backend = detect_backend(endpoint)
    if backend["kind"] == "native-comfyui":
        client = ComfyUIBackend(endpoint)
        response = client.queue_image(
            prompt.strip(),
            project_name=project_name.strip(),
            negative_prompt=str(payload.get("negative_prompt", "")),
            width=payload.get("width", 1024),
            height=payload.get("height", 1024),
            steps=payload.get("steps", 24),
            cfg_scale=payload.get("cfg_scale", 7.0),
            seed=payload.get("seed"),
            checkpoint=payload.get("checkpoint"),
            workflow_path=payload.get("workflow_path"),
            quality_profile=payload.get("quality_profile"),
            sampler_name=payload.get("sampler_name"),
            scheduler=payload.get("scheduler"),
            denoise=payload.get("denoise"),
            upscale_factor=payload.get("upscale_factor"),
            second_pass_steps=payload.get("second_pass_steps"),
            second_pass_cfg_scale=payload.get("second_pass_cfg_scale"),
            second_pass_sampler_name=payload.get("second_pass_sampler_name"),
            second_pass_scheduler=payload.get("second_pass_scheduler"),
            second_pass_denoise=payload.get("second_pass_denoise"),
            latent_upscale_method=payload.get("latent_upscale_method"),
        )
        response.update({"ok": True, "endpoint": endpoint, "timestamp": now_iso()})
        if bool(payload.get("wait")):
            timeout = float(payload.get("wait_timeout", 600.0))
            downloaded = client.wait_and_download(response["task_id"], _output_dir(payload), timeout=timeout)
            response.update({"status": "completed", "downloaded_files": downloaded, "output_dir": str(_output_dir(payload)), "timestamp": now_iso()})
        return response

    response = request_json(f"{endpoint}/api/prompt", method="POST", payload={"prompt": prompt.strip(), "project_name": project_name.strip()}, timeout=30.0)
    task_id = response.get("task_id")
    if response.get("status") != "queued" or not isinstance(task_id, str) or not task_id:
        raise RuntimeError("INVALID_RESPONSE:queue response did not contain a valid queued task_id")
    result = {"ok": True, "status": "queued", "task_id": task_id, "project_name": response.get("project_name", project_name), "backend_mode": backend["mode"], "endpoint": endpoint, "timestamp": now_iso()}
    if bool(payload.get("wait")):
        result["wait_note"] = "managed mock queues work but does not render files"
    return result


def task_status(endpoint: str, payload: Dict[str, Any], *, wait: bool = False) -> Dict[str, Any]:
    task_id = payload.get("task_id")
    if not isinstance(task_id, str) or not task_id.strip():
        raise ValueError("task_id must be a non-empty string")
    backend = detect_backend(endpoint)
    if backend["kind"] != "native-comfyui":
        return {"ok": True, "status": "queued", "task_id": task_id, "backend_mode": backend["mode"], "timestamp": now_iso()}

    client = ComfyUIBackend(endpoint)
    if wait:
        timeout = float(payload.get("wait_timeout", payload.get("timeout", 600.0)))
        outputs = client.wait_for_outputs(task_id, timeout=timeout)
    else:
        history = client.history(task_id)
        entry = history.get(task_id)
        outputs = client.outputs(task_id) if isinstance(entry, dict) else []
    completed = bool(outputs)
    result: Dict[str, Any] = {"ok": True, "status": "completed" if completed else "queued", "task_id": task_id, "outputs": outputs, "backend_mode": "native-comfyui", "timestamp": now_iso()}
    if completed and (wait or bool(payload.get("download"))):
        target_dir = _output_dir(payload)
        downloaded = [client.download_output(item, target_dir) for item in outputs]
        result.update({"downloaded_files": downloaded, "output_dir": str(target_dir)})
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="EVAVO local image generator wrapper")
    parser.add_argument("command", choices=["generate_image", "health_check", "task_status", "wait_image"])
    parser.add_argument("payload", nargs="?", default="{}", help="JSON object payload")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="EVAVO or native ComfyUI endpoint")
    args = parser.parse_args()

    try:
        payload = parse_payload(args.payload)
        endpoint = args.endpoint.rstrip("/")
        if args.command == "health_check":
            result = health_check(endpoint)
        elif args.command == "task_status":
            result = task_status(endpoint, payload)
        elif args.command == "wait_image":
            result = task_status(endpoint, payload, wait=True)
        else:
            result = generate_image(endpoint, payload)
    except ValueError as exc:
        print(json.dumps(error_payload("INVALID_ARGUMENT", str(exc)), ensure_ascii=False))
        return 2
    except RuntimeError as exc:
        raw = str(exc)
        code, _, message = raw.partition(":")
        print(json.dumps(error_payload(code or "RUNTIME_ERROR", message or raw), ensure_ascii=False))
        return 3
    except Exception as exc:
        print(json.dumps(error_payload("UNEXPECTED_ERROR", str(exc)), ensure_ascii=False))
        return 1

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
