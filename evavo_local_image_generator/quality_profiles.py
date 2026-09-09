"""Production quality profiles for EVAVO local image generation.

Profiles intentionally describe the *starting point* for a render, not an
absolute artistic truth. Every release should still be A/B tested with fixed
seeds on the actual GPU and checkpoint.
"""

from __future__ import annotations

import math
import os
from dataclasses import asdict, dataclass, replace
from typing import Any, Dict, Optional


def _align8(value: float) -> int:
    number = max(64, int(round(value)))
    return max(64, number - (number % 8))


@dataclass(frozen=True)
class ImageQualitySettings:
    name: str
    width: int
    height: int
    steps: int
    cfg_scale: float
    sampler_name: str
    scheduler: str
    denoise: float = 1.0
    upscale_factor: float = 1.0
    second_pass_steps: int = 0
    second_pass_cfg_scale: Optional[float] = None
    second_pass_sampler_name: Optional[str] = None
    second_pass_scheduler: Optional[str] = None
    second_pass_denoise: float = 0.0
    latent_upscale_method: str = "bislerp"

    @property
    def second_pass_enabled(self) -> bool:
        return self.upscale_factor > 1.0 and self.second_pass_steps > 0 and self.second_pass_denoise > 0.0

    @property
    def output_width(self) -> int:
        return _align8(self.width * self.upscale_factor) if self.second_pass_enabled else self.width

    @property
    def output_height(self) -> int:
        return _align8(self.height * self.upscale_factor) if self.second_pass_enabled else self.height

    @property
    def pass_count(self) -> int:
        return 2 if self.second_pass_enabled else 1

    def as_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload.update(
            {
                "second_pass_enabled": self.second_pass_enabled,
                "pass_count": self.pass_count,
                "output_width": self.output_width,
                "output_height": self.output_height,
            }
        )
        return payload


QUALITY_PROFILES: Dict[str, ImageQualitySettings] = {
    "draft": ImageQualitySettings(
        name="draft", width=1024, height=1024, steps=26, cfg_scale=6.0,
        sampler_name="dpmpp_2m_sde", scheduler="karras",
    ),
    "quality": ImageQualitySettings(
        name="quality", width=1024, height=1024, steps=36, cfg_scale=6.5,
        sampler_name="dpmpp_2m_sde", scheduler="karras",
    ),
    "detail": ImageQualitySettings(
        name="detail", width=1024, height=1024, steps=42, cfg_scale=6.0,
        sampler_name="dpmpp_3m_sde", scheduler="karras",
    ),
    # Hero deliberately remains opt-in. It keeps the proven 1024 SDXL base pass,
    # expands the latent to 1.5x, then performs a restrained low-denoise second
    # pass. This avoids a second model/refiner allocation and stays sequential on
    # the 12 GB target GPU while giving fine detail room to resolve at ~1536px.
    "hero": ImageQualitySettings(
        name="hero", width=1024, height=1024, steps=36, cfg_scale=6.5,
        sampler_name="dpmpp_2m_sde", scheduler="karras",
        upscale_factor=1.5,
        second_pass_steps=18,
        second_pass_cfg_scale=5.5,
        second_pass_sampler_name="dpmpp_2m_sde",
        second_pass_scheduler="karras",
        second_pass_denoise=0.24,
        latent_upscale_method="bislerp",
    ),
    "euler_reference": ImageQualitySettings(
        name="euler_reference", width=1024, height=1024, steps=30, cfg_scale=6.5,
        sampler_name="euler", scheduler="karras",
    ),
    "legacy_768_reference": ImageQualitySettings(
        name="legacy_768_reference", width=768, height=768, steps=30, cfg_scale=8.0,
        sampler_name="euler", scheduler="normal",
    ),
}


