"""Generation orchestration for EVAVO image tasks via native ComfyUI."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..backends import ComfyUIBackend
from .storage import get_storage_client


class GenerationTask:
    def __init__(self, task_type: str, parameters: Dict[str, Any], project_name: Optional[str] = None):
        self.task_type = task_type
        self.parameters = parameters
        self.project_name = project_name
        self.created_at = datetime.now(timezone.utc)
        seed = json.dumps({"type": task_type, "parameters": parameters, "project": project_name, "created_at": self.created_at.isoformat()}, sort_keys=True)
        self.task_id = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
        self.digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {"task_id": self.task_id, "type": self.task_type, "parameters": self.parameters, "project": self.project_name, "digest": self.digest, "created_at": self.created_at.isoformat()}


class ComfyUIClient:
    """Async facade over the shared standard-library ComfyUI backend."""

    def __init__(self, endpoint: str = "http://127.0.0.1:8188"):
        self.backend = ComfyUIBackend(endpoint)
        self.endpoint = self.backend.endpoint

    async def health(self) -> Dict[str, Any]:
        return await asyncio.to_thread(self.backend.health)

    async def queue_prompt(self, prompt: Dict[str, Any]) -> str:
        response = await asyncio.to_thread(self.backend._request, "/prompt", method="POST", payload={"prompt": prompt}, timeout=30.0)
        prompt_id = response.get("prompt_id")
        if not isinstance(prompt_id, str) or not prompt_id:
            raise RuntimeError(f"Failed to queue ComfyUI prompt: {response}")
        return prompt_id

    async def get_history(self, prompt_id: str) -> Dict[str, Any]:
        return await asyncio.to_thread(self.backend.history, prompt_id)

    async def close(self) -> None:
        return None


class ImageGenerator:
    """High-level image generation interface backed by native ComfyUI."""

    def __init__(self, endpoint: Optional[str] = None):
        self.comfyui_endpoint = (endpoint or os.getenv("EVAVO_COMFYUI_ENDPOINT") or os.getenv("COMFYUI_ENDPOINT") or "http://127.0.0.1:8188").rstrip("/")
        self.backend = ComfyUIBackend(self.comfyui_endpoint)
        self.storage_client = get_storage_client()

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
    ) -> Dict[str, Any]:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be a non-empty string")
        project = project_name or "default"
        task = GenerationTask("image", {"prompt": prompt, "negative_prompt": negative_prompt, "width": width, "height": height, "steps": steps, "cfg_scale": cfg_scale, "seed": seed, "checkpoint": checkpoint}, project)
        result = await asyncio.to_thread(
            self.backend.queue_image,
            prompt,
            project_name=project,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            steps=steps,
            cfg_scale=cfg_scale,
            seed=seed,
            checkpoint=checkpoint,
        )
        record = {**task.to_dict(), "backend_task_id": result["task_id"], "status": result["status"], "backend_mode": result.get("backend_mode"), "checkpoint": result.get("checkpoint")}
        self.storage_client.record_generation(record)
        return {**result, "digest": task.digest, "storage_uri": self.storage_client.get_outputs_path()}

    async def batch_generate(self, prompts: List[str], project_name: Optional[str] = None, concurrency: int = 4, **kwargs: Any) -> List[Dict[str, Any]]:
        if concurrency < 1:
            raise ValueError("concurrency must be at least 1")
        semaphore = asyncio.Semaphore(concurrency)

        async def one(prompt: str) -> Dict[str, Any]:
            async with semaphore:
                return await self.generate_image(prompt=prompt, project_name=project_name, **kwargs)

        return await asyncio.gather(*(one(prompt) for prompt in prompts))


async def generate_images(prompts: List[str], output_project: Optional[str] = None, **generation_kwargs: Any) -> List[Dict[str, Any]]:
    generator = ImageGenerator()
    return await generator.batch_generate(prompts=prompts, project_name=output_project, **generation_kwargs)
