"""Bounded provider adapters for the EVAVO Unified Gateway.

The public gateway contract is intentionally kept outside this module. This
module only turns a queued gateway request into a verified local artifact.
Providers are local-first and fail closed when their execution surface is not
configured or does not prove a successful result.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import aiohttp

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
try:
    _configured_log_limit = int(os.getenv("EVAVO_PROVIDER_MAX_LOG_BYTES", str(1024 * 1024)))
except ValueError:
    _configured_log_limit = 1024 * 1024
_MAX_PROVIDER_LOG_BYTES = max(64 * 1024, min(_configured_log_limit, 16 * 1024 * 1024))


class ProviderError(RuntimeError):
    """Structured provider failure that maps cleanly into gateway task state."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}:{message}")


@dataclass(frozen=True)
class ProviderResult:
    paths: list[str]
    receipt: dict[str, Any]
    backend_mode: str


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _float_env(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        return default
    return max(1.0, value)


def _int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _lexical_absolute(path: Path) -> Path:
    """Normalize an absolute path without following symlinks/junctions."""
    return Path(os.path.abspath(os.path.expanduser(str(path))))


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(os.path.normpath(str(left))) == os.path.normcase(os.path.normpath(str(right)))


def _loopback_endpoint(url: str, *, default_port: int) -> str:
    parsed = urllib.parse.urlparse(url.rstrip("/"))
    if parsed.scheme != "http" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ProviderError("PROVIDER_CONFIG_INVALID", f"provider endpoint must be a plain loopback HTTP URL: {url}")
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ProviderError("PROVIDER_CONFIG_INVALID", f"provider endpoint must use loopback: {url}")
    if parsed.path not in {"", "/"}:
        raise ProviderError("PROVIDER_CONFIG_INVALID", f"provider endpoint must not contain a path: {url}")
    try:
        port = parsed.port or default_port
    except ValueError as exc:
        raise ProviderError("PROVIDER_CONFIG_INVALID", f"provider endpoint contains an invalid port: {url}") from exc
    if not 1 <= port <= 65535:
        raise ProviderError("PROVIDER_CONFIG_INVALID", f"provider endpoint contains an invalid port: {url}")
    host = "127.0.0.1" if parsed.hostname == "localhost" else parsed.hostname
    display_host = f"[{host}]" if ":" in host else host
    return f"http://{display_host}:{port}"


def _json_argv(env_name: str) -> list[str] | None:
    raw = os.getenv(env_name, "").strip()
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProviderError("PROVIDER_CONFIG_INVALID", f"{env_name} must be a JSON array") from exc
    if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item for item in value):
        raise ProviderError("PROVIDER_CONFIG_INVALID", f"{env_name} must be a non-empty JSON string array")
    return value


def _render_argv(template: Iterable[str], values: dict[str, str]) -> list[str]:
    rendered: list[str] = []
    for item in template:
        try:
            rendered.append(item.format_map(values))
        except KeyError as exc:
            raise ProviderError("PROVIDER_CONFIG_INVALID", f"unknown argv placeholder: {exc.args[0]}") from exc
    return rendered


async def _drain(stream: asyncio.StreamReader | None, limit: int) -> bytes:
    if stream is None:
        return b""
    kept = bytearray()
    while True:
        chunk = await stream.read(65536)
        if not chunk:
            break
        if len(kept) < limit:
            kept.extend(chunk[: max(0, limit - len(kept))])
    return bytes(kept)


async def _run_process(argv: list[str], *, cwd: Path, timeout: float) -> tuple[int, str, str]:
    if not argv:
        raise ProviderError("PROVIDER_CONFIG_INVALID", "provider argv is empty")
    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(cwd),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except (FileNotFoundError, PermissionError, OSError) as exc:
        raise ProviderError("PROVIDER_UNAVAILABLE", f"could not start provider: {exc}") from exc

    stdout_task = asyncio.create_task(_drain(process.stdout, _MAX_PROVIDER_LOG_BYTES))
    stderr_task = asyncio.create_task(_drain(process.stderr, _MAX_PROVIDER_LOG_BYTES))
    try:
        await asyncio.wait_for(process.wait(), timeout=timeout)
    except asyncio.TimeoutError as exc:
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
        await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
        raise ProviderError("PROVIDER_TIMEOUT", f"provider exceeded {timeout:.0f}s timeout") from exc

    stdout_b, stderr_b = await asyncio.gather(stdout_task, stderr_task)
    stdout = stdout_b.decode("utf-8", errors="replace")
    stderr = stderr_b.decode("utf-8", errors="replace")
    return int(process.returncode or 0), stdout, stderr