def _env_true(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _finite_float(value: Any, *, name: str, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number") from exc
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise ValueError(f"{name} must be finite and between {minimum:g} and {maximum:g}")
    return number


def _positive_int(value: Any, *, name: str, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= number <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return number


def profile_names() -> list[str]:
    return sorted(QUALITY_PROFILES)


def get_quality_profile(name: Optional[str] = None) -> ImageQualitySettings:
    requested = (name or os.getenv("EVAVO_IMAGE_QUALITY_PROFILE") or "quality").strip().lower()
    if requested == "custom":
        requested = "quality"
    profile = QUALITY_PROFILES.get(requested)
    if profile is None:
        raise ValueError(
            f"unknown image quality profile {requested!r}; available: {', '.join(profile_names())}, custom"
        )
    return profile


def resolve_quality_settings(
    *,
    quality_profile: Optional[str] = None,
    width: Any = None,
    height: Any = None,
    steps: Any = None,
    cfg_scale: Any = None,
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
) -> ImageQualitySettings:
    """Resolve a render profile plus explicit/env overrides.

    The previous canonical EVAVO call path always injected ``steps=24`` and
    ``cfg_scale=7`` even when a user supplied no quality settings. With
    ``EVAVO_UPGRADE_LEGACY_IMAGE_DEFAULTS`` enabled (the default), that exact
    legacy pair is treated as "unset" so old gateway/wrapper callers inherit the
    new production-quality profile. Use ``quality_profile="custom"`` to keep an
    intentional 24/7 request.

    The two-pass fields are intentionally independent from the first-pass fields.
    They default to disabled for every profile except ``hero``. This keeps normal
    production predictable while allowing a higher-resolution render to be
    benchmarked and promoted per subject instead of becoming a hidden cost.
    """

    raw_profile = (quality_profile or os.getenv("EVAVO_IMAGE_QUALITY_PROFILE") or "quality").strip().lower()
    custom = raw_profile == "custom"
    base = get_quality_profile("quality" if custom else raw_profile)

    if (
        not custom
        and _env_true("EVAVO_UPGRADE_LEGACY_IMAGE_DEFAULTS", True)
        and steps is not None
        and cfg_scale is not None
    ):
        try:
            legacy_pair = int(steps) == 24 and abs(float(cfg_scale) - 7.0) < 1e-9
        except (TypeError, ValueError):
            legacy_pair = False
        if legacy_pair:
            steps = None
            cfg_scale = None

    if width is None:
        width = os.getenv("EVAVO_IMAGE_WIDTH", base.width)
    if height is None:
        height = os.getenv("EVAVO_IMAGE_HEIGHT", base.height)
    if steps is None:
        steps = os.getenv("EVAVO_IMAGE_STEPS", base.steps)
    if cfg_scale is None:
        cfg_scale = os.getenv("EVAVO_IMAGE_CFG", base.cfg_scale)
    if sampler_name is None:
        sampler_name = os.getenv("EVAVO_IMAGE_SAMPLER", base.sampler_name)
    if scheduler is None:
        scheduler = os.getenv("EVAVO_IMAGE_SCHEDULER", base.scheduler)
    if denoise is None:
        denoise = os.getenv("EVAVO_IMAGE_DENOISE", base.denoise)

    if upscale_factor is None:
        upscale_factor = os.getenv("EVAVO_IMAGE_UPSCALE_FACTOR", base.upscale_factor)
    if second_pass_steps is None:
        second_pass_steps = os.getenv("EVAVO_IMAGE_SECOND_STEPS", base.second_pass_steps)
    if second_pass_cfg_scale is None:
        second_pass_cfg_scale = os.getenv(
            "EVAVO_IMAGE_SECOND_CFG",
            base.second_pass_cfg_scale if base.second_pass_cfg_scale is not None else base.cfg_scale,
        )
    if second_pass_sampler_name is None:
        second_pass_sampler_name = os.getenv(
            "EVAVO_IMAGE_SECOND_SAMPLER",
            base.second_pass_sampler_name or base.sampler_name,
        )
    if second_pass_scheduler is None:
        second_pass_scheduler = os.getenv(
            "EVAVO_IMAGE_SECOND_SCHEDULER",
            base.second_pass_scheduler or base.scheduler,
        )
    if second_pass_denoise is None:
        second_pass_denoise = os.getenv("EVAVO_IMAGE_SECOND_DENOISE", base.second_pass_denoise)
    if latent_upscale_method is None:
        latent_upscale_method = os.getenv("EVAVO_IMAGE_LATENT_UPSCALE_METHOD", base.latent_upscale_method)

    resolved = replace(
        base,
        name="custom" if custom else base.name,
        width=_positive_int(width, name="width", minimum=64, maximum=4096),
        height=_positive_int(height, name="height", minimum=64, maximum=4096),
        steps=_positive_int(steps, name="steps", minimum=1, maximum=200),
        cfg_scale=_finite_float(cfg_scale, name="cfg_scale", minimum=0.0, maximum=100.0),
        sampler_name=str(sampler_name).strip(),
        scheduler=str(scheduler).strip(),
        denoise=_finite_float(denoise, name="denoise", minimum=0.0, maximum=1.0),
        upscale_factor=_finite_float(upscale_factor, name="upscale_factor", minimum=1.0, maximum=2.0),
        second_pass_steps=_positive_int(second_pass_steps, name="second_pass_steps", minimum=0, maximum=100),
        second_pass_cfg_scale=_finite_float(
            second_pass_cfg_scale,
            name="second_pass_cfg_scale",
            minimum=0.0,
            maximum=100.0,
        ),
        second_pass_sampler_name=str(second_pass_sampler_name).strip(),
        second_pass_scheduler=str(second_pass_scheduler).strip(),
        second_pass_denoise=_finite_float(
            second_pass_denoise,
            name="second_pass_denoise",
            minimum=0.0,
            maximum=1.0,
        ),
        latent_upscale_method=str(latent_upscale_method).strip(),
    )
    if not resolved.sampler_name:
        raise ValueError("sampler_name must not be empty")
    if not resolved.scheduler:
        raise ValueError("scheduler must not be empty")
    if not resolved.second_pass_sampler_name:
        raise ValueError("second_pass_sampler_name must not be empty")
    if not resolved.second_pass_scheduler:
        raise ValueError("second_pass_scheduler must not be empty")
    if not resolved.latent_upscale_method:
        raise ValueError("latent_upscale_method must not be empty")
    if resolved.output_width > 4096 or resolved.output_height > 4096:
        raise ValueError(
            f"second-pass output {resolved.output_width}x{resolved.output_height} exceeds the 4096px safety limit"
        )
    return resolved


def recommended_sdxl_dimensions() -> Dict[str, tuple[int, int]]:
    """Useful ~1MP SDXL-native buckets for callers that need non-square output."""
    return {
        "1:1": (1024, 1024),
        "9:7": (1152, 896),
        "3:2": (1216, 832),
        "wide": (1344, 768),
        "portrait_wide": (768, 1344),
        "portrait_3:2": (832, 1216),
        "portrait_9:7": (896, 1152),
    }
