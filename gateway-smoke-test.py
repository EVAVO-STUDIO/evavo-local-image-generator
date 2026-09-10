#!/usr/bin/env python3
"""Live end-to-end quality smoke test for the EVAVO native-image HTTP gateway."""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import re
import struct
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Tuple

TASK_RE = re.compile(r"^img_\d+$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def request(url: str, *, method: str = "GET", payload: Dict[str, Any] | None = None, timeout: float = 10.0) -> Tuple[int, bytes, Dict[str, str], float]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json", "User-Agent": "EVAVO-Gateway-Smoke/4"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = response.read()
            status = int(getattr(response, "status", 200))
            response_headers = {k.lower(): v for k, v in response.headers.items()}
    except urllib.error.HTTPError as exc:
        data = exc.read()
        status = exc.code
        response_headers = {k.lower(): v for k, v in exc.headers.items()}
    elapsed = (time.perf_counter() - started) * 1000
    return status, data, response_headers, elapsed


def json_request(url: str, **kwargs: Any) -> Tuple[int, Dict[str, Any], float]:
    status, data, _, elapsed = request(url, **kwargs)
    payload = json.loads(data.decode("utf-8", errors="replace"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected JSON object from {url}")
    return status, payload, elapsed


def png_dimensions(data: bytes) -> tuple[int | None, int | None]:
    if len(data) >= 24 and data.startswith(b"\x89PNG\r\n\x1a\n"):
        return struct.unpack(">II", data[16:24])
    return None, None


def finite_number(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


async def websocket_probe(base: str, task_id: str) -> Dict[str, Any]:
    try:
        import websockets
    except ImportError:
        return {"ok": False, "skipped": True, "reason": "websockets package unavailable"}
    ws_url = base.replace("http://", "ws://").replace("https://", "wss://") + f"/ws/progress/{task_id}"
    started = time.perf_counter()
    try:
        async with websockets.connect(ws_url, open_timeout=5) as socket:
            raw = await asyncio.wait_for(socket.recv(), timeout=5)
            payload = json.loads(raw)
            return {
                "ok": isinstance(payload, dict) and payload.get("task_id") == task_id,
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                "event": payload,
            }
    except Exception as exc:
        return {"ok": False, "latency_ms": round((time.perf_counter() - started) * 1000, 1), "error": str(exc)}


def quality_receipt_ok(
    task: Dict[str, Any],
    *,
    requested_profile: str,
    requested_seed: int,
    requested_vae: str | None,
    frozen: bool,
) -> tuple[bool, list[str]]:
    failures: list[str] = []
    if task.get("quality_profile") != requested_profile:
        failures.append(f"quality_profile={task.get('quality_profile')!r}, expected {requested_profile!r}")
    if task.get("seed") != requested_seed:
        failures.append(f"seed={task.get('seed')!r}, expected {requested_seed}")
    workflow_sha = task.get("workflow_sha256")
    if not isinstance(workflow_sha, str) or SHA256_RE.fullmatch(workflow_sha) is None:
        failures.append("workflow_sha256 is missing or invalid")
    if not isinstance(task.get("workflow_node_count"), int) or task["workflow_node_count"] < 7:
        failures.append("workflow_node_count is missing or unexpectedly small")
    passes = task.get("render_passes")
    if requested_profile == "hero" and passes != 2:
        failures.append(f"render_passes={passes!r}, expected 2 for hero")
    if requested_profile != "hero" and not isinstance(passes, int):
        failures.append("render_passes is missing")
    if not isinstance(task.get("checkpoint"), str) or not task["checkpoint"].strip():
        failures.append("checkpoint is missing")
    if not isinstance(task.get("output_width"), int) or task["output_width"] <= 0:
        failures.append("output_width is missing or invalid")
    if not isinstance(task.get("output_height"), int) or task["output_height"] <= 0:
        failures.append("output_height is missing or invalid")

    expected_environment = not frozen
    if task.get("use_environment") is not expected_environment:
        failures.append(
            f"use_environment={task.get('use_environment')!r}, expected {expected_environment!r}"
        )

    vae = task.get("vae")
    if requested_vae:
        if not isinstance(vae, dict) or vae.get("name") != requested_vae:
            failures.append(f"vae={vae!r}, expected name {requested_vae!r}")
    elif vae not in {None, {}}:
        failures.append(f"vae={vae!r}, expected baked checkpoint VAE")
    return not failures, failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test EVAVO native-image HTTP gateway and its quality receipt")
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--prompt",
        default="EVAVO gateway quality verification: black anodized desk speaker on a matte surface, precise geometry, soft studio light",
    )
    parser.add_argument("--negative", default="warped geometry, duplicate object, text, watermark")
    parser.add_argument("--profile", default="quality")
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--lora", default=None)
    parser.add_argument("--lora-strength", type=float, default=0.7)
    parser.add_argument("--vae", default=None, help="Optional exact live VAELoader inventory name")
    parser.add_argument("--frozen", action="store_true", help="Send use_environment=false and verify the frozen recipe receipt")
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--output", default=".evavo/gateway/smoke-test-result.png")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")
    if not finite_number(args.lora_strength) or not -4 <= args.lora_strength <= 4:
        parser.error("--lora-strength must be finite and between -4 and 4")
    if args.vae is not None and not str(args.vae).strip():
        parser.error("--vae must not be empty")

    base = args.base.rstrip("/")
    report: Dict[str, Any] = {
        "schema_version": 4,
        "base": base,
        "requested_profile": args.profile,
        "requested_seed": args.seed,
        "requested_lora": args.lora,
        "requested_vae": args.vae,
        "frozen_recipe_requested": bool(args.frozen),
        "started_at": time.time(),
        "checks": {},
    }

    try:
        status, health, latency = json_request(base + "/health")
        core_ok = status == 200 and health.get("status") == "healthy" and health.get("gateway") == "ok" and health.get("comfyui") == "ok"
        report["checks"]["health"] = {
            "ok": core_ok,
            "status_code": status,
            "latency_ms": round(latency, 1),
            "response": health,
        }
        if not core_ok:
            raise RuntimeError(f"Gateway/core image health is not ready: {health}")

        status, services, latency = json_request(base + "/services")
        service_shape_ok = (
            status == 200
            and all(isinstance(services.get(kind), dict) for kind in ("image", "video", "audio", "3d"))
            and services["image"].get("ready") is True
        )
        report["checks"]["services"] = {
            "ok": service_shape_ok,
            "status_code": status,
            "latency_ms": round(latency, 1),
            "response": services,
        }

        status, capabilities, latency = json_request(base + "/capabilities")
        image_cap = capabilities.get("image") if isinstance(capabilities.get("image"), dict) else {}
        profiles = image_cap.get("quality_profiles") if isinstance(image_cap.get("quality_profiles"), list) else []
        receipt_fields = image_cap.get("reproducible_receipt") if isinstance(image_cap.get("reproducible_receipt"), list) else []
        required_receipt = {
            "seed",
            "workflow_sha256",
            "workflow_node_count",
            "checkpoint",
            "quality_profile",
            "render_passes",
            "output_width",
            "output_height",
            "lora",
            "vae",
            "use_environment",
        }
        capabilities_ok = (
            status == 200
            and image_cap.get("ready") is True
            and image_cap.get("per_request_quality") is True
            and image_cap.get("frozen_recipe") is True
            and image_cap.get("hero_two_pass") is True
            and image_cap.get("lora") is True
            and image_cap.get("vae_override") is True
            and args.profile in profiles
            and required_receipt.issubset(set(receipt_fields))
            and all(isinstance(capabilities.get(kind), dict) for kind in ("video", "audio", "3d"))
        )
        report["checks"]["capabilities"] = {
            "ok": capabilities_ok,
            "status_code": status,
            "latency_ms": round(latency, 1),
            "response": capabilities,
        }
        if not capabilities_ok:
            raise RuntimeError("Gateway does not advertise the required image-quality/frozen/VAE contract")

        status, openapi, latency = json_request(base + "/openapi.json")
        required_paths = {
            "/health",
            "/services",
            "/capabilities",
            "/generate/image",
            "/generate/video",
            "/generate/audio",
            "/generate/3d",
            "/tasks",
            "/tasks/{task_id}/status",
            "/results/{task_id}",
        }
        paths = set(openapi.get("paths", {}).keys()) if isinstance(openapi.get("paths"), dict) else set()
        report["checks"]["openapi"] = {
            "ok": status == 200 and required_paths.issubset(paths),
            "latency_ms": round(latency, 1),
            "missing_paths": sorted(required_paths - paths),
        }

        image_request: Dict[str, Any] = {
            "prompt": args.prompt,
            "negative_prompt": args.negative,
            "project_name": "gateway_quality_smoke",
            "quality_profile": args.profile,
            "seed": args.seed,
        }
        if args.frozen:
            image_request["use_environment"] = False
        if args.lora:
            image_request.update(
                lora_name=args.lora,
                lora_model_strength=args.lora_strength,
                lora_clip_strength=args.lora_strength,
            )
        if args.vae:
            image_request["vae_name"] = args.vae

        status, queued, latency = json_request(base + "/generate/image", method="POST", payload=image_request)
        task_id = str(queued.get("task_id", ""))
        queue_ok = status == 202 and TASK_RE.fullmatch(task_id) is not None and queued.get("status") == "queued" and queued.get("progress") == 0
        report["checks"]["queue"] = {
            "ok": queue_ok,
            "status_code": status,
            "latency_ms": round(latency, 1),
            "request": image_request,
            "response": queued,
        }
        if not queue_ok:
            raise RuntimeError("Image queue contract failed")

        report["checks"]["websocket"] = asyncio.run(websocket_probe(base, task_id))

        deadline = time.monotonic() + args.timeout
        polls = 0
        latest: Dict[str, Any] = {}
        poll_latencies = []
        receipt_checked = False
        receipt_failures: list[str] = []
        while time.monotonic() < deadline:
            polls += 1
            status, latest, latency = json_request(base + f"/tasks/{task_id}/status")
            poll_latencies.append(latency)
            if latest.get("workflow_sha256"):
                receipt_checked = True
                _, receipt_failures = quality_receipt_ok(
                    latest,
                    requested_profile=args.profile,
                    requested_seed=args.seed,
                    requested_vae=args.vae,
                    frozen=args.frozen,
                )
            if latest.get("status") in {"completed", "failed"}:
                break
            time.sleep(0.5)

        receipt_ok, final_receipt_failures = quality_receipt_ok(
            latest,
            requested_profile=args.profile,
            requested_seed=args.seed,
            requested_vae=args.vae,
            frozen=args.frozen,
        )
        if final_receipt_failures:
            receipt_failures = final_receipt_failures
        lora_ok = True
        if args.lora:
            lora = latest.get("lora") if isinstance(latest.get("lora"), dict) else {}
            lora_ok = (
                lora.get("name") == args.lora
                and finite_number(lora.get("model_strength"))
                and abs(float(lora["model_strength"]) - args.lora_strength) < 1e-9
                and finite_number(lora.get("clip_strength"))
                and abs(float(lora["clip_strength"]) - args.lora_strength) < 1e-9
            )
        elif latest.get("lora") not in {None, {}}:
            lora_ok = False

        task_ok = (
            latest.get("status") == "completed"
            and latest.get("progress") == 100
            and latest.get("result_ready") is True
            and receipt_ok
            and lora_ok
        )
        report["checks"]["task_tracking"] = {
            "ok": task_ok,
            "polls": polls,
            "receipt_seen_before_completion": receipt_checked,
            "receipt_failures": receipt_failures,
            "lora_ok": lora_ok,
            "vae_ok": not any(failure.startswith("vae=") for failure in receipt_failures),
            "frozen_recipe_ok": not any(failure.startswith("use_environment=") for failure in receipt_failures),
            "average_poll_latency_ms": round(sum(poll_latencies) / max(1, len(poll_latencies)), 1),
            "final": latest,
        }
        if latest.get("status") != "completed":
            raise RuntimeError(f"Generation did not complete successfully: {latest}")
        if not receipt_ok:
            raise RuntimeError(f"Gateway quality receipt failed validation: {receipt_failures}")
        if not lora_ok:
            raise RuntimeError("Gateway LoRA receipt does not match the requested LoRA recipe")

        status, data, headers, latency = request(base + f"/results/{task_id}", timeout=60.0)
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        width, height = png_dimensions(data)
        expected_width = latest.get("output_width")
        expected_height = latest.get("output_height")
        dimensions_ok = (
            isinstance(expected_width, int)
            and isinstance(expected_height, int)
            and width == expected_width
            and height == expected_height
        )
        if status == 200 and data:
            output.write_bytes(data)
        result_ok = status == 200 and len(data) > 0 and dimensions_ok
        report["checks"]["result"] = {
            "ok": result_ok,
            "status_code": status,
            "latency_ms": round(latency, 1),
            "bytes": len(data),
            "content_type": headers.get("content-type"),
            "width": width,
            "height": height,
            "expected_width": expected_width,
            "expected_height": expected_height,
            "dimensions_ok": dimensions_ok,
            "output": str(output) if status == 200 and data else None,
        }
        if not result_ok:
            raise RuntimeError(
                f"Gateway result failed artifact/dimension validation: HTTP {status}, actual {width}x{height}, expected {expected_width}x{expected_height}"
            )
    except Exception as exc:
        report["error"] = str(exc)

    checks = report.get("checks", {})
    report["ok"] = (
        bool(checks)
        and all(bool(item.get("ok")) or bool(item.get("skipped")) for item in checks.values() if isinstance(item, dict))
        and "error" not in report
    )
    report["finished_at"] = time.time()
    report["duration_ms"] = round((report["finished_at"] - report["started_at"]) * 1000, 1)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
