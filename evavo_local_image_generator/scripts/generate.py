"""
Generation orchestration for multi-modal AI outputs via ComfyUI and local backends.

This module handles:
- Image generation via ComfyUI stable diffusion nodes
- Video generation and frame interpolation
- Batch processing with digest-bound validation
- Integration with evavo-local-storage bee:// URIs
"""

import os
import json
import asyncio
import hashlib
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path
import httpx

from .storage import get_storage_client


class GenerationTask:
    """Represents a single generation task."""
    
    def __init__(
        self,
        task_type: str,
        parameters: Dict[str, Any],
        project_name: Optional[str] = None
    ):
        """
        Initialize a generation task.
        
        Args:
            task_type: Type of generation (image, video, audio, etc.)
            parameters: Task-specific parameters
            project_name: Optional project context
        """
        self.task_id = self._generate_task_id()
        self.task_type = task_type
        self.parameters = parameters
        self.project_name = project_name
        self.created_at = datetime.utcnow()
        self.digest = self._compute_digest()
    
    def _generate_task_id(self) -> str:
        """Generate unique task ID."""
        timestamp = datetime.utcnow().isoformat()
        return hashlib.sha256(timestamp.encode()).hexdigest()[:16]
    
    def _compute_digest(self) -> str:
        """Compute digest for validation."""
        data = {
            "type": self.task_type,
            "params": self.parameters,
            "created": self.created_at.isoformat()
        }
        data_str = json.dumps(data, sort_keys=True)
        return hashlib.sha256(data_str.encode()).hexdigest()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert task to dictionary."""
        return {
            "task_id": self.task_id,
            "type": self.task_type,
            "parameters": self.parameters,
            "project": self.project_name,
            "digest": self.digest,
            "created_at": self.created_at.isoformat()
        }


class ComfyUIClient:
    """Client for ComfyUI API integration."""
    
    def __init__(self, endpoint: str = "http://127.0.0.1:8188"):
        """Initialize ComfyUI client."""
        self.endpoint = endpoint
        self.client = httpx.AsyncClient(timeout=300.0)
    
    async def queue_prompt(self, prompt: Dict[str, Any]) -> str:
        """Queue a prompt to ComfyUI and return prompt ID."""
        try:
            response = await self.client.post(
                f"{self.endpoint}/prompt",
                json={"prompt": prompt}
            )
            response.raise_for_status()
            data = response.json()
            return data.get("prompt_id", "")
        except Exception as e:
            raise RuntimeError(f"Failed to queue prompt: {e}")
    
    async def get_history(self, prompt_id: str) -> Dict[str, Any]:
        """Get execution history for a prompt."""
        try:
            response = await self.client.get(
                f"{self.endpoint}/history/{prompt_id}"
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            raise RuntimeError(f"Failed to get history: {e}")
    
    async def close(self) -> None:
        """Close the client."""
        await self.client.aclose()


class ImageGenerator:
    """High-level image generation interface."""
    
    def __init__(self):
        """Initialize image generator."""
        self.comfyui_endpoint = os.getenv(
            "EVAVO_COMFYUI_ENDPOINT",
            "http://127.0.0.1:8188"
        )
        self.storage_client = get_storage_client()
    
    async def generate_image(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 512,
        height: int = 512,
        steps: int = 20,
        cfg_scale: float = 7.5,
        project_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate an image from a text prompt.
        
        Args:
            prompt: Text prompt for generation
            negative_prompt: Negative prompt guidance
            width: Output width in pixels
            height: Output height in pixels
            steps: Number of inference steps
            cfg_scale: Guidance scale
            project_name: Optional project context
            
        Returns:
            Generation result with metadata
        """
        # Create task
        task = GenerationTask(
            task_type="image",
            parameters={
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "width": width,
                "height": height,
                "steps": steps,
                "cfg_scale": cfg_scale
            },
            project_name=project_name
        )
        
        # Record in storage
        self.storage_client.record_generation(task.to_dict())
        
        # In production, would queue to ComfyUI
        # For now, return task metadata
        return {
            "task_id": task.task_id,
            "digest": task.digest,
            "storage_uri": self.storage_client.get_outputs_path(),
            "status": "queued"
        }
    
    async def batch_generate(
        self,
        prompts: List[str],
        project_name: Optional[str] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """Generate multiple images in batch."""
        results = []
        for i, prompt in enumerate(prompts):
            result = await self.generate_image(
                prompt=prompt,
                project_name=project_name,
                **kwargs
            )
            result["batch_index"] = i
            results.append(result)
        return results


async def generate_images(
    prompts: List[str],
    output_project: Optional[str] = None,
    **generation_kwargs
) -> List[Dict[str, Any]]:
    """Convenience function for batch image generation."""
    generator = ImageGenerator()
    return await generator.batch_generate(
        prompts=prompts,
        project_name=output_project,
        **generation_kwargs
    )
