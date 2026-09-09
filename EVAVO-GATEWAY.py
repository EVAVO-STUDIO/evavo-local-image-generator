#!/usr/bin/env python3
"""EVAVO Unified Gateway.

Stable FastAPI compatibility layer for ChatGPT, Claude, MCP adapters, and
other HTTP clients. Public endpoint paths and the image task response shape
are intentionally conservative because external agents depend on them.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Literal, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parent
STATE_DIR = Path(os.getenv("EVAVO_GATEWAY_STATE_DIR", str(ROOT / "evavo-state"))).expanduser().resolve()
TASK_STATE_FILE = Path(os.getenv("EVAVO_GATEWAY_TASK_FILE", str(STATE_DIR / "gateway_tasks.json"))).expanduser().resolve()
RESULT_DIR = Path(os.getenv("EVAVO_GATEWAY_RESULT_DIR", str(STATE_DIR / "results"))).expanduser().resolve()
COMFYUI_ENDPOINT = os.getenv("EVAVO_COMFYUI_ENDPOINT", os.getenv("COMFYUI_ENDPOINT", "http://127.0.0.1:8188")).rstrip("/")
GATEWAY_HOST = os.getenv("EVAVO_GATEWAY_HOST", "127.0.0.1")
GATEWAY_PORT = int(os.getenv("EVAVO_GATEWAY_PORT", "8000"))
MAX_PROMPT_CHARS = int(os.getenv("EVAVO_GATEWAY_MAX_PROMPT_CHARS", "100000"))
IMAGE_TIMEOUT_SECONDS = float(os.getenv("EVAVO_GATEWAY_IMAGE_TIMEOUT", "600"))
TASK_ID_RE = re.compile(r"^(img|vid|aud|3d)_\d+$")


class GenerationRequest(BaseModel):
    """Compatible generation request: prompt is stable, extra fields are additive."""

    model_config = ConfigDict(extra="allow")
    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_CHARS)


class TaskQueuedResponse(BaseModel):
    task_id: str
    status: Literal["queued"] = "queued"
    progress: int = 0


class TaskStore:
    """Small atomic JSON task store with async serialization."""

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
        if isinstance(payload, dict):
            tasks = payload.get("tasks", payload)
            if isinstance(tasks, dict):
                self._tasks = {str(key): value for key, value in tasks.items() if isinstance(value, dict)}

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=self.path.name + ".", suffix=".tmp", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump({"version": 1, "tasks": self._tasks}, handle, indent=2, ensure_ascii=False)
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
            return dict(task) if task is not None else None

    async def list(self, limit: int = 100) -> list[Dict[str, Any]]:
        async with self._lock:
            values = list(self._tasks.values())[-max(1, min(limit, 1000)) :]
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
_LAST_EPOCH_BY_PREFIX: Dict[str, int] = {}


def _iso_now() -> str:
    from datetime import datetime

    return datetime.now().astimezone().isoformat()


def _next_task_id(prefix: str) -> str:
    now = int(time.time())
    previous = _LAST_EPOCH_BY_PREFIX.get(prefix, 0)
    value = now if now > previous else previous + 1
    _LAST_EPOCH_BY_PREFIX[prefix] = value
    return f"{prefix}_{value}"


def _public_task(task: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: value
        for key, value in task.items()
        if key not in {"request", "result_paths", "backend_task_id"}
    } | {"result_ready": bool(task.get("result_paths"))}


async def _track_add(task: Dict[str, Any]) -> None:
    try:
        from evavo_operations import TaskTracker

        await asyncio.to_thread(
            TaskTracker().add_task,
            task["task_id"],
            task["prompt"],
            task["status"],
            project_name=str(task.get("project_name", "gateway")),
            backend_mode=str(task.get("backend_mode", "gateway")),
        )
    except Exception:
        # Gateway state is authoritative for the HTTP contract; the shared
        # tracker is a best-effort compatibility mirror.
        return


async def _track_update(task_id: str, status: str, **fields: Any) -> None:
    try:
        from evavo_operations import TaskTracker

        await asyncio.to_thread(TaskTracker().update_task, task_id, status, **fields)
    except Exception:
        return


async def _check_comfyui_health() -> bool:
    try:
        from evavo_local_image_generator.backends import ComfyUIBackend

        result = await asyncio.to_thread(ComfyUIBackend(COMFYUI_ENDPOINT).health)
        return bool(result.get("healthy"))
    except Exception:
        return False


async def _image_worker(task_id: str, request: Dict[str, Any]) -> None:
    prompt = str(request["prompt"]).strip()
    project_name = str(request.get("project_name", "gateway")).strip() or "gateway"
    try:
        from evavo_local_image_generator.backends import ComfyUIBackend

        await STORE.update(task_id, status="running", progress=5)
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
        await STORE.update(task_id, progress=25, backend_task_id=backend_task_id, backend_mode="native-comfyui")
        target = RESULT_DIR / task_id
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
        await _track_update(task_id, "completed", output_uris=paths, output_dir=str(target), backend_mode="native-comfyui")
    except Exception as exc:
        message = str(exc)
        code = message.split(":", 1)[0] if ":" in message else type(exc).__name__.upper()
        await STORE.update(task_id, status="failed", progress=0, error_code=code, error=message)
        await _track_update(task_id, "failed", error_code=code, error_message=message)


async def _legacy_worker(task_id: str, kind: str, request: Dict[str, Any]) -> None:
    """Execute additive legacy modality adapters without changing HTTP contracts."""

    prompt = str(request["prompt"]).strip()
    try:
        await STORE.update(task_id, status="running", progress=5)
        if kind == "video":
            from evavo_local_image_generator.generators.video import VideoGenerator

            result = await VideoGenerator(COMFYUI_ENDPOINT).generate_video(
                prompt,
                duration=float(request.get("duration", 5.0)),
                fps=int(request.get("fps", 24)),
                negative_prompt=request.get("negative_prompt"),
            )
        elif kind == "audio":
            from evavo_local_image_generator.generators.audio import AudioGenerator

            generator = AudioGenerator(os.getenv("EVAVO_KOKORO_ENDPOINT", "http://127.0.0.1:8880"))
            mode = str(request.get("mode", "tts")).lower()
            if mode == "music":
                result = await generator.generate_music(prompt, duration=float(request.get("duration", 30.0)), genre=request.get("genre"))
            elif mode == "sfx":
                result = await generator.generate_sfx(prompt, duration=float(request.get("duration", 2.0)))
            else:
                result = await generator.text_to_speech(prompt, voice=str(request.get("voice", "default")), language=str(request.get("language", "en")))
        elif kind == "3d":
            from evavo_local_image_generator.generators.model_3d import Model3DGenerator

            result = await Model3DGenerator().generate_model(
                prompt,
                format=str(request.get("format", "gltf")),
                negative_prompt=request.get("negative_prompt"),
            )
        else:
            raise RuntimeError(f"UNSUPPORTED_GENERATOR:{kind}")

        paths: list[str] = []
        if isinstance(result, dict):
            for key in ("path", "output", "output_path", "file"):
                value = result.get(key)
                if isinstance(value, str) and Path(value).is_file():
                    paths.append(str(Path(value).resolve()))
        await STORE.update(task_id, status="completed", progress=100, result_paths=paths, result=result)
        await _track_update(task_id, "completed", output_uris=paths or None)
    except Exception as exc:
        message = str(exc)
        code = "NOT_IMPLEMENTED" if isinstance(exc, NotImplementedError) else (message.split(":", 1)[0] if ":" in message else type(exc).__name__.upper())
        await STORE.update(task_id, status="failed", progress=0, error_code=code, error=message)
        await _track_update(task_id, "failed", error_code=code, error_message=message)


def _launch(coro: Any) -> None:
    task = asyncio.create_task(coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


async def _queue(prefix: str, kind: str, request: GenerationRequest) -> TaskQueuedResponse:
    payload = request.model_dump()
    prompt = payload["prompt"].strip()
    task_id = _next_task_id(prefix)
    task = {
        "task_id": task_id,
        "type": kind,
        "status": "queued",
        "progress": 0,
        "prompt": prompt,
        "project_name": str(payload.get("project_name", "gateway")),
        "created_at": _iso_now(),
        "updated_at": _iso_now(),
        "request": payload,
    }
    await STORE.put(task)
    await _track_add(task)
    _launch(_image_worker(task_id, payload) if kind == "image" else _legacy_worker(task_id, kind, payload))
    return TaskQueuedResponse(task_id=task_id)


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
    title="EVAVO Unified Generator",
    version="1.0.0",
    description="Stable local multi-modal generation gateway for ChatGPT, Claude, MCP and HTTP clients.",
    lifespan=lifespan,
)

cors_raw = os.getenv("EVAVO_GATEWAY_CORS_ORIGINS", "*")
cors_origins = [item.strip() for item in cors_raw.split(",") if item.strip()] or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> Dict[str, str]:
    comfy_ok = await _check_comfyui_health()
    if comfy_ok:
        # This exact healthy response is a compatibility contract.
        return {"status": "healthy", "gateway": "ok", "comfyui": "ok"}
    return {"status": "degraded", "gateway": "ok", "comfyui": "offline"}


@app.get("/capabilities")
async def capabilities() -> Dict[str, Any]:
    return {
        "image": {"endpoint": "/generate/image", "backend": "ComfyUI", "ready": await _check_comfyui_health()},
        "video": {"endpoint": "/generate/video", "backend": "legacy adapter"},
        "audio": {"endpoint": "/generate/audio", "backend": "Kokoro adapter"},
        "3d": {"endpoint": "/generate/3d", "backend": "legacy adapter"},
        "progress_websocket": "/ws/progress/{task_id}",
    }


@app.post("/generate/image", response_model=TaskQueuedResponse, status_code=202)
async def generate_image(request: GenerationRequest) -> TaskQueuedResponse:
    return await _queue("img", "image", request)


@app.post("/generate/video", response_model=TaskQueuedResponse, status_code=202)
async def generate_video(request: GenerationRequest) -> TaskQueuedResponse:
    return await _queue("vid", "video", request)


@app.post("/generate/audio", response_model=TaskQueuedResponse, status_code=202)
async def generate_audio(request: GenerationRequest) -> TaskQueuedResponse:
    return await _queue("aud", "audio", request)


@app.post("/generate/3d", response_model=TaskQueuedResponse, status_code=202)
async def generate_3d(request: GenerationRequest) -> TaskQueuedResponse:
    return await _queue("3d", "3d", request)


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
        return JSONResponse(status_code=409, content={"task_id": task_id, "status": "failed", "error_code": task.get("error_code"), "error": task.get("error")})
    paths = task.get("result_paths")
    if not isinstance(paths, list) or not paths:
        return JSONResponse(status_code=202, content={"task_id": task_id, "status": task.get("status", "queued"), "progress": int(task.get("progress", 0))})
    candidate = Path(str(paths[0])).expanduser().resolve()
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
    if GATEWAY_HOST not in {"127.0.0.1", "localhost", "::1", "0.0.0.0"}:
        raise SystemExit("EVAVO_GATEWAY_HOST must be a loopback address or 0.0.0.0")
    if not 1 <= GATEWAY_PORT <= 65535:
        raise SystemExit("EVAVO_GATEWAY_PORT must be between 1 and 65535")
    import uvicorn

    uvicorn.run(app, host=GATEWAY_HOST, port=GATEWAY_PORT, log_level=os.getenv("EVAVO_GATEWAY_LOG_LEVEL", "info"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