def _receipt_from_stdout(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        candidate = line.strip()
        if not candidate:
            continue
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ProviderError("PROVIDER_PROTOCOL_ERROR", "provider did not emit a JSON object receipt")


def _receipt_sha256(receipt: dict[str, Any]) -> str | None:
    candidates: list[Any] = [
        receipt.get("sha256"),
        receipt.get("outputSha256"),
        receipt.get("artifactSha256"),
        receipt.get("fileSha256"),
    ]
    result = receipt.get("result")
    if isinstance(result, dict):
        candidates.extend([
            result.get("sha256"),
            result.get("outputSha256"),
            result.get("artifactSha256"),
            result.get("fileSha256"),
        ])
    supplied = [str(value).strip().lower() for value in candidates if value not in {None, ""}]
    if not supplied:
        return None
    if len(set(supplied)) != 1 or not _SHA256_RE.fullmatch(supplied[0]):
        raise ProviderError("PROVIDER_PROTOCOL_ERROR", "provider receipt contains an invalid or conflicting SHA-256")
    return supplied[0]


def _copy_verified(source: Path, destination: Path, *, admitted_root: Path) -> Path:
    source_lexical = _lexical_absolute(source)
    if source_lexical.is_symlink():
        raise ProviderError("PROVIDER_OUTPUT_INVALID", "provider artifact must not be a symlink")
    try:
        resolved = source_lexical.resolve(strict=True)
    except OSError as exc:
        raise ProviderError("PROVIDER_OUTPUT_INVALID", f"provider artifact is unavailable: {source}") from exc
    if not _same_path(source_lexical, resolved):
        raise ProviderError("PROVIDER_OUTPUT_INVALID", "provider artifact traversed a symlink or redirected parent path")
    if not resolved.is_file():
        raise ProviderError("PROVIDER_OUTPUT_INVALID", "provider artifact must be an ordinary file")
    if not _inside(resolved, admitted_root):
        raise ProviderError("PROVIDER_OUTPUT_INVALID", "provider artifact escaped its admitted workspace")

    destination_lexical = _lexical_absolute(destination)
    destination_parent = destination_lexical.parent
    destination_parent.mkdir(parents=True, exist_ok=True)
    if destination_parent.is_symlink():
        raise ProviderError("PROVIDER_OUTPUT_INVALID", "provider result directory must not be a symlink")
    try:
        resolved_parent = destination_parent.resolve(strict=True)
    except OSError as exc:
        raise ProviderError("PROVIDER_OUTPUT_INVALID", f"provider result directory is unavailable: {destination_parent}") from exc
    if not _same_path(destination_parent, resolved_parent):
        raise ProviderError("PROVIDER_OUTPUT_INVALID", "provider result directory traversed a symlink or redirected parent path")
    if destination_lexical.is_symlink():
        raise ProviderError("PROVIDER_OUTPUT_INVALID", "provider destination must not be a symlink")

    fd, temp_name = tempfile.mkstemp(prefix=destination_lexical.name + ".", suffix=".part", dir=str(resolved_parent))
    os.close(fd)
    try:
        shutil.copyfile(resolved, temp_name, follow_symlinks=False)
        temp_path = Path(temp_name)
        if not temp_path.is_file() or temp_path.is_symlink() or temp_path.stat().st_size < 1:
            raise ProviderError("PROVIDER_OUTPUT_INVALID", "copied provider artifact is empty or unsafe")
        with temp_path.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temp_name, destination_lexical)
        final = destination_lexical.resolve(strict=True)
        if destination_lexical.is_symlink() or not _same_path(destination_lexical, final) or not final.is_file() or final.stat().st_size < 1:
            raise ProviderError("PROVIDER_OUTPUT_INVALID", "final provider artifact path is unsafe")
        return final
    except Exception:
        try:
            Path(temp_name).unlink()
        except OSError:
            pass
        raise


