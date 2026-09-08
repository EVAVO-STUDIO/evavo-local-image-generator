"""MCP v2 server for automated EVAVO image generation."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from mcp.server import MCPServer
    from mcp.server.transport_security import TransportSecuritySettings
except ImportError as exc:  # pragma: no cover
    raise RuntimeError('MCP SDK is required. Install with: python -m pip install "mcp[cli]>=2,<3"') from exc

from .backends import ComfyUIBackend
from .comfyui_runtime import discover_comfyui, ensure_comfyui, stop_managed_comfyui

mcp = MCPServer("EVAVO Local Image Generator")


def _endpoint() -> str:
    return (os.getenv("EVAVO_COMFYUI_ENDPOINT") or os.getenv("COMFYUI_ENDPOINT") or "http://127.0.0.1:8188").rstrip("/")


def _backend() -> ComfyUIBackend:
    return ComfyUIBackend(_endpoint())


def _output_dir(project_name: str, output_dir: Optional[str]) -> Path:
    if output_dir:
        return Path(output_dir).expanduser().resolve()
    repo_root = Path(__file__).resolve().parents[1]
    root = Path(os.getenv("EVAVO_GENERATION_OUTPUT_DIR", str(repo_root / ".evavo" / "outputs"))).expanduser().resolve()
    safe_project = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in project_name)[:80] or "mcp"
    return root / safe_project


async def _ensure(auto_start: bool = True, wait_seconds: float = 90.0) -> Dict[str, Any]:
    return await asyncio.to_thread(ensure_comfyui, _endpoint(), wait_seconds=wait_seconds, allow_start=auto_start)


@mcp.tool()
async def ensure_backend(auto_start: bool = True, wait_seconds: float = 90.0) -> Dict[str, Any]:
    """Ensure native ComfyUI is healthy. Automatically discover and start a local install when allowed."""
    return await _ensure(auto_start=auto_start, wait_seconds=wait_seconds)


@mcp.tool()
async def health_check(auto_start: bool = True) -> Dict[str, Any]:
    """Return ComfyUI health/device/version details, starting the local backend automatically when needed."""
    ensured = await _ensure(auto_start=auto_start)
    return ensured["health"]


@mcp.tool()
async def discover_backends() -> List[Dict[str, Any]]:
    """List local ComfyUI installations EVAVO can automatically launch."""
    installs = await asyncio.to_thread(discover_comfyui)
    return [install.to_dict() for install in installs]


@mcp.tool()
async def list_checkpoints(auto_start: bool = True) -> List[str]:
    """List checkpoints exposed by ComfyUI, starting the backend automatically when needed."""
    await _ensure(auto_start=auto_start)
    return await asyncio.to_thread(_backend().checkpoints)


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
    """Generate through native ComfyUI. EVAVO can auto-start ComfyUI, wait for completion, and return downloaded files."""
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
    if wait:
        target = _output_dir(project_name, output_dir)
        downloaded = await asyncio.to_thread(backend.wait_and_download, result["task_id"], target, timeout=wait_timeout)
        result.update({"status": "completed", "downloaded_files": downloaded, "output_dir": str(target)})
    return result


@mcp.tool()
async def generation_status(task_id: str, auto_start: bool = False) -> Dict[str, Any]:
    """Check a ComfyUI prompt ID and return generated image outputs."""
    await _ensure(auto_start=auto_start)
    backend = _backend()
    history = await asyncio.to_thread(backend.history, task_id)
    outputs = await asyncio.to_thread(backend.outputs, task_id) if isinstance(history.get(task_id), dict) else []
    return {"task_id": task_id, "status": "completed" if outputs else "queued", "outputs": outputs}


@mcp.tool()
async def collect_generation(
    task_id: str,
    output_dir: Optional[str] = None,
    timeout: float = 600.0,
    auto_start: bool = False,
) -> Dict[str, Any]:
    """Wait for an existing prompt and download its images."""
    await _ensure(auto_start=auto_start)
    backend = _backend()
    target = _output_dir("collected", output_dir)
    downloaded = await asyncio.to_thread(backend.wait_and_download, task_id, target, timeout=timeout)
    return {"task_id": task_id, "status": "completed", "downloaded_files": downloaded, "output_dir": str(target)}


@mcp.tool()
async def stop_managed_backend() -> Dict[str, Any]:
    """Stop ComfyUI only when EVAVO itself started that native process."""
    return await asyncio.to_thread(stop_managed_comfyui)


def _transport_security(host: str, port: int) -> TransportSecuritySettings:
    """Use exact localhost host/origin allowlists instead of wildcard ports."""
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
