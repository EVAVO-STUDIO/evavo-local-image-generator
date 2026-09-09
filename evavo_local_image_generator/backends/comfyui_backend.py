"""Native ComfyUI backend adapter used by EVAVO generation tooling."""

from __future__ import annotations

import json
import math
import os
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


MODEL_LOADER_INPUTS: Dict[str, Tuple[str, str]] = {
    "checkpoints": ("CheckpointLoaderSimple", "ckpt_name"),
    "loras": ("LoraLoader", "lora_name"),
    "vae": ("VAELoader", "vae_name"),
    "controlnet": ("ControlNetLoader", "control_net_name"),
    "diffusion_models": ("UNETLoader", "unet_name"),
    "text_encoders": ("CLIPLoader", "clip_name"),
    "clip_vision": ("CLIPVisionLoader", "clip_name"),
    "upscale_models": ("UpscaleModelLoader", "model_name"),
}
SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


def _has_image_signature(path: Path, suffix: str) -> bool:
    try:
        with path.open("rb") as handle:
            head = handle.read(12)
    except OSError:
        return False
    suffix = suffix.lower()
    if suffix == ".png":
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    if suffix in {".jpg", ".jpeg"}:
        return head.startswith(b"\xff\xd8\xff")
    if suffix == ".gif":
        return head.startswith((b"GIF87a", b"GIF89a"))
    if suffix == ".webp":
        return len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    return False