def _generic_output(receipt: dict[str, Any]) -> str | None:
    for key in ("output", "path", "output_path", "file"):
        value = receipt.get(key)
        if isinstance(value, str) and value.strip():
            return value
    result = receipt.get("result")
    if isinstance(result, dict):
        for key in ("output", "path", "output_path", "file"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return value
    return None


def _generic_3d_brief(task_id: str, request: dict[str, Any]) -> dict[str, Any]:
    prompt = str(request.get("prompt", "")).strip()
    suffix = task_id.split("_", 1)[-1]
    asset_id = f"gateway-asset-{suffix}"[:64]
    request_id = f"gateway-request-{suffix}"[:64]
    target_triangles = _int(request.get("target_triangles"), 45000, 500, 500000)
    maximum_triangles = max(target_triangles, _int(request.get("maximum_triangles"), 70000, 500, 750000))
    requested_texture_resolution = _int(request.get("texture_resolution"), 2048, 256, 8192)
    texture_resolution = min((256, 512, 1024, 2048, 4096, 8192), key=lambda value: abs(value - requested_texture_resolution))
    return {
        "contractVersion": "evavo_3d_asset_production_brief_v1",
        "requestId": request_id,
        "assetId": asset_id,
        "assetClass": str(request.get("asset_class", "hero-prop")),
        "input": {
            "mode": "text",
            "prompt": prompt,
            "negativePrompt": str(request.get("negative_prompt", "")),
            "references": [],
            "sourceMesh": None,
            "seed": _int(request.get("seed"), 18712026, 0, 2147483647),
        },
        "artDirection": {
            "styleFamily": str(request.get("style_family", "stylised-realism")),
            "styleDescription": str(request.get("style_description", "Clean production-ready game asset with coherent authored forms and readable materials.")),
            "silhouette": str(request.get("silhouette", "Clear, readable silhouette appropriate to the requested asset.")),
            "palette": list(request.get("palette", ["#808080", "#303030", "#d0d0d0"])),
            "detailStrategy": str(request.get("detail_strategy", "Prioritise readable primary forms, restrained secondary detail, and production-safe surfaces.")),
            "avoid": list(request.get("avoid", ["broken topology", "floating parts", "baked lighting", "unreadable geometry"])),
        },
        "geometry": {
            "topologyStrategy": str(request.get("topology_strategy", "quadriflow")),
            "targetTriangles": target_triangles,
            "maximumTriangles": maximum_triangles,
            "watertightRequired": bool(request.get("watertight_required", False)),
            "manifoldRequired": bool(request.get("manifold_required", True)),
            "maximumComponents": _int(request.get("maximum_components"), 32, 1, 256),
            "minimumThicknessMetres": _float(request.get("minimum_thickness_metres"), 0.002, 0.00001, 10.0),
            "symmetry": bool(request.get("symmetry", False)),
            "hardSurface": bool(request.get("hard_surface", True)),
            "subdivisionReady": bool(request.get("subdivision_ready", False)),
        },
        "uv": {
            "strategy": str(request.get("uv_strategy", "xatlas")),
            "sets": _int(request.get("uv_sets"), 1, 1, 4),
            "resolution": texture_resolution,
            "paddingPixels": _int(request.get("uv_padding_pixels"), 16, 1, 128),
            "allowOverlap": bool(request.get("uv_allow_overlap", False)),
            "maximumOverlapRatio": _float(request.get("uv_maximum_overlap_ratio"), 0.001, 0.0, 1.0),
            "maximumStretchP95": _float(request.get("uv_maximum_stretch_p95"), 0.18, 0.0, 10.0),
            "minimumUtilization": _float(request.get("uv_minimum_utilization"), 0.72, 0.0, 1.0),
            "maximumTexelDensityCv": _float(request.get("uv_maximum_texel_density_cv"), 0.2, 0.0, 10.0),
            "udim": bool(request.get("udim", False)),
        },
        "materials": {
            "workflow": str(request.get("material_workflow", "openpbr-surface")),
            "graphId": str(request.get("material_graph_id", "gateway-default-material")),
            "textureResolution": texture_resolution,
            "normalConvention": str(request.get("normal_convention", "opengl")),
            "requiredChannels": list(request.get("required_channels", ["base-color", "normal", "roughness", "metalness", "ao", "mask"])),
            "channelPacking": dict(request.get("channel_packing", {"r": "ao", "g": "roughness", "b": "metalness", "a": "mask"})),
            "delightRequired": bool(request.get("delight_required", False)),
            "bakeRequired": bool(request.get("bake_required", False)),
        },
        "rigging": {
            "type": str(request.get("rig_type", "none")),
            "required": bool(request.get("rig_required", False)),
            "maximumBones": _int(request.get("maximum_bones"), 0, 0, 512),
            "maximumInfluences": _int(request.get("maximum_influences"), 0, 0, 16),
            "blendshapes": list(request.get("blendshapes", [])),
            "animations": list(request.get("animations", [])),
        },
        "lod": {
            "required": bool(request.get("lod_required", True)),
            "levels": _int(request.get("lod_levels"), 3, 1, 8),
            "ratios": list(request.get("lod_ratios", [1.0, 0.5, 0.2])),
            "preserveSilhouette": bool(request.get("lod_preserve_silhouette", True)),
            "preserveUVs": bool(request.get("lod_preserve_uvs", True)),
        },
        "delivery": {
            "targets": list(request.get("delivery_targets", ["godot", "blender"])),
            "format": "glb",
            "meshCompression": str(request.get("mesh_compression", "meshopt")),
            "textureCompression": str(request.get("texture_compression", "ktx2-uastc")),
            "embedTextures": bool(request.get("embed_textures", True)),
            "generateManifest": bool(request.get("generate_manifest", True)),
        },
        "budgets": {
            "maximumTransferBytes": _int(request.get("maximum_transfer_bytes"), 25165824, 1024, 1073741824),
            "maximumDecodedTextureBytes": _int(request.get("maximum_decoded_texture_bytes"), 134217728, 1024, 2147483647),
            "maximumDrawCalls": _int(request.get("maximum_draw_calls"), 24, 1, 1024),
            "targetFps": _int(request.get("target_fps"), 60, 1, 1000),
        },
        "quality": {
            "profile": str(request.get("quality_profile", "threejs-hero")),
            "minimumScore": _int(request.get("minimum_quality_score"), 88, 1, 100),
            "requireHumanVisualReview": True,
            "maximumRepairAttempts": _int(request.get("maximum_repair_attempts"), 3, 0, 3),
        },
        "provenance": {
            "requestedBy": "EVAVO Unified Gateway",
            "project": str(request.get("project_name", "gateway"))[:128],
            "rightsReviewRequired": True,
            "notes": "Generated through the EVAVO Unified Gateway; human visual review remains required.",
        },
    }


class ProviderRouter:
    def __init__(self, repository_root: Path, state_dir: Path, result_dir: Path):
        self.repository_root = repository_root.resolve()
        self.state_dir = state_dir.resolve()
        self.result_dir = result_dir.resolve()
        self.provider_root = self.state_dir / "provider-tasks"

    def _task_root(self, task_id: str) -> Path:
        if not re.fullmatch(r"(?:vid|aud|3d)_\d+", task_id):
            raise ProviderError("PROVIDER_TASK_ID_INVALID", "unexpected gateway task id")
        path = (self.provider_root / task_id).resolve()
        if not _inside(path, self.provider_root):
            raise ProviderError("PROVIDER_TASK_ID_INVALID", "provider task path escaped state root")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _result_root(self, task_id: str) -> Path:
        path = (self.result_dir / task_id).resolve()
        if not _inside(path, self.result_dir):
            raise ProviderError("PROVIDER_OUTPUT_INVALID", "result path escaped result root")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _video_repo(self) -> Path | None:
        candidates: list[Path] = []
        explicit = os.getenv("EVAVO_VIDEO_STUDIO_DIR", "").strip()
        if explicit:
            candidates.append(Path(explicit).expanduser())
        candidates.extend([
            self.repository_root.parent / "evavo-video-studio",
            self.repository_root.parent / "video-studio",
        ])
        for candidate in candidates:
            worker = candidate / "tools" / "wan21_t2v_worker.py"
            if worker.is_file() and not worker.is_symlink():
                return candidate.resolve()
        return None

    def _video_python(self, repo: Path) -> str:
        explicit = os.getenv("EVAVO_VIDEO_PYTHON", "").strip()
        if explicit:
            return explicit
        windows = repo / ".venv" / "Scripts" / "python.exe"
        posix = repo / ".venv" / "bin" / "python"
        if windows.is_file():
            return str(windows)
        if posix.is_file():
            return str(posix)
        return sys.executable

    async def services(self, *, comfyui_ready: bool | None = None) -> dict[str, Any]:
        video = await self._video_status()
        audio = self._generic_status("audio", "EVAVO_AUDIO_PROVIDER_ARGV")
        model3d = await self._three_d_status()
        return {
            "image": {
                "backend": "ComfyUI",
                "ready": bool(comfyui_ready),
                "endpoint": os.getenv("COMFYUI_ENDPOINT") or os.getenv("EVAVO_COMFYUI_ENDPOINT") or "http://127.0.0.1:8188",
            },
            "video": video,
            "audio": audio,
            "3d": model3d,
        }

    async def _video_status(self) -> dict[str, Any]:
        try:
            override = _json_argv("EVAVO_VIDEO_PROVIDER_ARGV")
        except ProviderError as exc:
            return {"backend": "configured-cli", "ready": False, "reason": str(exc)}
        if override:
            return {"backend": "configured-cli", "ready": True}
        repo = self._video_repo()
        if repo is None:
            return {"backend": "Wan 2.1 Studio worker", "ready": False, "reason": "video studio worker not found"}
        model_raw = os.getenv("EVAVO_WAN21_MODEL_DIR", "").strip()
        if not model_raw:
            return {"backend": "Wan 2.1 Studio worker", "ready": False, "reason": "EVAVO_WAN21_MODEL_DIR is not configured"}
        model = Path(model_raw).expanduser()
        manifest = model / "evavo-model-manifest.json"
        ready = model.is_dir() and manifest.is_file() and not manifest.is_symlink()
        return {
            "backend": "Wan 2.1 Studio worker",
            "ready": ready,
            "worker": str(repo / "tools" / "wan21_t2v_worker.py"),
            "reason": None if ready else "reviewed Wan model directory/manifest is unavailable",
        }

    def _generic_status(self, kind: str, env_name: str) -> dict[str, Any]:
        try:
            argv = _json_argv(env_name)
        except ProviderError as exc:
            return {"backend": "configured-cli", "ready": False, "reason": str(exc)}
        return {
            "backend": "configured-cli",
            "ready": bool(argv),
            "reason": None if argv else f"{env_name} is not configured",
            "kind": kind,
        }

    async def _three_d_status(self) -> dict[str, Any]:
        try:
            endpoint = _loopback_endpoint(os.getenv("EVAVO_3D_ENDPOINT", "http://127.0.0.1:4314"), default_port=4314)
        except ProviderError as exc:
            return {"backend": "EVAVO 3D Studio worker", "ready": False, "reason": str(exc)}
        token = os.getenv("EVAVO_3D_AGENT_EXECUTION_TOKEN", "")
        workspace = os.getenv("EVAVO_3D_AGENT_WORKSPACE_ROOT", "").strip()
        if len(token) < 32:
            return {"backend": "EVAVO 3D Studio worker", "ready": False, "endpoint": endpoint, "reason": "EVAVO_3D_AGENT_EXECUTION_TOKEN is not configured"}
        if not workspace:
            return {"backend": "EVAVO 3D Studio worker", "ready": False, "endpoint": endpoint, "reason": "EVAVO_3D_AGENT_WORKSPACE_ROOT is not configured"}
        try:
            timeout = aiohttp.ClientTimeout(total=2.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{endpoint}/api/v1/health") as response:
                    payload = await response.json(content_type=None)
                    status = response.status
            ready = status == 200 and isinstance(payload, dict) and payload.get("ok") is True and payload.get("executionEnabled") is True
            return {"backend": "EVAVO 3D Studio worker", "ready": ready, "endpoint": endpoint, "health": payload}
        except Exception as exc:
            return {"backend": "EVAVO 3D Studio worker", "ready": False, "endpoint": endpoint, "reason": str(exc)}

    async def generate(self, kind: str, task_id: str, request: dict[str, Any]) -> ProviderResult:
        if kind == "video":
            return await self._video(task_id, request)
        if kind == "audio":
            return await self._generic_cli("audio", task_id, request, "EVAVO_AUDIO_PROVIDER_ARGV", "EVAVO_AUDIO_PROVIDER_TIMEOUT", 900.0)
        if kind == "3d":
            return await self._three_d(task_id, request)
        raise ProviderError("PROVIDER_UNAVAILABLE", f"unsupported provider kind: {kind}")

    async def _generic_cli(
        self,
        kind: str,
        task_id: str,
        request: dict[str, Any],
        argv_env: str,
        timeout_env: str,
        default_timeout: float,
    ) -> ProviderResult:
        template = _json_argv(argv_env)
        if not template:
            raise ProviderError("PROVIDER_UNAVAILABLE", f"{kind} provider is not configured ({argv_env})")
        task_root = self._task_root(task_id)
        output_dir = task_root / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        request_path = task_root / "request.json"
        request_path.write_text(json.dumps(request, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        values = {
            "task_id": task_id,
            "prompt": str(request.get("prompt", "")),
            "request_json": str(request_path),
            "output_dir": str(output_dir),
        }
        argv = _render_argv(template, values)
        code, stdout, stderr = await _run_process(argv, cwd=self.repository_root, timeout=_float_env(timeout_env, default_timeout))
        receipt = _receipt_from_stdout(stdout)
        if code != 0 or receipt.get("ok") is not True:
            detail = str(receipt.get("error") or stderr.strip() or f"provider exited with status {code}")[:4096]
            raise ProviderError("PROVIDER_FAILED", detail)
        output_value = _generic_output(receipt)
        if not output_value:
            raise ProviderError("PROVIDER_PROTOCOL_ERROR", "provider success receipt did not identify an artifact")
        source = Path(output_value)
        if not source.is_absolute():
            source = output_dir / source
        suffix = source.suffix or ".bin"
        copied = await asyncio.to_thread(_copy_verified, source, self._result_root(task_id) / f"{kind}{suffix}", admitted_root=task_root)
        expected_sha = _receipt_sha256(receipt)
        if expected_sha and await asyncio.to_thread(_sha256_file, copied) != expected_sha:
            copied.unlink(missing_ok=True)
            raise ProviderError("PROVIDER_OUTPUT_INVALID", "provider output SHA-256 does not match its receipt")
        return ProviderResult(paths=[str(copied)], receipt=receipt, backend_mode=f"{kind}-configured-cli")

    async def _video(self, task_id: str, request: dict[str, Any]) -> ProviderResult:
        override = _json_argv("EVAVO_VIDEO_PROVIDER_ARGV")
        if override:
            return await self._generic_cli("video", task_id, request, "EVAVO_VIDEO_PROVIDER_ARGV", "EVAVO_VIDEO_PROVIDER_TIMEOUT", 7200.0)
        repo = self._video_repo()
        if repo is None:
            raise ProviderError("PROVIDER_UNAVAILABLE", "EVAVO Video Studio Wan worker was not found")
        model_raw = os.getenv("EVAVO_WAN21_MODEL_DIR", "").strip()
        if not model_raw:
            raise ProviderError("PROVIDER_UNAVAILABLE", "EVAVO_WAN21_MODEL_DIR is not configured")
        model_dir = Path(model_raw).expanduser().resolve()
        manifest = model_dir / "evavo-model-manifest.json"
        if not model_dir.is_dir() or not manifest.is_file() or manifest.is_symlink():
            raise ProviderError("PROVIDER_UNAVAILABLE", "reviewed Wan model directory/manifest is unavailable")
        configured_sha = os.getenv("EVAVO_WAN21_MODEL_MANIFEST_SHA256", "").strip().lower()
        manifest_sha = configured_sha or await asyncio.to_thread(_sha256_file, manifest)
        if not _SHA256_RE.fullmatch(manifest_sha):
            raise ProviderError("PROVIDER_CONFIG_INVALID", "Wan model manifest SHA-256 is invalid")
        if configured_sha and await asyncio.to_thread(_sha256_file, manifest) != configured_sha:
            raise ProviderError("PROVIDER_CONFIG_INVALID", "Wan model manifest SHA-256 does not match the configured value")

        task_root = self._task_root(task_id)
        output_dir = task_root / "wan-output"
        if output_dir.exists():
            shutil.rmtree(output_dir)
        worker = repo / "tools" / "wan21_t2v_worker.py"
        fps = _int(request.get("fps"), 8, 1, 60)
        argv = [
            self._video_python(repo), str(worker),
            "--model-dir", str(model_dir),
            "--model-manifest-sha256", manifest_sha,
            "--prompt", str(request.get("prompt", "")),
            "--negative-prompt", str(request.get("negative_prompt", "")),
            "--output-dir", str(output_dir),
            "--seed", str(_int(request.get("seed"), 18712026, 0, 2147483647)),
            "--width", str(_int(request.get("width"), 512, 128, 2048)),
            "--height", str(_int(request.get("height"), 320, 128, 2048)),
            "--frames", str(_int(request.get("frames"), 17, 5, 241)),
            "--fps", str(fps),
            "--steps", str(_int(request.get("steps"), 8, 1, 100)),
            "--guidance-scale", str(_float(request.get("guidance_scale"), 5.0, 0.0, 30.0)),
        ]
        code, stdout, stderr = await _run_process(argv, cwd=repo, timeout=_float_env("EVAVO_VIDEO_PROVIDER_TIMEOUT", 7200.0))
        receipt = _receipt_from_stdout(stdout)
        if code != 0 or receipt.get("ok") is not True:
            detail = str(receipt.get("error") or stderr.strip() or f"Wan worker exited with status {code}")[:4096]
            raise ProviderError("PROVIDER_FAILED", detail)
        video = output_dir / "video.mp4"
        if not video.is_file() or video.stat().st_size <= 1024:
            raise ProviderError("PROVIDER_OUTPUT_INVALID", "Wan worker did not produce a valid video.mp4")
        expected_sha = str(receipt.get("videoSha256", "")).lower()
        if not _SHA256_RE.fullmatch(expected_sha) or await asyncio.to_thread(_sha256_file, video) != expected_sha:
            raise ProviderError("PROVIDER_OUTPUT_INVALID", "Wan output SHA-256 does not match its receipt")
        copied = await asyncio.to_thread(_copy_verified, video, self._result_root(task_id) / "video.mp4", admitted_root=task_root)
        return ProviderResult(paths=[str(copied)], receipt=receipt, backend_mode="video-studio-wan21")

    async def _three_d(self, task_id: str, request: dict[str, Any]) -> ProviderResult:
        endpoint = _loopback_endpoint(os.getenv("EVAVO_3D_ENDPOINT", "http://127.0.0.1:4314"), default_port=4314)
        token = os.getenv("EVAVO_3D_AGENT_EXECUTION_TOKEN", "")
        workspace_raw = os.getenv("EVAVO_3D_AGENT_WORKSPACE_ROOT", "").strip()
        if len(token) < 32:
            raise ProviderError("PROVIDER_UNAVAILABLE", "EVAVO_3D_AGENT_EXECUTION_TOKEN must contain at least 32 characters")
        if not workspace_raw:
            raise ProviderError("PROVIDER_UNAVAILABLE", "EVAVO_3D_AGENT_WORKSPACE_ROOT is not configured")
        workspace_root = Path(workspace_raw).expanduser().resolve()
        workspace_root.mkdir(parents=True, exist_ok=True)
        suffix = task_id.split("_", 1)[-1]
        workspace = (workspace_root / "gateway" / f"task-{suffix}").resolve()
        if not _inside(workspace, workspace_root):
            raise ProviderError("PROVIDER_CONFIG_INVALID", "3D workspace escaped configured worker root")
        workspace.mkdir(parents=True, exist_ok=True)
        brief_value = request.get("brief")
        if brief_value is None:
            brief = _generic_3d_brief(task_id, request)
        elif isinstance(brief_value, dict):
            brief = brief_value
        else:
            raise ProviderError("PROVIDER_PROTOCOL_ERROR", "3D request brief must be a JSON object")

        worker_job_id = f"gateway-3d-{suffix}"[:64]
        worker_request_id = f"gateway-request-{suffix}"[:64]
        compile_body = {
            "jobId": worker_job_id,
            "requestId": worker_request_id,
            "operation": "pipeline.full-candidate",
            "workspace": str(workspace),
            "payload": {
                "brief": brief,
                "availableVramGiB": request.get("available_vram_gib"),
                "maximumCandidates": _int(request.get("maximum_candidates"), 3, 1, 3),
                "optimiser": str(request.get("optimiser", "none")),
                "validationRequired": bool(request.get("validation_required", False)),
            },
        }
        if compile_body["payload"]["availableVramGiB"] is None:
            compile_body["payload"].pop("availableVramGiB")

        timeout_seconds = _float_env("EVAVO_3D_PROVIDER_TIMEOUT", 10800.0)
        client_timeout = aiohttp.ClientTimeout(total=30.0)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        async with aiohttp.ClientSession(timeout=client_timeout) as session:
            try:
                async with session.get(f"{endpoint}/api/v1/health") as response:
                    health = await response.json(content_type=None)
                    health_status = response.status
                if health_status != 200 or not isinstance(health, dict) or health.get("ok") is not True or health.get("executionEnabled") is not True:
                    raise ProviderError("PROVIDER_UNAVAILABLE", "3D worker is not execution-ready")

                async with session.get(f"{endpoint}/api/v1/capabilities") as response:
                    caps = await response.json(content_type=None)
                    caps_status = response.status
                operations = caps.get("operations", []) if isinstance(caps, dict) else []
                if caps_status != 200 or "pipeline.full-candidate" not in operations:
                    raise ProviderError("PROVIDER_UNAVAILABLE", "3D worker does not expose pipeline.full-candidate")

                async with session.post(f"{endpoint}/api/v1/jobs/compile", json=compile_body) as response:
                    compiled = await response.json(content_type=None)
                    compile_status = response.status
                if compile_status != 200 or not isinstance(compiled, dict) or not compiled.get("jobSha256"):
                    raise ProviderError("PROVIDER_PROTOCOL_ERROR", f"3D worker rejected job compilation: {compiled}")

                async with session.post(f"{endpoint}/api/v1/jobs", json=compiled, headers=headers) as response:
                    submitted = await response.json(content_type=None)
                    submit_status = response.status
                if submit_status != 202:
                    raise ProviderError("PROVIDER_FAILED", f"3D worker rejected job submission: {submitted}")

                loop = asyncio.get_running_loop()
                deadline = loop.time() + timeout_seconds
                final: dict[str, Any] | None = None
                while loop.time() < deadline:
                    async with session.get(f"{endpoint}/api/v1/jobs/{worker_job_id}", headers=headers) as response:
                        current = await response.json(content_type=None)
                        current_status = response.status
                    if current_status != 200 or not isinstance(current, dict):
                        raise ProviderError("PROVIDER_PROTOCOL_ERROR", f"3D worker returned invalid job status: {current}")
                    state = current.get("state") if isinstance(current.get("state"), dict) else {}
                    status = state.get("status")
                    if status == "completed":
                        final = current
                        break
                    if status == "failed":
                        raise ProviderError("PROVIDER_FAILED", str(state.get("error") or "3D worker failed"))
                    await asyncio.sleep(1.0)
                if final is None:
                    raise ProviderError("PROVIDER_TIMEOUT", f"3D worker exceeded {timeout_seconds:.0f}s timeout")
            except ProviderError:
                raise
            except (aiohttp.ClientError, asyncio.TimeoutError, json.JSONDecodeError) as exc:
                raise ProviderError("PROVIDER_UNAVAILABLE", f"3D worker request failed: {exc}") from exc

        receipt = final.get("receipt")
        if not isinstance(receipt, dict) or receipt.get("executionStatus") != "completed" or receipt.get("jobId") != worker_job_id:
            raise ProviderError("PROVIDER_PROTOCOL_ERROR", "3D worker completed without a valid execution receipt")
        result = receipt.get("result") if isinstance(receipt.get("result"), dict) else {}
        web_delivery = result.get("webDelivery") if isinstance(result.get("webDelivery"), dict) else {}
        delivery = web_delivery.get("delivery") if isinstance(web_delivery.get("delivery"), dict) else {}
        artifact_value = delivery.get("path")
        if not isinstance(artifact_value, str) or not artifact_value:
            raise ProviderError("PROVIDER_PROTOCOL_ERROR", "3D receipt did not contain webDelivery.delivery.path")
        artifact = Path(artifact_value).expanduser()
        copied = await asyncio.to_thread(_copy_verified, artifact, self._result_root(task_id) / "model.glb", admitted_root=workspace)
        expected = str(delivery.get("sha256", "")).lower()
        if _SHA256_RE.fullmatch(expected) and await asyncio.to_thread(_sha256_file, copied) != expected:
            copied.unlink(missing_ok=True)
            raise ProviderError("PROVIDER_OUTPUT_INVALID", "3D output SHA-256 does not match its worker receipt")
        return ProviderResult(paths=[str(copied)], receipt=receipt, backend_mode="3d-studio-agent-worker")
