"""Backward-compatible package image API backed by native ComfyUI.

This module no longer maintains a separate BeeStation/digest-bound execution
system. It delegates rendering to the shared ``ComfyUIBackend`` and records real
ComfyUI prompt IDs in the same ``TaskTracker`` used by CLI and MCP workflows.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from evavo_operations import TaskTracker
from ..backends import ComfyUIBackend


class GenerationTask:
    """Legacy metadata wrapper retained for source compatibility only."""

    def __init__(self, task_type: str, parameters: Dict[str, Any], project_name: Optional[str] = None):
        self.task_type = str(task_type)
        self.parameters = dict(parameters)
        self.project_name = project_name
        self.created_at = datetime.now(timezone.utc)
        seed = json.dumps(
            {
                "type": self.task_type,
                "parameters": self.parameters,
                "project": project_name,
                "created_at": self.created_at.isoformat(),
            },
            sort_keys=True,
            default=str,
        )
        self.digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
        self.task_id = self.digest[:16]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "type": self.task_type,
            "parameters": self.parameters,
            "project": self.project_name,
            "digest": self.digest,
            "created_at": self.created_at.isoformat(),
        }


class ComfyUIClient:
    """Async compatibility facade over the shared standard-library backend."""

    def __init__(self, endpoint: Optional[str] = None):
        self.backend = ComfyUIBackend(endpoint)
        self.endpoint = self.backend.endpoint

    async def health(self) -> Dict[str, Any]:
        return await asyncio.to_thread(self.backend.health)

    async def queue_prompt(self, prompt: Dict[str, Any]) -> str:
        response = await asyncio.to_thread(
            self.backend._request,
            "/prompt",
            method="POST",
            payload={"prompt": prompt},
            timeout=30.0,
        )
        prompt_id = response.get("prompt_id")
        if not isinstance(prompt_id, str) or not prompt_id:
            raise RuntimeError(f"COMFYUI_QUEUE_REJECTED:{response}")
        return prompt_id

    async def get_history(self, prompt_id: str) -> Dict[str, Any]:
        return await asyncio.to_thread(self.backend.history, prompt_id)

    async def close(self) -> None:
        return None


class ImageGenerator:
    """Legacy high-level image API sharing the current native EVAVO contract."""

    def __init__(self, endpoint: Optional[str] = None, tracker: Optional[TaskTracker] = None):
        self.backend = ComfyUIBackend(endpoint)
        self.comfyui_endpoint = self.backend.endpoint
        self.tracker = tracker or TaskTracker()

    async def generate_image(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        steps: int = 24,
        cfg_scale: float = 7.0,
        project_name: Optional[str] = None,
        seed: Optional[int] = None,
        checkpoint: Optional[str] = None,
        workflow_path: Optional[str] = None,
        wait: bool = False,
        wait_timeout: float = 600.0,
        output_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be a non-empty string")
        project = (project_name or "default").strip() or "default"
        metadata = GenerationTask(
            "image",
            {
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "width": width,
                "height": height,
                "steps": steps,
                "cfg_scale": cfg_scale,
                "seed": seed,
                "checkpoint": checkpoint,
                "workflow_path": workflow_path,
            },
            project,
        )
        result = await asyncio.to_thread(
            self.backend.queue_image,
            prompt.strip(),
            project_name=project,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            steps=steps,
            cfg_scale=cfg_scale,
            seed=seed,
            checkpoint=checkpoint,
            workflow_path=workflow_path,
        )
        task_id = str(result["task_id"])
        target = Path(output_dir).expanduser().resolve() if output_dir else None
        await asyncio.to_thread(
            self.tracker.add_task,
            task_id,
            prompt.strip(),
            "queued",
            project_name=project,
            backend_mode="native-comfyui",
            checkpoint=str(result.get("checkpoint")) if result.get("checkpoint") else None,
            workflow_path=workflow_path,
            output_dir=str(target) if target else None,
        )
        response: Dict[str, Any] = {
            **result,
            "ok": True,
            "digest": metadata.digest,
            "prompt": prompt.strip(),
            "project_name": project,
        }
        if not wait:
            return response

        target = target or (Path(os.getenv("EVAVO_GENERATION_OUTPUT_DIR", ".evavo/outputs")).expanduser().resolve() / project)
        try:
            downloaded = await asyncio.to_thread(
                self.backend.wait_and_download,
                task_id,
                target,
                timeout=wait_timeout,
            )
        except Exception as exc:
            await asyncio.to_thread(
                self.tracker.update_task,
                task_id,
                "failed",
                output_dir=str(target),
                backend_mode="native-comfyui",
                error_code="GENERATION_WAIT_FAILED",
                error_message=str(exc),
            )
            raise
        await asyncio.to_thread(
            self.tracker.update_task,
            task_id,
            "completed",
            output_uris=[str(item) for item in downloaded],
            output_dir=str(target),
            backend_mode="native-comfyui",
        )
        response.update({"status": "completed", "downloaded_files": downloaded, "output_dir": str(target)})
        return response

    async def batch_generate(
        self,
        prompts: List[str],
        project_name: Optional[str] = None,
        concurrency: int = 4,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        if not isinstance(prompts, list) or not prompts:
            raise ValueError("prompts must be a non-empty list")
        if any(not isinstance(prompt, str) or not prompt.strip() for prompt in prompts):
            raise ValueError("every prompt must be a non-empty string")
        if concurrency < 1 or concurrency > 16:
            raise ValueError("concurrency must be between 1 and 16")
        semaphore = asyncio.Semaphore(concurrency)

        async def one(prompt: str) -> Dict[str, Any]:
            async with semaphore:
                return await self.generate_image(prompt=prompt, project_name=project_name, **kwargs)

        return await asyncio.gather(*(one(prompt) for prompt in prompts))


async def generate_images(
    prompts: List[str],
    output_project: Optional[str] = None,
    **generation_kwargs: Any,
) -> List[Dict[str, Any]]:
    """Compatibility convenience API for real native image generation."""
    generator = ImageGenerator()
    return await generator.batch_generate(
        prompts=prompts,
        project_name=output_project,
        **generation_kwargs,
    )
