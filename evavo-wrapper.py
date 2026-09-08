#!/usr/bin/env python3
"""Stable CLI wrapper around the EVAVO local ComfyUI-compatible HTTP service.

Backwards-compatible commands:
  python evavo-wrapper.py generate_image '{"prompt":"...","project_name":"..."}'
  python evavo-wrapper.py health_check '{}'

The wrapper always writes exactly one JSON object to stdout so it can be safely
consumed by automation and agents.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict

from evavo_operations import DEFAULT_ENDPOINT, SERVICE_NAME, now_iso, request_json, validate_health


def error_payload(code: str, message: str) -> Dict[str, Any]:
    return {
        "ok": False,
        "status": "failed",
        "error_code": code,
        "message": message,
        "timestamp": now_iso(),
    }


def parse_payload(raw: str) -> Dict[str, Any]:
    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"payload must be valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("payload JSON root must be an object")
    return payload


def health_check(endpoint: str) -> Dict[str, Any]:
    health = validate_health(request_json(f"{endpoint}/system", timeout=5.0))
    return {
        "ok": True,
        "status": "ready",
        "service": SERVICE_NAME,
        "protocol_version": health["protocol_version"],
        "mode": health.get("mode", "unknown"),
        "endpoint": endpoint,
        "timestamp": now_iso(),
    }


def generate_image(endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    prompt = payload.get("prompt")
    project_name = payload.get("project_name", "batch_gen")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")
    if not isinstance(project_name, str) or not project_name.strip():
        raise ValueError("project_name must be a non-empty string")

    response = request_json(
        f"{endpoint}/api/prompt",
        method="POST",
        payload={"prompt": prompt, "project_name": project_name},
        timeout=30.0,
    )
    task_id = response.get("task_id")
    if response.get("status") != "queued" or not isinstance(task_id, str) or not task_id:
        raise RuntimeError("INVALID_RESPONSE:queue response did not contain a valid queued task_id")
    return {
        "ok": True,
        "status": "queued",
        "task_id": task_id,
        "project_name": response.get("project_name", project_name),
        "endpoint": endpoint,
        "timestamp": now_iso(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="EVAVO local image generator wrapper")
    parser.add_argument("command", choices=["generate_image", "health_check"])
    parser.add_argument("payload", nargs="?", default="{}", help="JSON object payload")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="ComfyUI-compatible endpoint")
    args = parser.parse_args()

    try:
        payload = parse_payload(args.payload)
        if args.command == "health_check":
            result = health_check(args.endpoint.rstrip("/"))
        else:
            result = generate_image(args.endpoint.rstrip("/"), payload)
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
