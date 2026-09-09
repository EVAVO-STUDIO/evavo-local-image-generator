#!/usr/bin/env python3
"""EVAVO local image-generation HTTP compatibility gateway.

The gateway intentionally exposes one proven production capability: image
rendering through native ComfyUI. Historical video/audio/3D routes remain as
explicit 501 compatibility responses instead of pretending to queue work.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Literal, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from evavo_operations import TaskTracker
from evavo_local_image_generator.backends import ComfyUIBackend
from evavo_local_image_generator.comfyui_runtime import ensure_comfyui, native_health

ROOT = Path(__file__).resolve().parent
STATE_DIR = Path(os.getenv("EVAVO_GATEWAY_STATE_DIR", str(ROOT / ".evavo" / "gateway"))).expanduser().resolve()
TASK_STATE_FILE = Path(os.getenv("EVAVO_GATEWAY_TASK_FILE", str(STATE_DIR / "tasks.json"))).expanduser().resolve()
RESULT_DIR = Path(os.getenv("EVAVO_GATEWAY_RESULT_DIR", str(STATE_DIR / "results"))).expanduser().resolve()
COMFYUI_ENDPOINT = (os.getenv("COMFYUI_ENDPOINT") or os.getenv("EVAVO_COMFYUI_ENDPOINT") or "http://127.0.0.1:8188").rstrip("/")
GATEWAY_HOST = os.getenv("EVAVO_GATEWAY_HOST", "127.0.0.1")
GATEWAY_PORT = int(os.getenv("EVAVO_GATEWAY_PORT", "8000"))
MAX_PROMPT_CHARS = int(os.getenv("EVAVO_GATEWAY_MAX_PROMPT_CHARS", "100000"))
IMAGE_TIMEOUT_SECONDS = float(os.getenv("EVAVO_GATEWAY_IMAGE_TIMEOUT", "600"))


class GenerationRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_CHARS)


class TaskQueuedResponse(BaseModel):
    task_id: str
    status: Literal["queued"] = "queued"
    progress: int = 0


class TaskStore:
    """Small single-process task store with atomic persistence."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = asyncio.Lock()
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        tasks = payload.get("tasks") if isinstance(payload, dict) else None
        if isinstance(tasks, dict):
            self._tasks = {str(key): value for key, value in tasks.items() if isinstance(value, dict)}

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=self.path.name + ".", suffix=".tmp", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump({"version": 2, "tasks": self._tasks}, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.path)
        except Exception:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise

    async def put(self, task: Dict[str, Any]) -> Dict[str, Any]:
        async with self._lock:
            self._tasks[str(task["task_id"])] = dict(task)
            await asyncio.to_thread(self._write)
            return dict(task)

    async def update(self, task_id: str, **fields: Any) -> Dict[str, Any]:
        async with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise KeyError(task_id)
            task.update(fields)
            task["updated_at"] = _iso_now()
            await asyncio.to_thread(self._write)
            return dict(task)

    async def get(self, task_id: str) -> Optional[Dict[str, Any]]:
        async with self._lock:
            task = self._tasks.get(task_id)
            return dict(task) if task else None

    async def list(self, limit: int = 100) -> list[Dict[str, Any]]:
        async with self._lock:
            values = list(self._tasks.values())[-max(1, min(int(limit), 1000)) :]
            return [dict(item) for item in reversed(values)]

    async def recover_interrupted(self) -> None:
        changed = False
        async with self._lock:
            for task in self._tasks.values():
                if task.get("status") in {"queued", "running"}:
                    task.update(
                        status="failed",
                        progress=0,
                        error_code="GATEWAY_RESTARTED",
                        error="Gateway restarted before the task completed",
                        updated_at=_iso_now(),
                    )
                    changed = True
            if changed:
                await asyncio.to_thread(self._write)


STORE = TaskStore(TASK_STATE_FILE)
_BACKGROUND_TASKS: set[asyncio.Task[Any]] = set()


def _iso_now() -> str:
    from datetime import datetime

    return datetime.now().astimezone().isoformat()


def _next_task_id() -> str:
    return f"img_{time.time_ns()}"


def _public_task(task: Dict[str, Any]) -> Dict[str, Any]:
    hidden = {"request", "result_paths", "backend_task_id"}
    return {key: value for key, value in task.items() if key not in hidden} | {"result_ready": bool(task.get("result_paths"))}


