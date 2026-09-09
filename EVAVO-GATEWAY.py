#!/usr/bin/env python3
"""EVAVO Unified Gateway.

Stable FastAPI compatibility layer for ChatGPT, Claude, MCP adapters, and
other HTTP clients. Public endpoint paths and the task response shape are
intentionally conservative because external agents depend on them.
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

from evavo_operations import TaskTracker, interprocess_lock
from evavo_local_image_generator.backends import ComfyUIBackend
from evavo_local_image_generator.comfyui_runtime import ensure_comfyui, native_health

ROOT = Path(__file__).resolve().parent
STATE_DIR = Path(os.getenv("EVAVO_GATEWAY_STATE_DIR", str(ROOT / ".evavo" / "gateway"))).expanduser().resolve()
TASK_STATE_FILE = Path(os.getenv("EVAVO_GATEWAY_TASK_FILE", str(STATE_DIR / "tasks.json"))).expanduser().resolve()
RESULT_DIR = Path(os.getenv("EVAVO_GATEWAY_RESULT_DIR", str(STATE_DIR / "results"))).expanduser().resolve()
COMFYUI_ENDPOINT = (os.getenv("COMFYUI_ENDPOINT") or os.getenv("EVAVO_COMFYUI_ENDPOINT") or "http://127.0.0.1:8188").rstrip("/")
GATEWAY_HOST = os.getenv("EVAVO_GATEWAY_HOST", "127.0.0.1")
GATEWAY_PORT = int(os.getenv("EVAVO_GATEWAY_PORT", "8000"))
MAX_PROMPT_CHARS = max(1, min(int(os.getenv("EVAVO_GATEWAY_MAX_PROMPT_CHARS", "100000")), 1_000_000))
MAX_REQUEST_BYTES = max(4096, min(int(os.getenv("EVAVO_GATEWAY_MAX_REQUEST_BYTES", str(1024 * 1024))), 16 * 1024 * 1024))
MAX_PROJECT_CHARS = max(1, min(int(os.getenv("EVAVO_GATEWAY_MAX_PROJECT_CHARS", "128")), 1024))
IMAGE_TIMEOUT_SECONDS = max(1.0, min(float(os.getenv("EVAVO_GATEWAY_IMAGE_TIMEOUT", "600")), 86400.0))
TASK_ID_RE = re.compile(r"^(img|vid|aud|3d)_\d+$")
LOOPBACK_ORIGIN_RE = re.compile(r"^https?://(?:127\.0\.0\.1|localhost|\[::1\])(?::\d{1,5})?$", re.IGNORECASE)


def _env_true(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class RequestBodyLimitMiddleware:
    """Reject oversized HTTP request bodies before FastAPI/Pydantic parsing.

    Content-Length is rejected immediately when present. Bodies without a
    trustworthy length (including chunked transfer encoding) are consumed only
    up to the configured cap and then replayed to the application. This keeps
    the ingress memory bound aligned with the gateway's request contract.
    """

    def __init__(self, app: Any, max_bytes: int):
        self.app = app
        self.max_bytes = int(max_bytes)

    async def _reject(self, scope: Dict[str, Any], receive: Any, send: Any, status: int, detail: str) -> None:
        response = JSONResponse(status_code=status, content={"detail": detail})
        await response(scope, receive, send)

    async def __call__(self, scope: Dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or str(scope.get("method", "GET")).upper() not in {"POST", "PUT", "PATCH"}:
            await self.app(scope, receive, send)
            return

        content_length: Optional[int] = None
        for name, value in scope.get("headers", []):
            if bytes(name).lower() != b"content-length":
                continue
            try:
                content_length = int(bytes(value).decode("ascii"))
            except (UnicodeDecodeError, ValueError):
                await self._reject(scope, receive, send, 400, "invalid Content-Length header")
                return
            break
        if content_length is not None:
            if content_length < 0:
                await self._reject(scope, receive, send, 400, "invalid Content-Length header")
                return
            if content_length > self.max_bytes:
                await self._reject(scope, receive, send, 413, f"request exceeds EVAVO gateway limit of {self.max_bytes} bytes")
                return

        buffered: list[Dict[str, Any]] = []
        total = 0
        while True:
            message = await receive()
            buffered.append(message)
            if message.get("type") == "http.disconnect":
                break
            if message.get("type") != "http.request":
                break
            body = message.get("body", b"")
            total += len(body) if isinstance(body, (bytes, bytearray)) else 0
            if total > self.max_bytes:
                await self._reject(scope, receive, send, 413, f"request exceeds EVAVO gateway limit of {self.max_bytes} bytes")
                return
            if not message.get("more_body", False):
                break

        index = 0

        async def replay_receive() -> Dict[str, Any]:
            nonlocal index
            if index < len(buffered):
                message = buffered[index]
                index += 1
                return message
            return {"type": "http.request", "body": b"", "more_body": False}

        await self.app(scope, replay_receive, send)


class GenerationRequest(BaseModel):
    """Compatible generation request: prompt is stable, extra fields are additive."""

    model_config = ConfigDict(extra="allow")
    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_CHARS)


class TaskQueuedResponse(BaseModel):
    task_id: str
    status: Literal["queued"] = "queued"
    progress: int = 0


class TaskStore:
    """Atomic task store with process-local and cross-process serialization."""

    def __init__(self, path: Path):
        self.path = path
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        self._lock = asyncio.Lock()
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _read_unlocked(self) -> Dict[str, Dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"GATEWAY_TASK_STATE_CORRUPT:{self.path}:{exc}") from exc
        except OSError as exc:
            raise RuntimeError(f"GATEWAY_TASK_STATE_READ_ERROR:{self.path}:{exc}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError(f"GATEWAY_TASK_STATE_CORRUPT:{self.path}:root must be a JSON object")
        tasks = payload.get("tasks", payload)
        if not isinstance(tasks, dict):
            raise RuntimeError(f"GATEWAY_TASK_STATE_CORRUPT:{self.path}:tasks must be a JSON object")
        result: Dict[str, Dict[str, Any]] = {}
        for key, value in tasks.items():
            if not isinstance(value, dict):
                raise RuntimeError(f"GATEWAY_TASK_STATE_CORRUPT:{self.path}:task {key!r} must be an object")
            result[str(key)] = dict(value)
        return result

    def _load(self) -> None:
        with interprocess_lock(self.lock_path):
            self._tasks = self._read_unlocked()

    @staticmethod
    def _next_id(prefix: str, tasks: Dict[str, Dict[str, Any]]) -> str:
        previous = 0
        for task_id in tasks:
            match = TASK_ID_RE.fullmatch(task_id)
            if not match or match.group(1) != prefix:
                continue
            try:
                previous = max(previous, int(task_id.split("_", 1)[1]))
            except (IndexError, ValueError):
                continue
        now = int(time.time())
        value = now if now > previous else previous + 1
        return f"{prefix}_{value}"

    def _write_unlocked(self, tasks: Dict[str, Dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=self.path.name + ".", suffix=".tmp", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump({"version": 2, "tasks": tasks}, handle, indent=2, ensure_ascii=False)
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

    def _create_sync(self, prefix: str, task: Dict[str, Any]) -> Dict[str, Any]:
        with interprocess_lock(self.lock_path):
            tasks = self._read_unlocked()
            task_id = self._next_id(prefix, tasks)
            created = dict(task)
            created["task_id"] = task_id
            tasks[task_id] = created
            self._write_unlocked(tasks)
            self._tasks = tasks
            return dict(created)

    async def create(self, prefix: str, task: Dict[str, Any]) -> Dict[str, Any]:
        async with self._lock:
            return await asyncio.to_thread(self._create_sync, prefix, dict(task))

    def _put_sync(self, task: Dict[str, Any]) -> Dict[str, Any]:
        task_id = str(task["task_id"])
        with interprocess_lock(self.lock_path):
            tasks = self._read_unlocked()
            if task_id in tasks:
                raise RuntimeError(f"GATEWAY_TASK_ID_COLLISION:{task_id}")
            tasks[task_id] = dict(task)
            self._write_unlocked(tasks)
            self._tasks = tasks
            return dict(tasks[task_id])

    async def put(self, task: Dict[str, Any]) -> Dict[str, Any]:
        async with self._lock:
            return await asyncio.to_thread(self._put_sync, dict(task))

    def _update_sync(self, task_id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        with interprocess_lock(self.lock_path):
            tasks = self._read_unlocked()
            task = tasks.get(task_id)
            if task is None:
                raise KeyError(task_id)
            task.update(fields)
            task["updated_at"] = _iso_now()
            self._write_unlocked(tasks)
            self._tasks = tasks
            return dict(task)

    async def update(self, task_id: str, **fields: Any) -> Dict[str, Any]:
        async with self._lock:
            return await asyncio.to_thread(self._update_sync, task_id, dict(fields))

    def _get_sync(self, task_id: str) -> Optional[Dict[str, Any]]:
        with interprocess_lock(self.lock_path):
            tasks = self._read_unlocked()
            self._tasks = tasks
            task = tasks.get(task_id)
            return dict(task) if task is not None else None

    async def get(self, task_id: str) -> Optional[Dict[str, Any]]:
        async with self._lock:
            return await asyncio.to_thread(self._get_sync, task_id)

    def _list_sync(self, limit: int) -> list[Dict[str, Any]]:
        with interprocess_lock(self.lock_path):
            tasks = self._read_unlocked()
            self._tasks = tasks
            values = list(tasks.values())[-max(1, min(limit, 1000)) :]
            return [dict(item) for item in reversed(values)]

    async def list(self, limit: int = 100) -> list[Dict[str, Any]]:
        async with self._lock:
            return await asyncio.to_thread(self._list_sync, limit)

    def _recover_interrupted_sync(self) -> None:
        with interprocess_lock(self.lock_path):
            tasks = self._read_unlocked()
            changed = False
            for task in tasks.values():
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
                self._write_unlocked(tasks)
            self._tasks = tasks

    async def recover_interrupted(self) -> None:
        async with self._lock:
            await asyncio.to_thread(self._recover_interrupted_sync)


STORE = TaskStore(TASK_STATE_FILE)
_BACKGROUND_TASKS: set[asyncio.Task[Any]] = set()


def _iso_now() -> str:
    from datetime import datetime

    return datetime.now().astimezone().isoformat()


def _public_task(task: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: value
        for key, value in task.items()
        if key not in {"request", "result_paths", "backend_task_id", "provider_receipt"}
    } | {"result_ready": bool(task.get("result_paths"))}


def _bounded_wait_timeout(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = IMAGE_TIMEOUT_SECONDS
    return max(1.0, min(parsed, 86400.0))


async def _track_add(task: Dict[str, Any]) -> None:
    try:
        await asyncio.to_thread(
            TaskTracker().add_task,
            task["task_id"],
            task["prompt"],
            task["status"],
            project_name=str(task.get("project_name", "gateway")),
            backend_mode=str(task.get("backend_mode", "gateway")),
        )
    except Exception:
        return


async def _track_update(task_id: str, status: str, **fields: Any) -> None:
    try:
        await asyncio.to_thread(TaskTracker().update_task, task_id, status, **fields)
    except Exception:
        return


async def _check_comfyui_health() -> bool:
    return bool(await asyncio.to_thread(native_health, COMFYUI_ENDPOINT))


def _providers():
    from evavo_local_image_generator.provider_runner import ProviderRouter

    return ProviderRouter(ROOT, STATE_DIR, RESULT_DIR)


async def _image_worker(task_id: str, request: Dict[str, Any]) -> None:
    prompt = str(request["prompt"]).strip()
    project_name = str(request.get("project_name", "gateway")).strip()[:MAX_PROJECT_CHARS] or "gateway"
    workflow_path = request.get("workflow_path")
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
            workflow_path=str(workflow_path) if workflow_path else None,
        )
        backend_task_id = str(queued["task_id"])
        await STORE.update(task_id, progress=25, backend_task_id=backend_task_id, backend_mode="native-comfyui", checkpoint=queued.get("checkpoint"))
        target = (RESULT_DIR / task_id).resolve()
        paths = await asyncio.to_thread(
            backend.wait_and_download,
            backend_task_id,
            target,
            timeout=_bounded_wait_timeout(request.get("wait_timeout", IMAGE_TIMEOUT_SECONDS)),
            interval=0.5,
        )
        if not paths:
            raise RuntimeError("COMFYUI_NO_OUTPUT:no image output was produced")
        stored_paths = [str(path) for path in paths]
        await STORE.update(task_id, status="completed", progress=100, result_paths=stored_paths)
        await _track_update(
            task_id,
            "completed",
            output_uris=stored_paths,
            output_dir=str(target),
            backend_mode="native-comfyui",
            checkpoint=queued.get("checkpoint"),
            workflow_path=str(workflow_path) if workflow_path else None,
        )
    except Exception as exc:
        message = str(exc)
        code = message.split(":", 1)[0] if ":" in message else type(exc).__name__.upper()
        await STORE.update(task_id, status="failed", progress=0, error_code=code, error=message)
        await _track_update(task_id, "failed", error_code=code, error_message=message, backend_mode="native-comfyui")


async def _provider_worker(task_id: str, kind: str, request: Dict[str, Any]) -> None:
    """Delegate non-image modalities to their governed Studio execution surfaces."""
    try:
        from evavo_local_image_generator.provider_runner import ProviderError

        await STORE.update(task_id, status="running", progress=5)
        provider = _providers()
        result = await provider.generate(kind, task_id, request)
        if not result.paths:
            raise ProviderError("PROVIDER_OUTPUT_INVALID", "provider completed without an artifact")
        await STORE.update(
            task_id,
            status="completed",
            progress=100,
            result_paths=result.paths,
            provider_receipt=result.receipt,
            backend_mode=result.backend_mode,
        )
        await _track_update(
            task_id,
            "completed",
            output_uris=result.paths,
            output_dir=str(Path(result.paths[0]).parent),
            backend_mode=result.backend_mode,
        )
    except Exception as exc:
        message = str(exc)
        code = getattr(exc, "code", None) or (message.split(":", 1)[0] if ":" in message else type(exc).__name__.upper())
        await STORE.update(task_id, status="failed", progress=0, error_code=code, error=message)
        await _track_update(task_id, "failed", error_code=code, error_message=message)


def _launch(coro: Any) -> None:
    task = asyncio.create_task(coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


async def _queue(prefix: str, kind: str, request: GenerationRequest) -> TaskQueuedResponse:
    payload = request.model_dump()
    prompt = payload["prompt"].strip()
    if not prompt:
        raise HTTPException(status_code=422, detail="prompt must not be whitespace only")
    project_name = str(payload.get("project_name", "gateway")).strip()[:MAX_PROJECT_CHARS] or "gateway"
    payload["project_name"] = project_name
    if kind == "image" and payload.get("workflow_path") and not _env_true("EVAVO_GATEWAY_ALLOW_REQUEST_WORKFLOW_PATHS", False):
        raise HTTPException(
            status_code=403,
            detail="per-request workflow_path is disabled; configure EVAVO_COMFYUI_WORKFLOW or explicitly enable EVAVO_GATEWAY_ALLOW_REQUEST_WORKFLOW_PATHS",
        )
    try:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"request metadata is not JSON serializable: {exc}") from exc
    if len(encoded) > MAX_REQUEST_BYTES:
        raise HTTPException(status_code=413, detail=f"request exceeds EVAVO gateway limit of {MAX_REQUEST_BYTES} bytes")

    task = await STORE.create(
        prefix,
        {
            "type": kind,
            "status": "queued",
            "progress": 0,
            "prompt": prompt,
            "project_name": project_name,
            "created_at": _iso_now(),
            "updated_at": _iso_now(),
            "request": payload,
        },
    )
    task_id = str(task["task_id"])
    await _track_add(task)
    _launch(_image_worker(task_id, payload) if kind == "image" else _provider_worker(task_id, kind, payload))
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


def _configured_cors_origins() -> list[str]:
    """Return explicit loopback-only CORS origins; disabled by default."""
    raw = os.getenv("EVAVO_GATEWAY_CORS_ORIGINS", "").strip()
    if not raw:
        return []
    origins = [item.strip().rstrip("/") for item in raw.split(",") if item.strip()]
    invalid = [origin for origin in origins if origin == "*" or not LOOPBACK_ORIGIN_RE.fullmatch(origin)]
    if invalid:
        raise RuntimeError(
            "EVAVO_GATEWAY_CORS_ORIGINS accepts only explicit loopback http/https origins; invalid: " + ", ".join(invalid)
        )
    return list(dict.fromkeys(origins))


app = FastAPI(
    title="EVAVO Unified Generator",
    version="2.2.0",
    description="Stable local image gateway with governed auxiliary provider delegation for ChatGPT, Claude, MCP and HTTP clients.",
    lifespan=lifespan,
)

cors_origins = _configured_cors_origins()
if cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
app.add_middleware(RequestBodyLimitMiddleware, max_bytes=MAX_REQUEST_BYTES)


@app.get("/health")
async def health() -> Dict[str, str]:
    comfy_ok = await _check_comfyui_health()
    if comfy_ok:
        return {"status": "healthy", "gateway": "ok", "comfyui": "ok"}
    return {"status": "degraded", "gateway": "ok", "comfyui": "offline"}


@app.get("/services")
async def services() -> Dict[str, Any]:
    """Additive provider readiness detail; `/health` stays compatibility-stable."""
    comfy_ready = await _check_comfyui_health()
    return await _providers().services(comfyui_ready=comfy_ready)


@app.get("/capabilities")
async def capabilities() -> Dict[str, Any]:
    service_state = await services()
    return {
        "image": {
            "endpoint": "/generate/image",
            "backend": service_state["image"].get("backend", "ComfyUI"),
            "ready": bool(service_state["image"].get("ready")),
        },
        "video": {
            "endpoint": "/generate/video",
            "backend": service_state["video"].get("backend", "EVAVO Video Studio"),
            "ready": bool(service_state["video"].get("ready")),
        },
        "audio": {
            "endpoint": "/generate/audio",
            "backend": service_state["audio"].get("backend", "configured-cli"),
            "ready": bool(service_state["audio"].get("ready")),
        },
        "3d": {
            "endpoint": "/generate/3d",
            "backend": service_state["3d"].get("backend", "EVAVO 3D Studio worker"),
            "ready": bool(service_state["3d"].get("ready")),
        },
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
    if not TASK_ID_RE.fullmatch(task_id):
        raise HTTPException(status_code=404, detail="Task not found")
    task = await STORE.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return _public_task(task)


@app.get("/results/{task_id}")
async def result(task_id: str):
    if not TASK_ID_RE.fullmatch(task_id):
        raise HTTPException(status_code=404, detail="Task not found")
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
            content={
                "task_id": task_id,
                "status": task.get("status", "queued"),
                "progress": int(task.get("progress", 0)),
            },
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

    uvicorn.run(
        app,
        host=GATEWAY_HOST,
        port=GATEWAY_PORT,
        log_level=os.getenv("EVAVO_GATEWAY_LOG_LEVEL", "info"),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
