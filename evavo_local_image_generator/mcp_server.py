"""MCP v2 server for EVAVO Local Image Generator."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from mcp.server import MCPServer
except ImportError as exc:  # pragma: no cover - exercised by bootstrap/doctor environments
    raise RuntimeError('MCP SDK is required for agent integration. Install with: python -m pip install "mcp>=2,<3"') from exc

from .backends import ComfyUIBackend

mcp = MCPServer("EVAVO Local Image Generator")


def _backend() -> ComfyUIBackend:
    return ComfyUIBackend(os.getenv("EVAVO_COMFYUI_ENDPOINT") or os.getenv("COMFYUI_ENDPOINT") or "http://127.0.0.1:8188")


def _output_dir(project_name: str, output_dir: Optional[str]) -> Path:
    if output_dir:
        return Path(output_dir).expanduser().resolve()
    root = Path(os.getenv("EVAVO_GENERATION_OUTPUT_DIR", str(Path.cwd() / ".evavo" / "outputs"))).expanduser().resolve()
    safe_project = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in project_name)[:80] or "mcp"
    return root / safe_project


@mcp.tool()
async def health_check() -> Dict[str, Any]:
    """Check the native ComfyUI image-generation backend and return device/version details."""
    return await asyncio.to_thread(_backend().health)


@mcp.tool()
async def list_checkpoints() -> List[str]:
    """List checkpoints exposed by ComfyUI's CheckpointLoaderSimple node."""
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
) -> Dict[str, Any]:
    """Generate an image through native ComfyUI; optionally wait and download the resulting files."""
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
async def generation_status(task_id: str) -> Dict[str, Any]:
    """Check a ComfyUI prompt ID and return any generated image outputs."""
    backend = _backend()
    history = await asyncio.to_thread(backend.history, task_id)
    outputs = await asyncio.to_thread(backend.outputs, task_id) if isinstance(history.get(task_id), dict) else []
    return {"task_id": task_id, "status": "completed" if outputs else "queued", "outputs": outputs}


@mcp.tool()
async def collect_generation(task_id: str, output_dir: Optional[str] = None, timeout: float = 600.0) -> Dict[str, Any]:
    """Wait for an existing ComfyUI prompt ID and download all image outputs."""
    backend = _backend()
    target = _output_dir("collected", output_dir)
    downloaded = await asyncio.to_thread(backend.wait_and_download, task_id, target, timeout=timeout)
    return {"task_id": task_id, "status": "completed", "downloaded_files": downloaded, "output_dir": str(target)}


def main() -> None:
    """Run the MCP server over stdio for Claude/IDE/agent hosts."""
    mcp.run()


if __name__ == "__main__":
    main()