class ComfyUIBackend:
    """Small standard-library client for a local ComfyUI server."""

    def __init__(self, endpoint: Optional[str] = None):
        self.endpoint = (endpoint or os.getenv("COMFYUI_ENDPOINT") or os.getenv("EVAVO_COMFYUI_ENDPOINT") or "http://127.0.0.1:8188").rstrip("/")

    def _open(self, path: str, *, method: str = "GET", payload: Optional[Dict[str, Any]] = None, timeout: float = 10.0):
        body = None
        headers = {"Accept": "application/json", "User-Agent": "EVAVO-ComfyUI/1"}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(f"{self.endpoint}{path}", data=body, headers=headers, method=method)
        try:
            return urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise RuntimeError(f"COMFYUI_HTTP_ERROR:{exc.code}:{detail or exc.reason}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(f"COMFYUI_CONNECTION_ERROR:{exc}") from exc

    def _request(self, path: str, *, method: str = "GET", payload: Optional[Dict[str, Any]] = None, timeout: float = 10.0) -> Dict[str, Any]:
        with self._open(path, method=method, payload=payload, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
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

    @staticmethod
    def _extract_choice_values(info: Dict[str, Any], node_class: str, input_name: str) -> List[str]:
        node = info.get(node_class) if isinstance(info.get(node_class), dict) else info
        if not isinstance(node, dict):
            return []
        inputs = node.get("input")
        if not isinstance(inputs, dict):
            return []
        for section_name in ("required", "optional"):
            section = inputs.get(section_name)
            if not isinstance(section, dict):
                continue
            spec = section.get(input_name)
            if isinstance(spec, list) and spec:
                values = spec[0]
                if isinstance(values, list):
                    return [str(value) for value in values if isinstance(value, str) and value]
        return []

    def node_input_choices(self, node_class: str, input_name: str) -> List[str]:
        info = self.object_info(node_class)
        return self._extract_choice_values(info, node_class, input_name)

    def checkpoints(self) -> List[str]:
        try:
            return self.node_input_choices("CheckpointLoaderSimple", "ckpt_name")
        except RuntimeError as exc:
            if str(exc).startswith("COMFYUI_HTTP_ERROR:404:"):
                return []
            raise

    def model_inventory(self, limit_per_category: int = 200) -> Dict[str, Any]:
        try:
            limit = int(limit_per_category)
        except (TypeError, ValueError) as exc:
            raise ValueError("limit_per_category must be an integer") from exc
        limit = max(1, min(5000, limit))
        categories: Dict[str, Any] = {}
        total_items = 0
        available_categories = 0
        for category, (node_class, input_name) in MODEL_LOADER_INPUTS.items():
            try:
                values = self.node_input_choices(node_class, input_name)
            except RuntimeError as exc:
                categories[category] = {
                    "available": False,
                    "node_class": node_class,
                    "input_name": input_name,
                    "count": 0,
                    "items": [],
                    "error": str(exc),
                }
                continue
            available_categories += 1
            total_items += len(values)
            categories[category] = {
                "available": True,
                "node_class": node_class,
                "input_name": input_name,
                "count": len(values),
                "items": values[:limit],
                "truncated": len(values) > limit,
            }
        return {
            "endpoint": self.endpoint,
            "available_categories": available_categories,
            "total_categories": len(MODEL_LOADER_INPUTS),
            "total_items": total_items,
            "limit_per_category": limit,
            "categories": categories,
        }

    @staticmethod
    def _truthy_environment(name: str, default: bool = False) -> bool:
        raw = os.getenv(name)
        if raw is None:
            return default
        return raw.strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _checkpoint_source_configured() -> bool:
        return bool(os.getenv("EVAVO_CHECKPOINT_FILE") or os.getenv("EVAVO_CHECKPOINT_URL"))

    def _provision_configured_checkpoint(self) -> bool:
        if not self._truthy_environment("EVAVO_AUTO_PROVISION_CHECKPOINT", default=False):
            return False
        if not self._checkpoint_source_configured():
            return False
        repo_root = Path(__file__).resolve().parents[2]
        provisioner = repo_root / "provision-comfyui.py"
        if not provisioner.is_file():
            raise RuntimeError(f"COMFYUI_CHECKPOINT_PROVISIONER_MISSING:{provisioner}")
        command = [sys.executable, str(provisioner), "--checkpoint-only", "--json"]
        try:
            result = subprocess.run(command, cwd=str(repo_root), capture_output=True, text=True, timeout=3600)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("COMFYUI_CHECKPOINT_PROVISION_TIMEOUT:checkpoint provisioning exceeded one hour") from exc
        except OSError as exc:
            raise RuntimeError(f"COMFYUI_CHECKPOINT_PROVISION_PROCESS:{exc}") from exc
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            detail = (result.stderr or result.stdout).strip()[-2000:]
            raise RuntimeError(f"COMFYUI_CHECKPOINT_PROVISION_INVALID_JSON:{detail}") from exc
        if not isinstance(payload, dict) or result.returncode != 0 or not payload.get("ok"):
            detail = payload.get("message") if isinstance(payload, dict) else None
            raise RuntimeError(f"COMFYUI_CHECKPOINT_PROVISION_FAILED:{detail or result.stderr or result.stdout}")
        return True

    def choose_checkpoint(self, requested: Optional[str] = None, *, allow_repair: bool = True) -> str:
        checkpoints = self.checkpoints()
        preferred = requested or os.getenv("EVAVO_COMFYUI_CHECKPOINT")
        missing = (preferred is not None and preferred not in checkpoints) or (preferred is None and not checkpoints)
        if missing and allow_repair and self._provision_configured_checkpoint():
            checkpoints = self.checkpoints()

        if preferred:
            if preferred in checkpoints:
                return preferred
            raise RuntimeError(f"COMFYUI_CHECKPOINT_NOT_FOUND:{preferred}")
        if not checkpoints:
            raise RuntimeError(
                "COMFYUI_NO_CHECKPOINTS:no checkpoints reported by CheckpointLoaderSimple; "
                "configure EVAVO_CHECKPOINT_FILE/URL, EVAVO_SHARED_MODEL_ROOTS, or use a custom workflow"
            )
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

    @staticmethod
    def _replace_template(value: Any, replacements: Dict[str, Any]) -> Any:
        if isinstance(value, dict):
            return {key: ComfyUIBackend._replace_template(item, replacements) for key, item in value.items()}
        if isinstance(value, list):
            return [ComfyUIBackend._replace_template(item, replacements) for item in value]
        if isinstance(value, str):
            if value in replacements:
                return replacements[value]
            result = value
            for placeholder, replacement in replacements.items():
                result = result.replace(placeholder, str(replacement))
            return result
        return value

    def load_workflow_template(self, path: str | Path, replacements: Dict[str, Any]) -> Dict[str, Any]:
        workflow_path = Path(path).expanduser().resolve()
        try:
            payload = json.loads(workflow_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise RuntimeError(f"COMFYUI_WORKFLOW_NOT_FOUND:{workflow_path}") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"COMFYUI_WORKFLOW_INVALID:{workflow_path}:{exc}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("COMFYUI_WORKFLOW_INVALID:workflow root must be a JSON object")
        rendered = self._replace_template(payload, replacements)
        if not isinstance(rendered, dict) or not rendered:
            raise RuntimeError("COMFYUI_WORKFLOW_INVALID:rendered workflow is empty")
        return rendered

    @staticmethod
    def _workflow_replacements(
        *,
        prompt: str,
        negative_prompt: str,
        checkpoint: str,
        width: int,
        height: int,
        steps: int,
        cfg_scale: float,
        seed: int,
        filename_prefix: str,
    ) -> Dict[str, Any]:
        values: Dict[str, Any] = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "checkpoint": checkpoint,
            "width": width,
            "height": height,
            "steps": steps,
            "cfg_scale": cfg_scale,
            "seed": seed,
            "filename_prefix": filename_prefix,
        }
        replacements: Dict[str, Any] = {}
        for name, value in values.items():
            replacements[f"{{{{{name}}}}}"] = value
            replacements[f"{{{{{name.upper()}}}}}"] = value
        replacements["{{CFG}}"] = cfg_scale
        replacements["{{cfg}}"] = cfg_scale
        return replacements

    @staticmethod
    def _workflow_choice_values(spec: Any) -> List[str]:
        if not isinstance(spec, list) or not spec or not isinstance(spec[0], list):
            return []
        return [str(value) for value in spec[0] if isinstance(value, str) and value]

    def preflight_workflow(self, workflow: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(workflow, dict) or not workflow:
            raise RuntimeError("COMFYUI_WORKFLOW_PREFLIGHT_FAILED:workflow must be a non-empty object")

        info = self.object_info()
        missing_nodes: List[Dict[str, str]] = []
        malformed_nodes: List[Dict[str, str]] = []
        missing_inputs: List[Dict[str, str]] = []
        invalid_choices: List[Dict[str, Any]] = []
        node_classes = set()

        for node_id, node in workflow.items():
            node_key = str(node_id)
            if not isinstance(node, dict):
                malformed_nodes.append({"node_id": node_key, "reason": "node must be an object"})
                continue
            class_type = node.get("class_type")
            inputs = node.get("inputs")
            if not isinstance(class_type, str) or not class_type:
                malformed_nodes.append({"node_id": node_key, "reason": "class_type is missing"})
                continue
            node_classes.add(class_type)
            if not isinstance(inputs, dict):
                malformed_nodes.append({"node_id": node_key, "reason": "inputs must be an object"})
                continue

            definition = info.get(class_type)
            if not isinstance(definition, dict):
                missing_nodes.append({"node_id": node_key, "class_type": class_type})
                continue
            input_definition = definition.get("input")
            if not isinstance(input_definition, dict):
                continue

            required = input_definition.get("required")
            if isinstance(required, dict):
                for input_name in required:
                    if input_name not in inputs:
                        missing_inputs.append({"node_id": node_key, "class_type": class_type, "input": str(input_name)})

            for section_name in ("required", "optional"):
                section = input_definition.get(section_name)
                if not isinstance(section, dict):
                    continue
                for input_name, spec in section.items():
                    if input_name not in inputs:
                        continue
                    value = inputs[input_name]
                    choices = self._workflow_choice_values(spec)
                    if choices and isinstance(value, str) and value not in choices:
                        invalid_choices.append({
                            "node_id": node_key,
                            "class_type": class_type,
                            "input": str(input_name),
                            "value": value,
                            "available_count": len(choices),
                            "available": choices[:20],
                            "truncated": len(choices) > 20,
                        })

        result: Dict[str, Any] = {
            "ok": not (missing_nodes or malformed_nodes or missing_inputs or invalid_choices),
            "node_count": len(workflow),
            "node_classes": sorted(node_classes),
            "missing_nodes": missing_nodes,
            "malformed_nodes": malformed_nodes,
            "missing_inputs": missing_inputs,
            "invalid_choices": invalid_choices,
        }
        if not result["ok"]:
            raise RuntimeError("COMFYUI_WORKFLOW_PREFLIGHT_FAILED:" + json.dumps(result, ensure_ascii=False, sort_keys=True))
        return result

    def build_txt2img_workflow(self, prompt: str, *, negative_prompt: str = "", width: int = 1024, height: int = 1024, steps: int = 24, cfg_scale: float = 7.0, seed: Optional[int] = None, checkpoint: Optional[str] = None, filename_prefix: str = "EVAVO", workflow_path: Optional[str] = None) -> Dict[str, Any]:
        width = self._dimension(width, 1024)
        height = self._dimension(height, 1024)
        steps = max(1, min(200, int(steps)))
        cfg_scale = float(cfg_scale)
        if not math.isfinite(cfg_scale) or not 0.0 <= cfg_scale <= 100.0:
            raise ValueError("cfg_scale must be finite and between 0 and 100")
        seed_value = int(seed) if seed is not None else secrets.randbits(63)
        safe_prefix = "".join(ch if ch.isalnum() or ch in "_-/" else "_" for ch in filename_prefix)[:120] or "EVAVO"
        template_path = workflow_path or os.getenv("EVAVO_COMFYUI_WORKFLOW")

        if template_path:
            preferred = checkpoint or os.getenv("EVAVO_COMFYUI_CHECKPOINT")
            if preferred:
                try:
                    chosen_checkpoint = self.choose_checkpoint(preferred, allow_repair=False)
                except RuntimeError:
                    chosen_checkpoint = preferred
            else:
                available = self.checkpoints()
                chosen_checkpoint = available[0] if available else ""
        else:
            chosen_checkpoint = self.choose_checkpoint(checkpoint, allow_repair=True)

        replacements = self._workflow_replacements(
            prompt=prompt,
            negative_prompt=negative_prompt,
            checkpoint=chosen_checkpoint,
            width=width,
            height=height,
            steps=steps,
            cfg_scale=cfg_scale,
            seed=seed_value,
            filename_prefix=safe_prefix,
        )
        if template_path:
            return self.load_workflow_template(template_path, replacements)

        return {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": chosen_checkpoint}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": negative_prompt, "clip": ["1", 1]}},
            "4": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
            "5": {"class_type": "KSampler", "inputs": {"seed": seed_value, "steps": steps, "cfg": cfg_scale, "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0, "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0]}},
            "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
            "7": {"class_type": "SaveImage", "inputs": {"filename_prefix": safe_prefix, "images": ["6", 0]}},
        }

    def queue_image(self, prompt: str, *, project_name: str = "batch_gen", negative_prompt: str = "", width: int = 1024, height: int = 1024, steps: int = 24, cfg_scale: float = 7.0, seed: Optional[int] = None, checkpoint: Optional[str] = None, workflow_path: Optional[str] = None) -> Dict[str, Any]:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be a non-empty string")
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
        )
        if template_path and self._truthy_environment("EVAVO_PREFLIGHT_CUSTOM_WORKFLOW", default=True):
            self.preflight_workflow(workflow)
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
            "checkpoint": checkpoint or os.getenv("EVAVO_COMFYUI_CHECKPOINT") or self._workflow_checkpoint(workflow),
            "backend_mode": "native-comfyui",
        }

    @staticmethod
    def _workflow_checkpoint(workflow: Dict[str, Any]) -> Optional[str]:
        for node in workflow.values():
            if not isinstance(node, dict) or node.get("class_type") != "CheckpointLoaderSimple":
                continue
            inputs = node.get("inputs")
            if isinstance(inputs, dict) and isinstance(inputs.get("ckpt_name"), str):
                return inputs["ckpt_name"]
        return None

    def history(self, prompt_id: str) -> Dict[str, Any]:
        if not isinstance(prompt_id, str) or not prompt_id:
            raise ValueError("prompt_id must be a non-empty string")
        return self._request(f"/history/{urllib.parse.quote(prompt_id, safe='')}", timeout=15.0)

    @staticmethod
    def _outputs_from_history(history: Dict[str, Any], prompt_id: str) -> List[Dict[str, str]]:
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

    def outputs(self, prompt_id: str) -> List[Dict[str, str]]:
        return self._outputs_from_history(self.history(prompt_id), prompt_id)

    def wait_for_outputs(self, prompt_id: str, *, timeout: float = 600.0, interval: float = 1.0) -> List[Dict[str, str]]:
        try:
            timeout = float(timeout)
            interval = float(interval)
        except (TypeError, ValueError) as exc:
            raise ValueError("timeout/interval must be numbers") from exc
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be finite and greater than zero")
        if not math.isfinite(interval) or interval < 0.1:
            raise ValueError("interval must be finite and at least 0.1 seconds")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            history = self.history(prompt_id)
            entry = history.get(prompt_id)
            if isinstance(entry, dict):
                outputs = self._outputs_from_history(history, prompt_id)
                if outputs:
                    return outputs
                status = entry.get("status")
                if isinstance(status, dict):
                    messages = status.get("messages")
                    if status.get("completed") is False and messages:
                        raise RuntimeError(f"COMFYUI_EXECUTION_FAILED:{messages}")
            time.sleep(interval)
        raise RuntimeError(f"COMFYUI_WAIT_TIMEOUT:{prompt_id}:{timeout:g}s")

    def download_output(self, output: Dict[str, str], target_dir: str | Path, *, max_bytes: int = 256 * 1024 * 1024) -> str:
        filename = output.get("filename")
        if not isinstance(filename, str) or not filename or "\x00" in filename:
            raise ValueError("output filename is missing or invalid")
        safe_name = Path(filename).name
        if safe_name in {"", ".", ".."}:
            raise ValueError("output filename is invalid")
        suffix = Path(safe_name).suffix.lower()
        if suffix not in SUPPORTED_IMAGE_SUFFIXES:
            raise RuntimeError(f"COMFYUI_OUTPUT_TYPE_UNSUPPORTED:{safe_name}")
        try:
            max_bytes = int(max_bytes)
        except (TypeError, ValueError) as exc:
            raise ValueError("max_bytes must be an integer") from exc
        if max_bytes <= 0:
            raise ValueError("max_bytes must be greater than zero")

        destination_dir = Path(target_dir).expanduser().resolve()
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / safe_name
        query = urllib.parse.urlencode({
            "filename": filename,
            "subfolder": output.get("subfolder", ""),
            "type": output.get("type", "output"),
        })
        fd, temp_name = tempfile.mkstemp(prefix=safe_name + ".", suffix=".part", dir=str(destination_dir))
        total = 0
        try:
            with os.fdopen(fd, "wb") as handle, self._open(f"/view?{query}", timeout=60.0) as response:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        raise RuntimeError(f"COMFYUI_OUTPUT_TOO_LARGE:{safe_name}")
                    handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
            temp_path = Path(temp_name)
            if total <= 0 or temp_path.stat().st_size <= 0:
                raise RuntimeError(f"COMFYUI_OUTPUT_EMPTY:{safe_name}")
            if not _has_image_signature(temp_path, suffix):
                raise RuntimeError(f"COMFYUI_OUTPUT_INVALID_IMAGE:{safe_name}")
            os.replace(temp_name, destination)
            if not destination.is_file() or destination.is_symlink() or destination.stat().st_size <= 0:
                raise RuntimeError(f"COMFYUI_OUTPUT_PROMOTION_FAILED:{safe_name}")
        except Exception:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise
        return str(destination)

    def wait_and_download(self, prompt_id: str, target_dir: str | Path, *, timeout: float = 600.0, interval: float = 1.0) -> List[str]:
        outputs = self.wait_for_outputs(prompt_id, timeout=timeout, interval=interval)
        return [self.download_output(output, target_dir) for output in outputs]

    def __repr__(self) -> str:
        return f"ComfyUIBackend(endpoint={self.endpoint!r})"