async def _mirror_add(task: Dict[str, Any]) -> None:
    try:
        await asyncio.to_thread(
            TaskTracker().add_task,
            task["task_id"],
            task["prompt"],
            task["status"],
            project_name=str(task.get("project_name", "gateway")),
            backend_mode="native-comfyui",
        )
    except Exception:
        return


async def _mirror_update(task_id: str, status: str, **fields: Any) -> None:
    try:
        await asyncio.to_thread(TaskTracker().update_task, task_id, status, **fields)
    except Exception:
        return


async def _image_worker(task_id: str, request: Dict[str, Any]) -> None:
    prompt = str(request["prompt"]).strip()
    project_name = str(request.get("project_name", "gateway")).strip() or "gateway"
    try:
        await STORE.update(task_id, status="running", progress=5)
        await asyncio.to_thread(ensure_comfyui, COMFYUI_ENDPOINT, wait_seconds=90.0, allow_start=True)
        backend = ComfyUIBackend(COMFYUI_ENDPOINT)
        queued = await asyncio.to_thread(
            backend.queue_image,
            prompt,
            project_name=project_name,
            negative_prompt=str(request.get("negative_prompt", "")),
            width=request.get("width", 1024),
            height=request.get("height", 1024),
            steps=request.get("steps", 24),
            cfg_scale=request.get("cfg_scale", 7.0),
            seed=request.get("seed"),
            checkpoint=request.get("checkpoint"),
            workflow_path=request.get("workflow_path"),
        )
        backend_task_id = str(queued["task_id"])
        await STORE.update(
            task_id,
            progress=25,
            backend_task_id=backend_task_id,
            backend_mode="native-comfyui",
            checkpoint=queued.get("checkpoint"),
        )
        target = (RESULT_DIR / task_id).resolve()
        paths = await asyncio.to_thread(
            backend.wait_and_download,
            backend_task_id,
            target,
            timeout=float(request.get("wait_timeout", IMAGE_TIMEOUT_SECONDS)),
            interval=0.5,
        )
        if not paths:
            raise RuntimeError("COMFYUI_NO_OUTPUT:no image output was produced")
        await STORE.update(task_id, status="completed", progress=100, result_paths=paths)
        await _mirror_update(
            task_id,
            "completed",
            output_uris=[str(path) for path in paths],
            output_dir=str(target),
            backend_mode="native-comfyui",
            checkpoint=queued.get("checkpoint"),
            workflow_path=request.get("workflow_path"),
        )
    except Exception as exc:
        message = str(exc)
        code = message.split(":", 1)[0] if ":" in message else type(exc).__name__.upper()
        await STORE.update(task_id, status="failed", progress=0, error_code=code, error=message)
        await _mirror_update(task_id, "failed", error_code=code, error_message=message, backend_mode="native-comfyui")


