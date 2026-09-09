"""Technical diagnostics for generated image quality review.

These metrics are deliberately descriptive signals rather than aesthetic scores.
They help catch clipping, flatness, unexpected resolution changes, over/under
exposure and loss of local detail, but human review remains authoritative for
composition, anatomy, geometry, materials and production usability.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict

import numpy as np
from PIL import Image


def _finite(value: float) -> float:
    return float(value) if math.isfinite(float(value)) else 0.0


def _entropy_8bit(values: np.ndarray) -> float:
    quantized = np.clip(np.rint(values * 255.0), 0, 255).astype(np.uint8)
    histogram = np.bincount(quantized.ravel(), minlength=256).astype(np.float64)
    total = float(histogram.sum())
    if total <= 0.0:
        return 0.0
    probability = histogram[histogram > 0] / total
    return _finite(float(-(probability * np.log2(probability)).sum()))


def image_quality_diagnostics(path: str | Path) -> Dict[str, Any]:
    """Return stable technical image diagnostics for a generated artifact."""

    image_path = Path(path).expanduser().resolve(strict=True)
    if not image_path.is_file():
        raise ValueError(f"image path is not an ordinary file: {image_path}")

    try:
        with Image.open(image_path) as source:
            source.load()
            image = source.convert("RGB")
    except (OSError, ValueError) as exc:
        raise ValueError(f"could not decode image {image_path}: {exc}") from exc

    rgb = np.asarray(image, dtype=np.float32) / np.float32(255.0)
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError(f"decoded image has an unexpected shape: {rgb.shape}")

    height, width, _ = rgb.shape
    # Rec. 709 luminance coefficients suit the sRGB-like output used by the
    # current generation stack well enough for robust technical diagnostics.
    luminance = (
        rgb[:, :, 0] * np.float32(0.2126)
        + rgb[:, :, 1] * np.float32(0.7152)
        + rgb[:, :, 2] * np.float32(0.0722)
    )
    saturation_proxy = rgb.max(axis=2) - rgb.min(axis=2)

    horizontal = np.abs(np.diff(luminance, axis=1)) if width > 1 else np.zeros((height, 1), dtype=np.float32)
    vertical = np.abs(np.diff(luminance, axis=0)) if height > 1 else np.zeros((1, width), dtype=np.float32)
    local_detail_energy = (float(horizontal.mean()) + float(vertical.mean())) / 2.0

    metrics: Dict[str, Any] = {
        "width": int(width),
        "height": int(height),
        "megapixels": round((width * height) / 1_000_000.0, 6),
        "file_bytes": int(image_path.stat().st_size),
        "luminance_mean": round(_finite(float(luminance.mean())), 6),
        "luminance_std": round(_finite(float(luminance.std())), 6),
        "near_black_fraction": round(_finite(float(np.mean(luminance <= 0.02))), 6),
        "near_white_fraction": round(_finite(float(np.mean(luminance >= 0.98))), 6),
        "saturation_proxy_mean": round(_finite(float(saturation_proxy.mean())), 6),
        "luminance_entropy_bits": round(_entropy_8bit(luminance), 6),
        "local_detail_energy": round(_finite(local_detail_energy), 6),
    }
    return metrics
