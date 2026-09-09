"""MCP v2 server for automated EVAVO image generation."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from mcp.server import MCPServer
    from mcp.server.mcpserver.utilities.types import Image
    from mcp.server.transport_security import TransportSecuritySettings
except ImportError as exc:  # pragma: no cover
    raise RuntimeError('MCP SDK is required. Install with: python -m pip install "mcp[cli]>=2,<3"') from exc

from evavo_operations import ROOT, TaskTracker
from .backends import ComfyUIBackend
from .comfyui_runtime import discover_comfyui, ensure_comfyui, stop_managed_comfyui

mcp = MCPServer("EVAVO Local Image Generator")
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
MAX_MCP_IMAGE_BYTES = 32 * 1024 * 1024


def _endpoint() -> str:
    return (os.getenv("EVAVO_COMFYUI_ENDPOINT") or os.getenv("COMFYUI_ENDPOINT") or "http://127.0.0.1:8188").rstrip("/")


def _backend() -> ComfyUIBackend:
    return ComfyUIBackend(_endpoint())


def _tracker() -> TaskTracker:
    return TaskTracker()


def _output_root() -> Path:
    return Path(os.getenv("EVAVO_GENERATION_OUTPUT_DIR", str(ROOT / ".evavo" / "outputs"))).expanduser().resolve()


def _output_dir(project_name: str, output_dir: Optional[str]) -> Path:
    if output_dir:
        return Path(output_dir).expanduser().resolve()
    safe_project = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in project_name)[:80] or "mcp"
    return _output_root() / safe_project


def _truthy_environment(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _provision_backend_sync() -> Dict[str, Any]:
    """Run the fixed EVAVO provisioner using operator-controlled environment only."""
    provisioner = ROOT / "provision-comfyui.py"
    if not provisioner.is_file():
        raise RuntimeError(f"PROVISIONER_MISSING:{provisioner}")
    try:
        result = subprocess.run(
            [sys.executable, str(provisioner), "--json"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=3600,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("COMFYUI_PROVISION_TIMEOUT:provisioner exceeded one hour") from exc
    except OSError as exc:
        raise RuntimeError(f"COMFYUI_PROVISION_PROCESS:{exc}") from exc
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        detail = (result.stderr or result.stdout).strip()[-2000:]
        raise RuntimeError(f"COMFYUI_PROVISION_INVALID_JSON:{detail}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("COMFYUI_PROVISION_INVALID_RESPONSE:expected JSON object")
    if result.returncode != 0 or not payload.get("ok"):
        raise RuntimeError(f"COMFYUI_PROVISION_FAILED:{payload.get('message') or result.stderr or result.stdout}")
    return payload


async def _provision_backend() -> Dict[str, Any]:
    return await asyncio.to_thread(_provision_backend_sync)


async def _ensure(auto_start: bool = True, wait_seconds: float = 90.0) -> Dict[str, Any]:
    try:
        return await asyncio.to_thread(ensure_comfyui, _endpoint(), wait_seconds=wait_seconds, allow_start=auto_start)
    except RuntimeError as exc:
        if not auto_start or not _truthy_environment("EVAVO_AUTO_PROVISION_COMFYUI", default=False):
            raise
        message = str(exc)
        provisionable = any(code in message for code in ("COMFYUI_NOT_FOUND", "COMFYUI_OFFLINE", "COMFYUI_START_FAILED"))
        if not provisionable:
            raise
        provisioned = await _provision_backend()
        ensured = await asyncio.to_thread(ensure_comfyui, _endpoint(), wait_seconds=max(wait_seconds, 180.0), allow_start=True)
        return {**ensured, "provisioned": True, "provision": provisioned}


async def _track_queued(
    task_id: str,
    prompt: str,
    project_name: str,
    *,
    backend_mode: Optional[str] = None,
    checkpoint: Optional[str] = None,
    workflow_path: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> Optional[str]:
    try:
        await asyncio.to_thread(
            _tracker().add_task,
            task_id,
            prompt,
            "queued",
            project_name=project_name,
            backend_mode=backend_mode,
            checkpoint=checkpoint,
            workflow_path=workflow_path,
            output_dir=output_dir,
        )
        return None
    except Exception as exc:
        return str(exc)


async def _track_update(
    task_id: str,
    status: str,
    *,
    output_uris: Optional[List[str]] = None,
    output_dir: Optional[str] = None,
    backend_mode: Optional[str] = None,
    checkpoint: Optional[str] = None,
    workflow_path: Optional[str] = None,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
) -> Optional[str]:
    try:
        await asyncio.to_thread(
            _tracker().update_task,
            task_id,
            status,
            output_uris=output_uris,
            output_dir=output_dir,
            backend_mode=backend_mode,
            checkpoint=checkpoint,
            workflow_path=workflow_path,
            error_code=error_code,
            error_message=error_message,
        )
        return None
    except KeyError:
        return "task was not present in local history"
    except Exception as exc:
        return str(exc)


def _recorded_output_paths() -> set[Path]:
    allowed: set[Path] = set()
    for task in _tracker().list_tasks(limit=200):
        outputs = task.get("output_uris")
        if isinstance(outputs, list):
            for raw in outputs:
                try:
                    allowed.add(Path(str(raw)).expanduser().resolve())
                except OSError:
                    continue
        raw = task.get("output_uri")
        if raw:
            try:
                allowed.add(Path(str(raw)).expanduser().resolve())
            except OSError:
                pass
    return allowed


def _validated_output_image(path: str) -> Path:
    candidate = Path(path).expanduser().resolve()
    if not candidate.is_file():
        raise ValueError(f"generated image does not exist: {candidate}")
    if candidate.suffix.lower() not in IMAGE_EXTENSIONS:
        raise ValueError("generated output must be PNG/JPEG/GIF/WebP")
    try:
        within_default_root = candidate.is_relative_to(_output_root())
    except ValueError:
        within_default_root = False
    if not within_default_root and candidate not in _recorded_output_paths():
        raise PermissionError("image path is not a recorded EVAVO output")
    size = candidate.stat().st_size
    if size <= 0:
        raise ValueError("generated image is empty")
    if size > MAX_MCP_IMAGE_BYTES:
        raise ValueError(f"generated image exceeds {MAX_MCP_IMAGE_BYTES // (1024 * 1024)} MiB MCP payload limit")
    return candidate


async def _generate_image_impl(
    prompt: str,
    project_name: str = "mcp",
    negative_prompt: str = "",
    width: int = 1024,
    height: int = 1024,
    steps: int = 24,
    cfg_scale: float = 7.0,
    seed: Optional[int] = None,
    checkpoint: Optional[str] = None,
    workflow_path: Optional[str] = None,
    wait: bool = True,
    wait_timeout: float = 600.0,
    output_dir: Optional[str] = None,
    auto_start: bool = True,
) -> Dict[str, Any]:
    if not isinstance(prompt, str) or not prompt.strip():
        return {"ok": False, "status": "failed", "error_code": "INVALID_PROMPT", "message": "prompt must be a non-empty string"}
    if not isinstance(project_name, str) or not project_name.strip():
        return {"ok": False, "status": "failed", "error_code": "INVALID_PROJECT", "message": "project_name must be a non-empty string"}

    prompt = prompt.strip()
    project_name = project_name.strip()
    local_failure_id = f"mcp_failed_{uuid.uuid4().hex}"

    try:
        await _ensure(auto_start=auto_start)
        backend = _backend()
        result = await asyncio.to_thread(
            backend.queue_image,
            prompt,
            project_name=project_name,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            steps=steps,
            cfg_scale=cfg_scale,
            seed=seed,
            checkpoint=checkpoint,
            workflow_path=workflow_path,
        )
    except Exception as exc:
        try:
            await asyncio.to_thread(
                _tracker().add_task,
                local_failure_id,
                prompt,
                "failed",
                project_name=project_name,
                backend_mode="native-comfyui",
                checkpoint=checkpoint,
                workflow_path=workflow_path,
                output_dir=output_dir,
                error_code="GENERATION_START_FAILED",
                error_message=str(exc),
            )
        except Exception:
            pass
        return {
            "ok": False,
            "status": "failed",
            "task_id": local_failure_id,
            "error_code": "GENERATION_START_FAILED",
            "message": str(exc),
        }

    task_id = str(result["task_id"])
    effective_checkpoint = result.get("checkpoint")
    effective_backend = str(result.get("backend_mode") or "native-comfyui")
    target = _output_dir(project_name, output_dir) if wait or output_dir else None
    tracking_warning = await _track_queued(
        task_id,
        prompt,
        project_name,
        backend_mode=effective_backend,
        checkpoint=str(effective_checkpoint) if effective_checkpoint else None,
        workflow_path=workflow_path,
        output_dir=str(target) if target else output_dir,
    )
    result.update({"ok": True, "prompt": prompt, "project_name": project_name})
    if workflow_path:
        result["workflow_path"] = workflow_path
    if tracking_warning:
        result["tracking_warning"] = tracking_warning

    if not wait:
        return result

    assert target is not None
    try:
        downloaded = await asyncio.to_thread(backend.wait_and_download, task_id, target, timeout=wait_timeout)
    except Exception as exc:
        warning = await _track_update(
            task_id,
            "failed",
            output_dir=str(target),
            backend_mode=effective_backend,
            checkpoint=str(effective_checkpoint) if effective_checkpoint else None,
            workflow_path=workflow_path,
            error_code="GENERATION_WAIT_FAILED",
            error_message=str(exc),
        )
        result.update({"ok": False, "status": "failed", "error_code": "GENERATION_WAIT_FAILED", "message": str(exc), "output_dir": str(target)})
        if warning:
            result["tracking_warning"] = warning
        return result

    warning = await _track_update(
        task_id,
        "completed",
        output_uris=[str(item) for item in downloaded],
        output_dir=str(target),
        backend_mode=effective_backend,
        checkpoint=str(effective_checkpoint) if effective_checkpoint else None,
        workflow_path=workflow_path,
    )
    result.update({"status": "completed", "downloaded_files": downloaded, "output_dir": str(target)})
    if warning:
        result["tracking_warning"] = warning
    return result


@mcp.tool()
async def provision_backend() -> Dict[str, Any]:
    """Provision official ComfyUI using only workstation-configured environment/model sources, then ensure it is running."""
    provisioned = await _provision_backend()
    ensured = await asyncio.to_thread(ensure_comfyui, _endpoint(), wait_seconds=180.0, allow_start=True)
    backend = _backend()
    checkpoints = await asyncio.to_thread(backend.checkpoints)
    inventory = await asyncio.to_thread(backend.model_inventory, 100)
    return {
        "ok": bool(checkpoints),
        "status": "ready" if checkpoints else "model_required",
        "provision": provisioned,
        "backend": ensured,
        "checkpoints": checkpoints,
        "model_inventory": inventory,
    }


@mcp.tool()
async def ensure_backend(auto_start: bool = True, wait_seconds: float = 90.0) -> Dict[str, Any]:
    """Ensure native ComfyUI is healthy. It may be provisioned first when EVAVO_AUTO_PROVISION_COMFYUI=1."""
    return await _ensure(auto_start=auto_start, wait_seconds=wait_seconds)


@mcp.tool()
async def health_check(auto_start: bool = True) -> Dict[str, Any]:
    """Return ComfyUI health/device/version details, starting/provisioning the local backend when configured."""
    ensured = await _ensure(auto_start=auto_start)
    return ensured["health"]


@mcp.tool()
async def discover_backends() -> List[Dict[str, Any]]:
    """List local ComfyUI installations EVAVO can automatically launch."""
    installs = await asyncio.to_thread(discover_comfyui)
    return [install.to_dict() for install in installs]


@mcp.tool()
async def list_checkpoints(auto_start: bool = True) -> List[str]:
    """List checkpoints exposed by ComfyUI, starting/provisioning the backend when configured."""
    await _ensure(auto_start=auto_start)
    return await asyncio.to_thread(_backend().checkpoints)


@mcp.tool()
async def model_inventory(auto_start: bool = True, limit_per_category: int = 200) -> Dict[str, Any]:
    """List models exposed by common ComfyUI loader nodes: checkpoints, LoRAs, VAEs, ControlNet, UNet/diffusion, text encoders, CLIP vision and upscalers."""
    await _ensure(auto_start=auto_start)
    limit = max(1, min(5000, int(limit_per_category)))
    return await asyncio.to_thread(_backend().model_inventory, limit)


@mcp.tool()
async def generate_image(
    prompt: str,
    project_name: str = "mcp",
    negative_prompt: str = "",
    width: int = 1024,
    height: int = 1024,
    steps: int = 24,
    cfg_scale: float = 7.0,
    seed: Optional[int] = None,
    checkpoint: Optional[str] = None,
    workflow_path: Optional[str] = None,
    wait: bool = True,
    wait_timeout: float = 600.0,
    output_dir: Optional[str] = None,
    auto_start: bool = True,
) -> Dict[str, Any]:
    """Generate one image, wait/download by default, and persist the task in shared EVAVO history."""
    return await _generate_image_impl(
        prompt,
        project_name=project_name,
        negative_prompt=negative_prompt,
        width=width,
        height=height,
        steps=steps,
        cfg_scale=cfg_scale,
        seed=seed,
        checkpoint=checkpoint,
        workflow_path=workflow_path,
        wait=wait,
        wait_timeout=wait_timeout,
        output_dir=output_dir,
        auto_start=auto_start,
    )


@mcp.tool()
async def generate_batch(
    prompts: List[str],
    project_name: str = "mcp_batch",
    negative_prompt: str = "",
    width: int = 1024,
    height: int = 1024,
    steps: int = 24,
    cfg_scale: float = 7.0,
    checkpoint: Optional[str] = None,
    workflow_path: Optional[str] = None,
    wait: bool = True,
    wait_timeout: float = 600.0,
    output_dir: Optional[str] = None,
    concurrency: int = 2,
    auto_start: bool = True,
) -> Dict[str, Any]:
    """Generate multiple prompts with bounded concurrency and shared persistent history."""
    if not isinstance(prompts, list) or not prompts:
        return {"ok": False, "status": "failed", "error_code": "INVALID_PROMPTS", "message": "prompts must be a non-empty list"}
    if len(prompts) > 100:
        return {"ok": False, "status": "failed", "error_code": "TOO_MANY_PROMPTS", "message": "a batch may contain at most 100 prompts"}
    invalid = [index for index, prompt in enumerate(prompts) if not isinstance(prompt, str) or not prompt.strip()]
    if invalid:
        return {
            "ok": False,
            "status": "failed",
            "error_code": "INVALID_PROMPT_ITEMS",
            "message": f"prompts at indices {invalid[:20]} must be non-empty strings",
        }
    concurrency = max(1, min(16, int(concurrency)))
    await _ensure(auto_start=auto_start)
    semaphore = asyncio.Semaphore(concurrency)

    async def one(prompt: str) -> Dict[str, Any]:
        async with semaphore:
            return await _generate_image_impl(
                prompt,
                project_name=project_name,
                negative_prompt=negative_prompt,
                width=width,
                height=height,
                steps=steps,
                cfg_scale=cfg_scale,
                checkpoint=checkpoint,
                workflow_path=workflow_path,
                wait=wait,
                wait_timeout=wait_timeout,
                output_dir=output_dir,
                auto_start=False,
            )

    results = await asyncio.gather(*(one(prompt) for prompt in prompts))
    successful = sum(1 for item in results if item.get("ok") and item.get("status") in {"queued", "completed"})
    return {
        "ok": successful == len(results),
        "status": "completed" if wait and successful == len(results) else ("queued" if successful == len(results) else "partial_failure"),
        "project_name": project_name,
        "total": len(results),
        "successful": successful,
        "failed": len(results) - successful,
        "results": results,
    }


@mcp.tool()
async def generation_status(task_id: str, auto_start: bool = False) -> Dict[str, Any]:
    """Check a ComfyUI prompt ID, return outputs, and reconcile local task history."""
    await _ensure(auto_start=auto_start)
    backend = _backend()
    history = await asyncio.to_thread(backend.history, task_id)
    outputs = await asyncio.to_thread(backend.outputs, task_id) if isinstance(history.get(task_id), dict) else []
    status = "completed" if outputs else "queued"
    warning = await _track_update(task_id, status, backend_mode="native-comfyui")
    result: Dict[str, Any] = {"task_id": task_id, "status": status, "outputs": outputs}
    if warning and warning != "task was not present in local history":
        result["tracking_warning"] = warning
    return result


@mcp.tool()
async def collect_generation(
    task_id: str,
    output_dir: Optional[str] = None,
    timeout: float = 600.0,
    auto_start: bool = False,
) -> Dict[str, Any]:
    """Wait for an existing prompt, download its images, and reconcile local task history."""
    await _ensure(auto_start=auto_start)
    backend = _backend()
    target = _output_dir("collected", output_dir)
    try:
        downloaded = await asyncio.to_thread(backend.wait_and_download, task_id, target, timeout=timeout)
    except Exception as exc:
        warning = await _track_update(task_id, "failed", output_dir=str(target), backend_mode="native-comfyui", error_code="GENERATION_WAIT_FAILED", error_message=str(exc))
        result: Dict[str, Any] = {"ok": False, "task_id": task_id, "status": "failed", "message": str(exc), "output_dir": str(target)}
        if warning and warning != "task was not present in local history":
            result["tracking_warning"] = warning
        return result
    warning = await _track_update(task_id, "completed", output_uris=[str(item) for item in downloaded], output_dir=str(target), backend_mode="native-comfyui")
    result = {"ok": True, "task_id": task_id, "status": "completed", "downloaded_files": downloaded, "output_dir": str(target)}
    if warning and warning != "task was not present in local history":
        result["tracking_warning"] = warning
    return result


@mcp.tool(structured_output=False)
def read_output_image(path: str) -> Image:
    """Return a generated EVAVO output as native MCP image content for visual inspection by the host model."""
    return Image(path=_validated_output_image(path))


@mcp.tool()
async def task_history(limit: int = 20, project_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return recent generation history shared by MCP and CLI workflows."""
    limit = max(1, min(200, int(limit)))
    return await asyncio.to_thread(_tracker().list_tasks, limit, project_name)