def _launch(coro: Any) -> None:
    task = asyncio.create_task(coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


@asynccontextmanager
async def lifespan(_: FastAPI):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    await STORE.recover_interrupted()
    yield
    pending = list(_BACKGROUND_TASKS)
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


app = FastAPI(
    title="EVAVO Local Image Generator",
    version="2.0.0",
    description="Loopback-only native-ComfyUI image generation compatibility gateway.",
    lifespan=lifespan,
)

cors_raw = os.getenv("EVAVO_GATEWAY_CORS_ORIGINS", "").strip()
if cors_raw:
    cors_origins = [item.strip() for item in cors_raw.split(",") if item.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Accept"],
    )


@app.get("/health")
async def health() -> Dict[str, str]:
    native = await asyncio.to_thread(native_health, COMFYUI_ENDPOINT)
    if native:
        return {"status": "healthy", "gateway": "ok", "comfyui": "ok"}
    return {"status": "degraded", "gateway": "ok", "comfyui": "offline"}


@app.get("/capabilities")
async def capabilities() -> Dict[str, Any]:
    native = await asyncio.to_thread(native_health, COMFYUI_ENDPOINT)
    unsupported = {"ready": False, "reason": "not part of the proven evavo-local-image-generator production contract"}
    return {
        "image": {"endpoint": "/generate/image", "backend": "native-comfyui", "ready": bool(native)},
        "video": {"endpoint": "/generate/video", **unsupported},
        "audio": {"endpoint": "/generate/audio", **unsupported},
        "3d": {"endpoint": "/generate/3d", **unsupported},
        "progress_websocket": "/ws/progress/{task_id}",
    }


@app.post("/generate/image", response_model=TaskQueuedResponse, status_code=202)
async def generate_image(request: GenerationRequest) -> TaskQueuedResponse:
    payload = request.model_dump()
    prompt = payload["prompt"].strip()
    if not prompt:
        raise HTTPException(status_code=422, detail="prompt must not be whitespace only")
    task_id = _next_task_id()
    task = {
        "task_id": task_id,
        "type": "image",
        "status": "queued",
        "progress": 0,
        "prompt": prompt,
        "project_name": str(payload.get("project_name", "gateway")),
        "backend_mode": "native-comfyui",
        "created_at": _iso_now(),
        "updated_at": _iso_now(),
        "request": payload,
    }
    await STORE.put(task)
    await _mirror_add(task)
    _launch(_image_worker(task_id, payload))
    return TaskQueuedResponse(task_id=task_id)


def _unsupported_modality(kind: str) -> None:
    raise HTTPException(
        status_code=501,
        detail=f"{kind} generation is not implemented by the verified evavo-local-image-generator production runtime",
    )


@app.post("/generate/video")
async def generate_video(_: GenerationRequest) -> None:
    _unsupported_modality("video")


@app.post("/generate/audio")
async def generate_audio(_: GenerationRequest) -> None:
    _unsupported_modality("audio")


@app.post("/generate/3d")
async def generate_3d(_: GenerationRequest) -> None:
    _unsupported_modality("3d")


@app.get("/tasks")
async def list_tasks(limit: int = 100) -> Dict[str, Any]:
    tasks = await STORE.list(limit=limit)
    return {"tasks": [_public_task(task) for task in tasks]}


@app.get("/tasks/{task_id}/status")
async def task_status(task_id: str) -> Dict[str, Any]:
    task = await STORE.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return _public_task(task)


@app.get("/results/{task_id}")
async def result(task_id: str):
    task = await STORE.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.get("status") == "failed":
        return JSONResponse(
            status_code=409,
            content={
                "task_id": task_id,
                "status": "failed",
                "error_code": task.get("error_code"),
                "error": task.get("error"),
            },
        )
    paths = task.get("result_paths")
    if not isinstance(paths, list) or not paths:
        return JSONResponse(
            status_code=202,
            content={"task_id": task_id, "status": task.get("status", "queued"), "progress": int(task.get("progress", 0))},
        )
    candidate = Path(str(paths[0])).expanduser().resolve()
    task_root = (RESULT_DIR / task_id).resolve()
    try:
        authorized = candidate.is_relative_to(task_root)
    except ValueError:
        authorized = False
    if not authorized:
        raise HTTPException(status_code=410, detail="Recorded result path is outside the gateway result directory")
    if not candidate.is_file():
        raise HTTPException(status_code=410, detail="Result file is no longer available")
    return FileResponse(candidate, filename=candidate.name)


@app.websocket("/ws/progress/{task_id}")
async def progress_socket(websocket: WebSocket, task_id: str) -> None:
    await websocket.accept()
    last_payload: Optional[str] = None
    try:
        while True:
            task = await STORE.get(task_id)
            if task is None:
                await websocket.send_json({"task_id": task_id, "status": "not_found", "progress": 0})
                await websocket.close(code=4404)
                return
            public = _public_task(task)
            encoded = json.dumps(public, sort_keys=True, default=str)
            if encoded != last_payload:
                await websocket.send_json(public)
                last_payload = encoded
            if task.get("status") in {"completed", "failed", "cancelled"}:
                await websocket.close(code=1000)
                return
            await asyncio.sleep(0.25)
    except WebSocketDisconnect:
        return


def main() -> int:
    if GATEWAY_HOST not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("EVAVO_GATEWAY_HOST is restricted to loopback (127.0.0.1/localhost/::1)")
    if not 1 <= GATEWAY_PORT <= 65535:
        raise SystemExit("EVAVO_GATEWAY_PORT must be between 1 and 65535")
    import uvicorn

    uvicorn.run(app, host=GATEWAY_HOST, port=GATEWAY_PORT, log_level=os.getenv("EVAVO_GATEWAY_LOG_LEVEL", "info"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
