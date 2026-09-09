"""Compatibility health helper for the current EVAVO native-ComfyUI runtime.

This module is intentionally read-only. It no longer probes unrelated Ollama or
Kokoro services and it does not treat the deterministic EVAVO mock as a real
renderer.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Dict

from evavo_local_image_generator.comfyui_runtime import native_health


class HealthChecker:
    """Check whether the configured endpoint is a real native ComfyUI renderer."""

    @staticmethod
    def endpoint() -> str:
        return (
            os.getenv("EVAVO_COMFYUI_ENDPOINT")
            or os.getenv("COMFYUI_ENDPOINT")
            or "http://127.0.0.1:8188"
        ).rstrip("/")

    @classmethod
    async def check_backend(cls) -> Dict[str, Any]:
        endpoint = cls.endpoint()
        health = await asyncio.to_thread(native_health, endpoint)
        if health:
            return {"healthy": True, "endpoint": endpoint, **health}
        return {
            "healthy": False,
            "status": "offline_or_not_native",
            "mode": "native-comfyui",
            "endpoint": endpoint,
        }

    @classmethod
    async def check_all(cls) -> Dict[str, bool]:
        """Backward-compatible boolean summary for older callers."""
        health = await cls.check_backend()
        return {"native_comfyui": bool(health.get("healthy"))}

    @classmethod
    def run_sync(cls) -> Dict[str, bool]:
        return asyncio.run(cls.check_all())


def print_health_report(json_output: bool = False) -> bool:
    health = asyncio.run(HealthChecker.check_backend())
    if json_output:
        print(json.dumps(health, indent=2))
    else:
        print("=== EVAVO Native ComfyUI Health ===")
        print(f"Endpoint: {health['endpoint']}")
        print(f"Status:   {'READY' if health.get('healthy') else 'NOT READY'}")
        if health.get("comfyui_version"):
            print(f"ComfyUI:  {health['comfyui_version']}")
        devices = health.get("devices")
        if isinstance(devices, list):
            print(f"Devices:  {len(devices)}")
    return bool(health.get("healthy"))


if __name__ == "__main__":
    raise SystemExit(0 if print_health_report() else 3)