@mcp.tool()
async def task_statistics() -> Dict[str, int]:
    """Return shared EVAVO generation task counts by status."""
    return await asyncio.to_thread(_tracker().get_statistics)


@mcp.tool()
async def stop_managed_backend() -> Dict[str, Any]:
    """Stop ComfyUI only when EVAVO itself started that native process."""
    return await asyncio.to_thread(stop_managed_comfyui)


def _transport_security(host: str, port: int) -> TransportSecuritySettings:
    if host == "::1":
        allowed_hosts = [f"[::1]:{port}"]
        allowed_origins = [f"http://[::1]:{port}"]
    else:
        allowed_hosts = [f"127.0.0.1:{port}", f"localhost:{port}"]
        allowed_origins = [f"http://127.0.0.1:{port}", f"http://localhost:{port}"]
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="EVAVO MCP image-generation server")
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default=os.getenv("EVAVO_MCP_TRANSPORT", "stdio"))
    parser.add_argument("--host", default=os.getenv("EVAVO_MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("EVAVO_MCP_PORT", "8765")))
    parser.add_argument("--path", default=os.getenv("EVAVO_MCP_PATH", "/mcp"))
    parser.add_argument("--json-response", action="store_true", help="Use single JSON HTTP responses instead of SSE bodies")
    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run()
        return
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("local MCP HTTP transport is restricted to loopback")
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    if not args.path.startswith("/"):
        parser.error("--path must start with /")
    mcp.run(
        transport="streamable-http",
        host=args.host,
        port=args.port,
        streamable_http_path=args.path,
        json_response=args.json_response,
        transport_security=_transport_security(args.host, args.port),
    )


if __name__ == "__main__":
    main()
