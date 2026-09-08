"""Native ComfyUI backend adapter used by EVAVO generation tooling."""

from __future__ import annotations

import json
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional


class ComfyUIBackend:
    """Small standard-library client for a local ComfyUI server."""

    def __init__(self, endpoint: Optional[str] = None):
        self.endpoint = (endpoint or os.getenv("EVAVO_COMFYUI_ENDPOINT") or os.getenv("COMFYUI_ENDPOINT") or "http://127.0.0.1:8188").rstrip("/")

    def _request(self, path: str, *, method: str = "GET", payload: Optional[Dict[str, Any]] = None, timeout: float = 10.0) -> Dict[str, Any]:
        body = None
        headers = {"Accept": "application/json", "User-Agent": "EVAVO-ComfyUI/1"}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(f"{self.endpoint}{path}", data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise RuntimeError(f"COMFYUI_HTTP_ERROR:{exc.code}:{detail or exc.reason}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(f"COMFYUI_CONNECTION_ERROR:{exc}") from exc
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("COMFYUI_INVALID_JSON:server returned invalid JSON") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError("COMFYUI_INVALID_RESPONSE:expected a JSON object")
        return parsed

    def health(self) -> Dict[str, Any]:
        stats = self._request("/system_stats", timeout=5.0)
        system = stats.get("system") if isinstance(stats.get("system"), dict) else {}
        devices = stats.get("devices") if isinstance(stats.get("devices"), list) else []
        return {
            "healthy": True,
            "status": "ready",
            "mode": "native-comfyui",
            "endpoint": self.endpoint,
            "comfyui_version": system.get("comfyui_version"),
            "python_version": system.get("python_version"),
            "devices": devices,
        }

    def health_check(self) -> bool:
        try:
            return bool(self.health().get("healthy"))
        except RuntimeError:
            return False

    def object_info(self, node_class: Optional[str] = None) -> Dict[str, Any]:
        suffix = f"/{urllib.parse.quote(node_class)}" if node_class else ""
        return self._request(f"/object_info{suffix}", timeout=15.0)

    def checkpoints(self) -> List[str]:
        info = self.object_info("CheckpointLoaderSimple")
        node = info.get("CheckpointLoaderSimple") if isinstance(info.get("CheckpointLoaderSimple"), dict) else info
        required = node.get("input", {}).get("required", {}) if isinstance(node, dict) else {}
        spec = required.get("ckpt_name") if isinstance(required, dict) else None
        if isinstance(spec, list) and spec:
            values = spec[0]
            if isinstance(values, list):
                return [str(value) for value in values if isinstance(value, str) and value]
        return []

    def choose_checkpoint(self, requested: Optional[str] = None) -> str:
        checkpoints = self.checkpoints()
        preferred = requested or os.getenv("EVAVO_COMFYUI_CHECKPOINT")
        if preferred:
            if preferred in checkpoints:
                return preferred
            raise RuntimeError(f"COMFYUI_CHECKPOINT_NOT_FOUND:{preferred}")
        if not checkpoints:
            raise RuntimeError("COMFYUI_NO_CHECKPOINTS:no checkpoints reported by CheckpointLoaderSimple")
        return checkpoints[0]

    @staticmethod
    def _dimension(value: Any, default: int) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = default
        if number < 64 or number > 4096:
            raise ValueError("width/height must be between 64 and 4096")
        return max(64, number - (number % 8))

    def build_txt2img_workflow(self, prompt: str, *, negative_prompt: str = "", width: int = 1024, height: int = 1024, steps: int = 24, cfg_scale: float = 7.0, seed: Optional[int] = None, checkpoint: Optional[str] = None, filename_prefix: str = "EVAVO") -> Dict[str, Any]:
        width = self._dimension(width, 1024)
        height = self._dimension(height, 1024)
        steps = max(1, min(200, int(steps)))
        cfg_scale = float(cfg_scale)
        if not 0.0 <= cfg_scale <= 100.0:
            raise ValueError("cfg_scale must be between 0 and 100")
        chosen_checkpoint = self.choose_checkpoint(checkpoint)
        seed_value = int(seed) if seed is not None else secrets.randbits(63)
        safe_prefix = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in filename_prefix)[:120] or "EVAVO"
        return {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": chosen_checkpoint}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": negative_prompt, "clip": ["1", 1]}},
            "4": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
            "5": {"class_type": "KSampler", "inputs": {"seed": seed_value, "steps": steps, "cfg": cfg_scale, "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0, "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0]}},
            "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
            "7": {"class_type": "SaveImage", "inputs": {"filename_prefix": safe_prefix, "images": ["6", 0]}},
        }

    def queue_image(self, prompt: str, *, project_name: str = "batch_gen", negative_prompt: str = "", width: int = 1024, height: int = 1024, steps: int = 24, cfg_scale: float = 7.0, seed: Optional[int] = None, checkpoint: Optional[str] = None) -> Dict[str, Any]:
        workflow = self.build_txt2img_workflow(
            prompt,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            steps=steps,
            cfg_scale=cfg_scale,
            seed=seed,
            checkpoint=checkpoint,
            filename_prefix=f"EVAVO/{project_name}",
        )
        response = self._request("/prompt", method="POST", payload={"prompt": workflow}, timeout=30.0)
        prompt_id = response.get("prompt_id")
        if not isinstance(prompt_id, str) or not prompt_id:
            errors = response.get("node_errors")
            raise RuntimeError(f"COMFYUI_QUEUE_REJECTED:{errors or response}")
        return {
            "status": "queued",
            "task_id": prompt_id,
            "prompt_id": prompt_id,
            "project_name": project_name,
            "checkpoint": workflow["1"]["inputs"]["ckpt_name"],
            "backend_mode": "native-comfyui",
        }

    def history(self, prompt_id: str) -> Dict[str, Any]:
        return self._request(f"/history/{urllib.parse.quote(prompt_id)}", timeout=15.0)

    def outputs(self, prompt_id: str) -> List[Dict[str, str]]:
        history = self.history(prompt_id)
        entry = history.get(prompt_id)
        if not isinstance(entry, dict):
            return []
        outputs = entry.get("outputs")
        if not isinstance(outputs, dict):
            return []
        found: List[Dict[str, str]] = []
        for node_output in outputs.values():
            if not isinstance(node_output, dict):
                continue
            images = node_output.get("images")
            if not isinstance(images, list):
                continue
            for image in images:
                if isinstance(image, dict) and isinstance(image.get("filename"), str):
                    found.append({
                        "filename": image["filename"],
                        "subfolder": str(image.get("subfolder", "")),
                        "type": str(image.get("type", "output")),
                    })
        return found

    def __repr__(self) -> str:
        return f"ComfyUIBackend(endpoint={self.endpoint!r})"
