"""Quality-first ComfyUI adapter.

This class preserves the hardened transport, model inventory, checkpoint
selection, workflow preflight, cancellation and output validation from the
legacy ComfyUI adapter, while making SDXL-native production settings canonical.
"""

from __future__ import annotations

import os
from dataclasses import replace
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
    _LATENT_UPSCALE_FALLBACKS = ("bislerp", "bicubic", "bilinear", "area", "nearest-exact")

    def sampling_inventory(self) -> Dict[str, Any]:
        samplers = self.node_input_choices("KSampler", "sampler_name")
        schedulers = self.node_input_choices("KSampler", "scheduler")
        try:
            latent_upscale_methods = self.node_input_choices("LatentUpscale", "upscale_method")
        except RuntimeError:
            latent_upscale_methods = []
        return {
            "samplers": samplers,
            "schedulers": schedulers,
            "latent_upscale_methods": latent_upscale_methods,
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
            "recommended_latent_upscale_method": self._choose_available(
                os.getenv("EVAVO_IMAGE_LATENT_UPSCALE_METHOD", "bislerp"),
                latent_upscale_methods,
                self._LATENT_UPSCALE_FALLBACKS,
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
        second_sampler = settings.second_pass_sampler_name or settings.sampler_name
        second_scheduler = settings.second_pass_scheduler or settings.scheduler
        latent_method = settings.latent_upscale_method

        if settings.second_pass_enabled:
            second_sampler = self._choose_available(second_sampler, samplers, self._SAMPLER_FALLBACKS)
            second_scheduler = self._choose_available(second_scheduler, schedulers, self._SCHEDULER_FALLBACKS)
            try:
                latent_methods = self.node_input_choices("LatentUpscale", "upscale_method")
            except RuntimeError:
                latent_methods = []
            latent_method = self._choose_available(
                settings.latent_upscale_method,
                latent_methods,
                self._LATENT_UPSCALE_FALLBACKS,
            )

        return replace(
            settings,
            sampler_name=sampler,
            scheduler=scheduler,
            second_pass_sampler_name=second_sampler,
            second_pass_scheduler=second_scheduler,
            latent_upscale_method=latent_method,
        )

    @staticmethod
    def _apply_primary_sampling(workflow: Dict[str, Any], settings: ImageQualitySettings) -> None:
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

    @staticmethod
    def _append_hero_second_pass(workflow: Dict[str, Any], settings: ImageQualitySettings) -> None:
        """Append a core-node-only latent upscale and low-denoise detail pass.

        This method intentionally assumes the canonical built-in EVAVO graph
        created by the base adapter. Custom templates can have arbitrary graph
        topology, so two-pass expansion is refused for them rather than silently
        claiming the hero profile was applied.
        """

        if not settings.second_pass_enabled:
            return
        required_nodes = {"1", "2", "3", "4", "5", "6", "7"}
        if not required_nodes.issubset(workflow):
            raise RuntimeError("COMFYUI_HERO_BASE_GRAPH_INVALID:canonical nodes 1-7 are required")

        first_sampler = workflow["5"]
        first_inputs = first_sampler.get("inputs") if isinstance(first_sampler, dict) else None
        if not isinstance(first_inputs, dict):
            raise RuntimeError("COMFYUI_HERO_BASE_GRAPH_INVALID:primary KSampler inputs are missing")
        seed = first_inputs.get("seed")
        if not isinstance(seed, int):
            try:
                seed = int(seed)
            except (TypeError, ValueError) as exc:
                raise RuntimeError("COMFYUI_HERO_BASE_GRAPH_INVALID:primary seed is invalid") from exc

        second_cfg = settings.second_pass_cfg_scale
        if second_cfg is None:
            second_cfg = settings.cfg_scale
        second_sampler = settings.second_pass_sampler_name or settings.sampler_name
        second_scheduler = settings.second_pass_scheduler or settings.scheduler

        workflow["8"] = {
            "class_type": "LatentUpscale",
            "inputs": {
                "samples": ["5", 0],
                "upscale_method": settings.latent_upscale_method,
                "width": settings.output_width,
                "height": settings.output_height,
                "crop": "disabled",
            },
        }
        workflow["9"] = {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": settings.second_pass_steps,
                "cfg": second_cfg,
                "sampler_name": second_sampler,
                "scheduler": second_scheduler,
                "denoise": settings.second_pass_denoise,
                "model": ["1", 0],
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["8", 0],
            },
        }
        decode = workflow["6"]
        decode_inputs = decode.get("inputs") if isinstance(decode, dict) else None
        if not isinstance(decode_inputs, dict):
            raise RuntimeError("COMFYUI_HERO_BASE_GRAPH_INVALID:VAEDecode inputs are missing")
        decode_inputs["samples"] = ["9", 0]

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
        upscale_factor: Any = None,
        second_pass_steps: Any = None,
        second_pass_cfg_scale: Any = None,
        second_pass_sampler_name: Optional[str] = None,
        second_pass_scheduler: Optional[str] = None,
        second_pass_denoise: Any = None,
        latent_upscale_method: Optional[str] = None,
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
            upscale_factor=upscale_factor,
            second_pass_steps=second_pass_steps,
            second_pass_cfg_scale=second_pass_cfg_scale,
            second_pass_sampler_name=second_pass_sampler_name,
            second_pass_scheduler=second_pass_scheduler,
            second_pass_denoise=second_pass_denoise,
            latent_upscale_method=latent_upscale_method,
        )
        settings = self.resolve_sampling(settings)

        template_path = workflow_path or os.getenv("EVAVO_COMFYUI_WORKFLOW")
        if template_path and settings.second_pass_enabled:
            raise RuntimeError(
                "COMFYUI_HERO_CUSTOM_WORKFLOW_UNSUPPORTED:two-pass quality expansion requires the canonical built-in graph; "
                "encode the high-resolution pass directly in the custom workflow instead"
            )

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
            value is not None
            for value in (
                quality_profile,
                sampler_name,
                scheduler,
                denoise,
                upscale_factor,
                second_pass_steps,
                second_pass_cfg_scale,
                second_pass_sampler_name,
                second_pass_scheduler,
                second_pass_denoise,
                latent_upscale_method,
            )
        )
        if template_path and not explicit_sampling:
            return workflow

        self._apply_primary_sampling(workflow, settings)
        if settings.second_pass_enabled:
            self._append_hero_second_pass(workflow, settings)
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
        upscale_factor: Any = None,
        second_pass_steps: Any = None,
        second_pass_cfg_scale: Any = None,
        second_pass_sampler_name: Optional[str] = None,
        second_pass_scheduler: Optional[str] = None,
        second_pass_denoise: Any = None,
        latent_upscale_method: Optional[str] = None,
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
            upscale_factor=upscale_factor,
            second_pass_steps=second_pass_steps,
            second_pass_cfg_scale=second_pass_cfg_scale,
            second_pass_sampler_name=second_pass_sampler_name,
            second_pass_scheduler=second_pass_scheduler,
            second_pass_denoise=second_pass_denoise,
            latent_upscale_method=latent_upscale_method,
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
            upscale_factor=upscale_factor,
            second_pass_steps=second_pass_steps,
            second_pass_cfg_scale=second_pass_cfg_scale,
            second_pass_sampler_name=second_pass_sampler_name,
            second_pass_scheduler=second_pass_scheduler,
            second_pass_denoise=second_pass_denoise,
            latent_upscale_method=latent_upscale_method,
        )
        if (
            template_path
            and self._truthy_environment("EVAVO_PREFLIGHT_CUSTOM_WORKFLOW", default=True)
        ) or settings.second_pass_enabled:
            self.preflight_workflow(workflow)

        response = self._request("/prompt", method="POST", payload={"prompt": workflow}, timeout=30.0)
        prompt_id = response.get("prompt_id")
        if not isinstance(prompt_id, str) or not prompt_id:
            errors = response.get("node_errors")
            raise RuntimeError(f"COMFYUI_QUEUE_REJECTED:{errors or response}")

        explicit_sampling = any(
            value is not None
            for value in (
                quality_profile,
                sampler_name,
                scheduler,
                denoise,
                upscale_factor,
                second_pass_steps,
                second_pass_cfg_scale,
                second_pass_sampler_name,
                second_pass_scheduler,
                second_pass_denoise,
                latent_upscale_method,
            )
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
            "render_passes": settings.pass_count if quality_applied else None,
            "output_width": settings.output_width if quality_applied else None,
            "output_height": settings.output_height if quality_applied else None,
        }
