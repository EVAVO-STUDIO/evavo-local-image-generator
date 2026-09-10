#!/usr/bin/env python3
"""Inventory local EVAVO/ComfyUI model files without loading model tensors."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from evavo_local_image_generator.backends import ComfyUIBackend

MODEL_EXTENSIONS = {".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".gguf", ".onnx"}
CATEGORY_ALIASES = {
    "checkpoints": "checkpoint",
    "loras": "lora",
    "vae": "vae",
    "upscale_models": "upscaler",
    "controlnet": "controlnet",
    "clip": "text_encoder",
    "text_encoders": "text_encoder",
    "clip_vision": "vision_encoder",
    "diffusion_models": "diffusion_model",
    "unet": "diffusion_model",
    "audio_encoders": "audio_encoder",
    "model_patches": "model_patch",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safetensors_header(path: Path) -> dict[str, Any]:
    """Read only the bounded JSON header from a SafeTensors file."""
    try:
        with path.open("rb") as handle:
            raw_length = handle.read(8)
            if len(raw_length) != 8:
                return {"ok": False, "error": "missing 8-byte header length"}
            length = struct.unpack("<Q", raw_length)[0]
            if length <= 1 or length > 64 * 1024 * 1024:
                return {"ok": False, "error": f"unsafe/invalid SafeTensors header length: {length}"}
            raw = handle.read(length)
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, struct.error) as exc:
        return {"ok": False, "error": str(exc)}
    if not isinstance(value, dict):
        return {"ok": False, "error": "SafeTensors header root is not an object"}
    metadata = value.get("__metadata__")
    metadata = metadata if isinstance(metadata, dict) else {}
    tensor_count = sum(1 for key, item in value.items() if key != "__metadata__" and isinstance(item, dict))
    selected_keys = (
        "modelspec.architecture",
        "modelspec.title",
        "modelspec.description",
        "modelspec.sai_model_spec",
        "modelspec.implementation",
        "ss_base_model_version",
        "ss_network_module",
        "ss_network_dim",
        "ss_network_alpha",
        "format",
    )
    selected = {key: metadata[key] for key in selected_keys if key in metadata}
    return {
        "ok": True,
        "header_bytes": length,
        "tensor_count": tensor_count,
        "metadata": selected,
        "metadata_key_count": len(metadata),
    }


def _architecture_hint(filename: str, header: dict[str, Any] | None) -> dict[str, Any]:
    metadata = header.get("metadata", {}) if isinstance(header, dict) else {}
    haystack = " ".join(
        [filename, *[str(value) for value in metadata.values()]]
    ).lower()
    hints: list[str] = []
    if any(token in haystack for token in ("sdxl", "stable-diffusion-xl", "stable diffusion xl")):
        hints.append("sdxl")
    if any(token in haystack for token in ("sd1.5", "sd15", "stable-diffusion-v1", "v1-5")):
        hints.append("sd15")
    if "flux" in haystack:
        hints.append("flux")
    if "hunyuan" in haystack:
        hints.append("hunyuan")
    if "sd3" in haystack or "stable diffusion 3" in haystack:
        hints.append("sd3")
    if "pony" in haystack:
        hints.append("pony")
    if "lora" in haystack or metadata.get("ss_network_module"):
        hints.append("lora")
    return {
        "hints": sorted(set(hints)),
        "warning": "Architecture is a filename/metadata hint only; validate the model in its intended workflow before production use.",
    }


def _category(models_root: Path, path: Path) -> str:
    try:
        relative = path.relative_to(models_root)
    except ValueError:
        return "model"
    first = relative.parts[0].lower() if len(relative.parts) > 1 else models_root.name.lower()
    return CATEGORY_ALIASES.get(first, first or "model")


def _scan_root(root: Path, *, include_hash: bool) -> tuple[list[dict[str, Any]], list[str]]:
    models: list[dict[str, Any]] = []
    warnings: list[str] = []
    if not root.is_dir():
        return models, [f"model root not found: {root}"]

    for path in sorted(root.rglob("*"), key=lambda value: str(value).lower()):
        try:
            if not path.is_file() or path.is_symlink() or path.suffix.lower() not in MODEL_EXTENSIONS:
                continue
            stat = path.stat()
        except OSError as exc:
            warnings.append(f"could not inspect {path}: {exc}")
            continue
        header = _safetensors_header(path) if path.suffix.lower() == ".safetensors" else None
        receipt: dict[str, Any] = {
            "name": path.name,
            "path": str(path.resolve()),
            "relative_path": str(path.relative_to(root)).replace("\\", "/"),
            "root": str(root.resolve()),
            "category": _category(root, path),
            "extension": path.suffix.lower(),
            "bytes": stat.st_size,
            "size_gib": round(stat.st_size / (1024**3), 4),
            "modified_ns": stat.st_mtime_ns,
            "safetensors": header,
            "architecture": _architecture_hint(path.name, header),
        }
        if include_hash:
            try:
                receipt["sha256"] = _sha256(path)
            except OSError as exc:
                receipt["hash_error"] = str(exc)
                warnings.append(f"could not hash {path}: {exc}")
        models.append(receipt)
    return models, warnings


def _live_inventory(endpoint: str) -> dict[str, Any]:
    backend = ComfyUIBackend(endpoint)
    try:
        health = backend.health()
        checkpoints = backend.checkpoints()
        sampling = backend.sampling_inventory()
        loras = sampling.get("loras", []) if isinstance(sampling, dict) else []
        return {
            "ok": True,
            "endpoint": backend.endpoint,
            "health": health,
            "checkpoints": checkpoints,
            "loras": loras,
        }
    except Exception as exc:
        return {"ok": False, "endpoint": endpoint, "error": str(exc)}


def _mark_live_visibility(models: list[dict[str, Any]], live: dict[str, Any]) -> None:
    checkpoint_names = {str(value).replace("\\", "/").lower() for value in live.get("checkpoints", []) if isinstance(value, str)}
    lora_names = {str(value).replace("\\", "/").lower() for value in live.get("loras", []) if isinstance(value, str)}
    for model in models:
        relative = str(model.get("relative_path", "")).replace("\\", "/").lower()
        name = str(model.get("name", "")).lower()
        category = model.get("category")
        if category == "checkpoint":
            visible = relative in checkpoint_names or name in checkpoint_names or any(value.endswith("/" + name) for value in checkpoint_names)
        elif category == "lora":
            visible = relative in lora_names or name in lora_names or any(value.endswith("/" + name) for value in lora_names)
        else:
            visible = None
        model["live_comfyui_visible"] = visible


def _duplicates(models: list[dict[str, Any]], include_hash: bool) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for model in models:
        if include_hash and model.get("sha256"):
            key = ("sha256", model["sha256"])
        else:
            key = ("possible", model.get("name", "").lower(), model.get("bytes"))
        groups.setdefault(key, []).append(model)
    result = []
    for key, values in groups.items():
        if len(values) < 2:
            continue
        result.append(
            {
                "certainty": "exact" if key[0] == "sha256" else "possible",
                "key": key[1:],
                "paths": [value["path"] for value in values],
            }
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Inventory EVAVO/ComfyUI local model files")
    parser.add_argument("--root", action="append", default=[], help="Model root to scan; can be repeated")
    parser.add_argument("--endpoint", default=os.getenv("COMFYUI_ENDPOINT", "http://127.0.0.1:8188"))
    parser.add_argument("--no-live", action="store_true", help="Skip live ComfyUI inventory comparison")
    parser.add_argument("--hash", action="store_true", help="Compute full SHA-256 for model bytes (slow for large weights)")
    parser.add_argument("--output", default=str(Path(".evavo") / "model-inventory.json"))
    args = parser.parse_args()

    roots = [Path(value).expanduser().resolve() for value in args.root if str(value).strip()]
    if not roots:
        for value in (r"C:\AI\ComfyUI\models", r"C:\AI\ComfyUI-next\models"):
            path = Path(value)
            if path.is_dir():
                roots.append(path.resolve())
    if not roots:
        print(json.dumps({"ok": False, "error": "no model roots found; pass --root"}, indent=2))
        return 2

    all_models: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen_paths: set[str] = set()
    for root in roots:
        models, root_warnings = _scan_root(root, include_hash=args.hash)
        warnings.extend(root_warnings)
        for model in models:
            normalized = os.path.normcase(os.path.normpath(model["path"]))
            if normalized in seen_paths:
                continue
            seen_paths.add(normalized)
            all_models.append(model)

    live = {"ok": False, "skipped": True} if args.no_live else _live_inventory(args.endpoint)
    if live.get("ok"):
        _mark_live_visibility(all_models, live)

    counts: dict[str, int] = {}
    bytes_by_category: dict[str, int] = {}
    for model in all_models:
        category = str(model.get("category", "model"))
        counts[category] = counts.get(category, 0) + 1
        bytes_by_category[category] = bytes_by_category.get(category, 0) + int(model.get("bytes", 0))

    payload = {
        "schema_version": 1,
        "captured_at": datetime.now().astimezone().isoformat(),
        "roots": [str(root) for root in roots],
        "hashes_computed": bool(args.hash),
        "model_count": len(all_models),
        "counts_by_category": dict(sorted(counts.items())),
        "gib_by_category": {key: round(value / (1024**3), 4) for key, value in sorted(bytes_by_category.items())},
        "live_comfyui": live,
        "duplicates": _duplicates(all_models, args.hash),
        "warnings": warnings,
        "models": all_models,
        "interpretation_warning": "Metadata/filename architecture hints are not compatibility certification. Validate each model in a controlled workflow before production use.",
    }
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"ok": True, "output": str(output), "model_count": len(all_models), "counts_by_category": payload["counts_by_category"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
