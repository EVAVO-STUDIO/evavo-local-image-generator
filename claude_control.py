"""Backward-compatible synchronous controller for real EVAVO image generation.

Modern Claude/ChatGPT integrations should use MCP. This module remains for older
Python callers, but it now delegates to the same native ComfyUI runtime and can
no longer fabricate completed image/video outputs.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from evavo_local_image_generator.backends import ComfyUIBackend
from evavo_local_image_generator.comfyui_runtime import ensure_comfyui, native_health

logger = logging.getLogger(__name__)

COMFYUI_URL = (os.getenv("COMFYUI_ENDPOINT") or os.getenv("EVAVO_COMFYUI_ENDPOINT") or "http://127.0.0.1:8188").rstrip("/")
OUTPUT_DIR = Path(os.getenv("EVAVO_GENERATION_OUTPUT_DIR", str(Path(__file__).resolve().parent / ".evavo" / "outputs" / "claude-control"))).expanduser().resolve()
TIMEOUT = 30


class GenerationStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    ERROR = "error"


class ClaudeControllerException(Exception):
    pass


class ServerUnavailableException(ClaudeControllerException):
    pass


class GenerationFailedException(ClaudeControllerException):
    pass


class ClaudeController:
    """Compatibility controller backed by native ComfyUI image generation."""

    def __init__(self, comfyui_url: str = COMFYUI_URL, output_dir: Optional[str | Path] = None):
        self.base_url = comfyui_url.rstrip("/")
        self.output_dir = Path(output_dir or OUTPUT_DIR).expanduser().resolve()
        self.results_cache: List[Dict[str, Any]] = []
        self.execution_log: List[Dict[str, Any]] = []
        self.start_time = datetime.now()

    def log_action(self, action: str, details: Optional[Dict[str, Any]] = None, level: str = "INFO") -> None:
        entry = {"timestamp": datetime.now().isoformat(), "action": action, "details": details or {}}
        self.execution_log.append(entry)
        log = getattr(logger, level.lower(), logger.info)
        log("[%s] %s", action, details or "")

    def check_server(self, timeout: int = TIMEOUT) -> bool:
        del timeout  # native_health has its own bounded request timeout.
        return bool(native_health(self.base_url))

    def check_system(self) -> Dict[str, Any]:
        health = native_health(self.base_url)
        ready = bool(health)
        return {
            "server_running": ready,
            "server_url": self.base_url,
            "ready": ready,
            "mode": "native-comfyui" if ready else "offline_or_not_native",
            "message": "Ready to generate" if ready else "Native ComfyUI is not ready",
            "health": health,
            "timestamp": datetime.now().isoformat(),
        }

    def _ensure(self) -> Dict[str, Any]:
        try:
            return ensure_comfyui(self.base_url, wait_seconds=120.0, allow_start=True)
        except RuntimeError as exc:
            raise ServerUnavailableException(str(exc)) from exc

    @staticmethod
    def _quality_steps(quality: str) -> int:
        return {"standard": 20, "high": 28, "ultra": 36}.get(str(quality).lower(), 28)

    def generate_image_simple(
        self,
        subject: str,
        quality: str = "high",
        style: str = "",
        retry: int = 0,
    ) -> Dict[str, Any]:
        del retry  # retained only for source compatibility; backend errors are explicit.
        if not isinstance(subject, str) or not subject.strip():
            result = {"status": GenerationStatus.FAILED.value, "error_code": "INVALID_PROMPT", "error": "subject must be a non-empty string"}
            self.results_cache.append(result)
            return result

        prompt = subject.strip()
        if style and style.strip():
            prompt = f"{prompt}, {style.strip()} style"
        started = time.perf_counter()
        self.log_action("generate_image_simple", {"prompt": prompt, "quality": quality})
        try:
            self._ensure()
            backend = ComfyUIBackend(self.base_url)
            queued = backend.queue_image(
                prompt,
                project_name="claude_control",
                steps=self._quality_steps(quality),
            )
            task_id = str(queued["task_id"])
            target = self.output_dir / task_id
            paths = backend.wait_and_download(task_id, target, timeout=600.0)
            if not paths:
                raise GenerationFailedException("ComfyUI completed without an image output")
            result = {
                "status": GenerationStatus.COMPLETED.value,
                "task_id": task_id,
                "request_id": task_id,
                "output": str(paths[0]),
                "outputs": [str(path) for path in paths],
                "time": round(time.perf_counter() - started, 3),
                "quality": quality,
                "style": style,
                "prompt": prompt,
                "backend_mode": "native-comfyui",
                "checkpoint": queued.get("checkpoint"),
            }
        except Exception as exc:
            result = {
                "status": GenerationStatus.FAILED.value,
                "error_code": "IMAGE_GENERATION_FAILED",
                "error": str(exc),
                "prompt": prompt,
                "time": round(time.perf_counter() - started, 3),
            }
        self.results_cache.append(result)
        return result

    def generate_image_series(self, subjects: List[str], quality: str = "high") -> List[Dict[str, Any]]:
        if not isinstance(subjects, list):
            raise ValueError("subjects must be a list")
        return [self.generate_image_simple(subject, quality=quality) for subject in subjects]

    def generate_video_simple(self, subject: str, length: str = "short") -> Dict[str, Any]:
        """Historical API retained only to fail explicitly; video is not implemented here."""
        result = {
            "status": GenerationStatus.FAILED.value,
            "error_code": "NOT_IMPLEMENTED",
            "error": "Video generation is not part of the verified evavo-local-image-generator production runtime",
            "subject": subject,
            "length": length,
        }
        self.results_cache.append(result)
        return result

    def orchestrate_content_creation(
        self,
        project_name: str,
        scene_descriptions: List[str],
        output_format: str = "standard",
    ) -> Dict[str, Any]:
        started = datetime.now()
        scene_results = []
        for description in scene_descriptions:
            result = self.generate_image_simple(description, quality=output_format)
            scene_results.append({"description": description, "result": result})
        completed = sum(1 for item in scene_results if item["result"].get("status") == GenerationStatus.COMPLETED.value)
        total = len(scene_results)
        return {
            "project": project_name,
            "started_at": started.isoformat(),
            "scenes": scene_results,
            "summary": {
                "completed": completed,
                "failed": total - completed,
                "total": total,
                "success_rate": f"{(completed / total * 100):.1f}%" if total else "0%",
                "total_time": f"{(datetime.now() - started).total_seconds():.1f}s",
                "completed_at": datetime.now().isoformat(),
                "mode": "image-only",
            },
        }

    def get_stats(self) -> Dict[str, Any]:
        completed = sum(1 for item in self.results_cache if item.get("status") == GenerationStatus.COMPLETED.value)
        failed = sum(1 for item in self.results_cache if item.get("status") == GenerationStatus.FAILED.value)
        total = len(self.results_cache)
        return {
            "total_generations": total,
            "successful": completed,
            "failed": failed,
            "success_rate": f"{(completed / total * 100):.1f}%" if total else "0%",
            "total_time": f"{(datetime.now() - self.start_time).total_seconds():.1f}s",
            "cache_size": total,
            "execution_log_size": len(self.execution_log),
        }

    def export_results(self, format: str = "json") -> str:
        report = {
            "generated_at": datetime.now().isoformat(),
            "execution_log": self.execution_log,
            "results": self.results_cache,
            "statistics": self.get_stats(),
        }
        if format == "json":
            return json.dumps(report, indent=2)
        stats = report["statistics"]
        return (
            "EVAVO Image Generation Report\n"
            + "=" * 60
            + f"\nGenerated at: {report['generated_at']}\n\n"
            + f"Total Generations: {stats['total_generations']}\n"
            + f"Successful: {stats['successful']}\n"
            + f"Failed: {stats['failed']}\n"
            + f"Success Rate: {stats['success_rate']}\n"
            + f"Total Time: {stats['total_time']}\n"
        )

    def wait_for_server(self, max_wait: int = 60) -> bool:
        deadline = time.monotonic() + max(1, int(max_wait))
        while time.monotonic() < deadline:
            if self.check_server():
                return True
            time.sleep(1)
        return False


def generate_image(prompt: str, quality: str = "high") -> Dict[str, Any]:
    return ClaudeController().generate_image_simple(prompt, quality=quality)


def generate_images(prompts: List[str], quality: str = "high") -> List[Dict[str, Any]]:
    return ClaudeController().generate_image_series(prompts, quality=quality)


def check_ready() -> bool:
    return ClaudeController().check_system()["ready"]


def get_status() -> Dict[str, Any]:
    controller = ClaudeController()
    return {"system": controller.check_system(), "stats": controller.get_stats()}


if __name__ == "__main__":
    print(json.dumps(get_status(), indent=2))
