"""Quality-first ComfyUI adapter.

This class preserves the hardened transport, model inventory, checkpoint
selection, workflow preflight, cancellation and output validation from the
legacy ComfyUI adapter, while making SDXL-native production settings canonical.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from .comfyui_backend import ComfyUIBackend as _BaseComfyUIBackend
from ..quality_profiles import ImageQualitySettings, resolve_quality_settings


class QualityComfyUIBackend(_BaseComfyUIBackend):
    """ComfyUI backend with validated quality profiles and runtime fallbacks."""

    _SAMPLER_FALLBACKS = (
        "dpmpp_2m_sde",
        "dpmpp_3m_sde",
        "dpmpp_2m",
        "euler",
    )
    _SCHEDULER_FALLBACKS = ("karras", "normal", "simple")

    def sampling_inventory(self) -> Dict[str, Any]:
        samplers = self.node_input_choices("KSampler", "sampler_name")
        schedulers = self.node_input_choices("KSampler", "scheduler")
        return {
            "samplers": samplers,
            "schedulers": schedulers,
            "recommended_sampler": self._choose_available(
                os.getenv("EVAVO_IMAGE_SAMPLER", "dpmpp_2m_sde"),
                samplers,
                self._SAMPLER_FALLBACKS,
            ),
            "recommended_scheduler": self._choose_available(
                os.getenv("EVAVO_IMAGE_SCHEDULER", "karras"),
                schedulers,
                self._SCHEDULER_FALLBACKS,
            ),
        }

    @staticmethod
    def _choose_available(preferred: str, available: list[str], fallbacks: tuple[str, ...]) -> str:
        if not available:
            return preferred
        if preferred in available:
            return preferred
        for candidate in fallbacks:
            if candidate in available:
                return candidate
        return available[0]

    def resolve_sampling(self, settings: ImageQualitySettings) -> ImageQualitySettings:
        try:
            samplers = self.node_input_choices("KSampler", "sampler_name")
        except RuntimeError:
            samplers = []
        try:
            schedulers = self.node_input_choices("KSampler", "scheduler")
        except RuntimeError:
            schedulers = []
        sampler = self._choose_available(settings.sampler_name, samplers, self._SAMPLER_FALLBACKS)
        scheduler = self._choose_available(settings.scheduler, schedulers, self._SCHEDULER_FALLBACKS)
        if sampler == settings.sampler_name and scheduler == settings.scheduler:
            return settings
        return ImageQualitySettings(
            name=settings.name,
            width=settings.width,
            height=settings.height,
            steps=settings.steps,
            cfg_scale=settings.cfg_scale,
            sampler_name=sampler,
            scheduler=scheduler,
            denoise=settings.denoise,
        )

    def build_txt2img_workflow(
        self,
        prompt: str,
        *,
        negative_prompt: str = "",
        width: Any = None,
        height: Any = None,
        steps: Any = None,
        cfg_scale: Any = None,
        seed: Optional[int] = None,
        checkpoint: Optional[str] = None,
        filename_prefix: str = "EVAVO",
        workflow_path: Optional[str] = None,
        quality_profile: Optional[str] = None,
        sampler_name: Optional[str] = None,
        scheduler: Optional[str] = None,
        denoise: Any = None,
    ) -> Dict[str, Any]:
        settings = resolve_quality_settings(
            quality_profile=quality_profile,
            width=width,
            height=height,
            steps=steps,
            cfg_scale=cfg_scale,
            sampler_name=sampler_name,
            scheduler=scheduler,
            denoise=denoise,
        )
        settings = self.resolve_sampling(settings)

        workflow = super().build_txt2img_workflow(
            prompt,
            negative_prompt=negative_prompt,
            width=settings.width,
            height=settings.height,
            steps=settings.steps,
            cfg_scale=settings.cfg_scale,
            seed=seed,
            checkpoint=checkpoint,
            filename_prefix=filename_prefix,
            workflow_path=workflow_path,
        )

        explicit_sampling = any(
            value is not None for value in (quality_profile, sampler_name, scheduler, denoise)
        )
        template_path = workflow_path or os.getenv("EVAVO_COMFYUI_WORKFLOW")
        if template_path and not explicit_sampling:
            return workflow

        for node in workflow.values():
            if not isinstance(node, dict) or node.get("class_type") != "KSampler":
                continue
            inputs = node.get("inputs")
            if not isinstance(inputs, dict):
                continue
            inputs["steps"] = settings.steps
            inputs["cfg"] = settings.cfg_scale
            inputs["sampler_name"] = settings.sampler_name
            inputs["scheduler"] = settings.scheduler
            inputs["denoise"] = settings.denoise
        return workflow

    def queue_image(
        self,
        prompt: str,
        *,
        project_name: str = "batch_gen",
        negative_prompt: str = "",
        width: Any = None,
        height: Any = None,
        steps: Any = None,
        cfg_scale: Any = None,
        seed: Optional[int] = None,
        checkpoint: Optional[str] = None,
        workflow_path: Optional[str] = None,
        quality_profile: Optional[str] = None,
        sampler_name: Optional[str] = None,
        scheduler: Optional[str] = None,
        denoise: Any = None,
    ) -> Dict[str, Any]:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be a non-empty string")

        settings = resolve_quality_settings(
            quality_profile=quality_profile,
            width=width,
            height=height,
            steps=steps,
            cfg_scale=cfg_scale,
            sampler_name=sampler_name,
            scheduler=scheduler,
            denoise=denoise,
        )
        settings = self.resolve_sampling(settings)

        template_path = workflow_path or os.getenv("EVAVO_COMFYUI_WORKFLOW")
        workflow = self.build_txt2img_workflow(
            prompt.strip(),
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            steps=steps,
            cfg_scale=cfg_scale,
            seed=seed,
            checkpoint=checkpoint,
            filename_prefix=f"EVAVO/{project_name}",
            workflow_path=workflow_path,
            quality_profile=quality_profile,
            sampler_name=sampler_name,
            scheduler=scheduler,
            denoise=denoise,
        )
        if template_path and self._truthy_environment("EVAVO_PREFLIGHT_CUSTOM_WORKFLOW", default=True):
            self.preflight_workflow(workflow)

        response = self._request("/prompt", method="POST", payload={"prompt": workflow}, timeout=30.0)
        prompt_id = response.get("prompt_id")
        if not isinstance(prompt_id, str) or not prompt_id:
            errors = response.get("node_errors")
            raise RuntimeError(f"COMFYUI_QUEUE_REJECTED:{errors or response}")

        explicit_sampling = any(
            value is not None for value in (quality_profile, sampler_name, scheduler, denoise)
        )
        quality_applied = not template_path or explicit_sampling
        return {
            "status": "queued",
            "task_id": prompt_id,
            "prompt_id": prompt_id,
            "project_name": project_name,
            "checkpoint": checkpoint or os.getenv("EVAVO_COMFYUI_CHECKPOINT") or self._workflow_checkpoint(workflow),
            "backend_mode": "native-comfyui",
            "quality_profile": settings.name if quality_applied else "custom_workflow",
            "quality": settings.as_dict() if quality_applied else None,
            "quality_applied": quality_applied,
        }
