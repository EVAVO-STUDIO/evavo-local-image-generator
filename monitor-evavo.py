#!/usr/bin/env python3
"""Health monitoring for the EVAVO local image generator."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict

from evavo_operations import DEFAULT_ENDPOINT, SERVICE_NAME, now_iso, request_json, validate_health

ROOT = Path(__file__).resolve().parent
WRAPPER = ROOT / "evavo-wrapper.py"


async def check_comfyui_health(endpoint: str, timeout: float = 5.0) -> Dict[str, Any]:
    started = time.perf_counter()
    try:
        payload = await asyncio.to_thread(request_json, f"{endpoint}/system", timeout=timeout)
        validate_health(payload)
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        return {
            "healthy": True,
            "status": "ready",
            "latency_ms": latency_ms,
            "service": payload.get("service"),
            "protocol_version": payload.get("protocol_version"),
            "mode": payload.get("mode", "unknown"),
        }
    except RuntimeError as exc:
        return {
            "healthy": False,
            "status": "offline",
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "error": str(exc),
        }


async def check_evavo_wrapper(endpoint: str, timeout: float = 10.0) -> Dict[str, Any]:
    started = time.perf_counter()
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            str(WRAPPER),
            "health_check",
            "{}",
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
        return {"healthy": False, "status": "error", "error": "WRAPPER_TIMEOUT"}
    except OSError as exc:
        return {"healthy": False, "status": "error", "error": f"PROCESS_ERROR:{exc}"}

    text = stdout.decode("utf-8", errors="replace").strip()
    err_text = stderr.decode("utf-8", errors="replace").strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {
            "healthy": False,
            "status": "error",
            "error": f"INVALID_WRAPPER_JSON:{(text or err_text)[:300]}",
        }

    healthy = process.returncode == 0 and isinstance(payload, dict) and payload.get("status") == "ready"
    result: Dict[str, Any] = {
        "healthy": healthy,
        "status": "ready" if healthy else "error",
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
    }
    if isinstance(payload, dict):
        result["details"] = payload
    if not healthy:
        result["error"] = str(payload.get("message") if isinstance(payload, dict) else err_text) or f"WRAPPER_EXIT_{process.returncode}"
    return result


async def run_health_check(endpoint: str = DEFAULT_ENDPOINT) -> Dict[str, Any]:
    endpoint = endpoint.rstrip("/")
    comfyui, wrapper = await asyncio.gather(
        check_comfyui_health(endpoint),
        check_evavo_wrapper(endpoint),
    )
    healthy = bool(comfyui.get("healthy") and wrapper.get("healthy"))
    return {
        "healthy": healthy,
        "status": "operational" if healthy else "degraded",
        "service": SERVICE_NAME,
        "endpoint": endpoint,
        "timestamp": now_iso(),
        "components": {
            "comfyui": comfyui,
            "evavo_wrapper": wrapper,
        },
    }


def clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def display_health(health: Dict[str, Any]) -> None:
    components = health["components"]
    comfy = components["comfyui"]
    wrapper = components["evavo_wrapper"]
    print("=" * 68)
    print("EVAVO LOCAL IMAGE GENERATOR - SYSTEM STATUS")
    print("=" * 68)
    print(f"Time:     {health['timestamp']}")
    print(f"Endpoint: {health['endpoint']}")
    print()
    print(f"ComfyUI:  {'OK' if comfy['healthy'] else 'OFFLINE'} ({comfy.get('latency_ms', '?')} ms)")
    if comfy.get("error"):
        print(f"           {comfy['error']}")
    print(f"Wrapper:  {'OK' if wrapper['healthy'] else 'ERROR'} ({wrapper.get('latency_ms', '?')} ms)")
    if wrapper.get("error"):
        print(f"           {wrapper['error']}")
    print()
    print(f"Overall:  {health['status'].upper()}")
    print("=" * 68)


async def monitor_continuous(endpoint: str, interval: float, json_output: bool) -> int:
    try:
        while True:
            health = await run_health_check(endpoint)
            if json_output:
                print(json.dumps(health, ensure_ascii=False), flush=True)
            else:
                clear_screen()
                display_health(health)
                print(f"Next check in {interval:g}s (Ctrl+C to stop)")
            await asyncio.sleep(interval)
    except KeyboardInterrupt:
        if not json_output:
            print("\nMonitoring stopped.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitor EVAVO system health")
    parser.add_argument("--continuous", action="store_true", help="Continuous monitoring")
    parser.add_argument("--interval", type=float, default=10.0, help="Check interval in seconds")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="EVAVO service base URL")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()

    if args.interval < 0.25:
        parser.error("--interval must be at least 0.25 seconds")

    if args.continuous:
        return asyncio.run(monitor_continuous(args.endpoint, args.interval, args.json))

    health = asyncio.run(run_health_check(args.endpoint))
    if args.json:
        print(json.dumps(health, ensure_ascii=False, indent=2))
    else:
        display_health(health)
    return 0 if health["healthy"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
