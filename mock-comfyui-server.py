#!/usr/bin/env python3
"""Local deterministic EVAVO/native-ComfyUI simulator for operational tests."""

from __future__ import annotations

import argparse
import base64
import json
import threading
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict
from urllib.parse import unquote, urlparse

from evavo_operations import PROTOCOL_VERSION, SERVICE_NAME, now_iso

TASKS: Dict[str, Dict[str, Any]] = {}
TASKS_LOCK = threading.Lock()
STARTED_AT = now_iso()
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl1e6sAAAAASUVORK5CYII="
)


def _choice_node(input_name: str, values: list[str]) -> Dict[str, Any]:
    return {"input": {"required": {input_name: [values, {}]}}}


NATIVE_NODES: Dict[str, Dict[str, Any]] = {
    "CheckpointLoaderSimple": _choice_node("ckpt_name", ["evavo-test-model.safetensors"]),
    "LoraLoader": _choice_node("lora_name", ["evavo-test-lora.safetensors"]),
    "VAELoader": _choice_node("vae_name", ["evavo-test-vae.safetensors"]),
    "ControlNetLoader": _choice_node("control_net_name", ["evavo-test-controlnet.safetensors"]),
    "UNETLoader": _choice_node("unet_name", ["evavo-test-unet.safetensors"]),
    "CLIPLoader": _choice_node("clip_name", ["evavo-test-clip.safetensors"]),
    "CLIPVisionLoader": _choice_node("clip_name", ["evavo-test-clip-vision.safetensors"]),
    "UpscaleModelLoader": _choice_node("model_name", ["evavo-test-upscaler.pth"]),
    "CLIPTextEncode": {"input": {"required": {}}},
    "EmptyLatentImage": {"input": {"required": {}}},
    "KSampler": {"input": {"required": {}}},
    "VAEDecode": {"input": {"required": {}}},
    "SaveImage": {"input": {"required": {}}},
}


class EvavoMockHandler(BaseHTTPRequestHandler):
    server_version = "EVAVOMockComfyUI/2.3"

    @property
    def native_only(self) -> bool:
        return bool(getattr(self.server, "native_only", False))

    @property
    def no_checkpoint_loader(self) -> bool:
        return bool(getattr(self.server, "no_checkpoint_loader", False))

    def _native_nodes(self) -> Dict[str, Dict[str, Any]]:
        if not self.no_checkpoint_loader:
            return NATIVE_NODES
        return {name: value for name, value in NATIVE_NODES.items() if name != "CheckpointLoaderSimple"}

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[{datetime.now().astimezone().isoformat()}] {self.client_address[0]} {fmt % args}")

    def _send_bytes(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
        self._send_bytes(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _read_json(self, max_bytes: int = 1024 * 1024) -> Dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length <= 0:
            raise ValueError("request body is required")
        if length > max_bytes:
            raise OverflowError("request body exceeds 1 MiB")
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("request body must be valid UTF-8 JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("request JSON root must be an object")
        return payload

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/system" and not self.native_only:
            self._send_json(200, {"service": SERVICE_NAME, "protocol_version": PROTOCOL_VERSION, "status": "ready", "mode": "mock", "started_at": STARTED_AT, "timestamp": now_iso()})
            return
        if path == "/api/status" and not self.native_only:
            with TASKS_LOCK:
                total = len(TASKS)
            self._send_json(200, {"service": SERVICE_NAME, "protocol_version": PROTOCOL_VERSION, "status": "ready", "mode": "mock", "queue": {"total": total}, "timestamp": now_iso()})
            return
        if path == "/system_stats":
            self._send_json(200, {"system": {"comfyui_version": "test-native-1.0", "python_version": "test"}, "devices": [{"name": "EVAVO Test GPU", "vram_total": 8589934592, "vram_free": 6442450944}]})
            return
        if path == "/object_info":
            self._send_json(200, self._native_nodes())
            return
        if path.startswith("/object_info/"):
            node_name = unquote(path[len("/object_info/"):])
            node = self._native_nodes().get(node_name)
            if node is None:
                self._send_json(404, {"error": "unknown_node", "node": node_name})
            else:
                self._send_json(200, {node_name: node})
            return
        if path.startswith("/history/"):
            prompt_id = path.rsplit("/", 1)[-1]
            with TASKS_LOCK:
                task = TASKS.get(prompt_id)
            if task is None:
                self._send_json(200, {})
            else:
                self._send_json(200, {prompt_id: {"status": {"completed": True}, "outputs": {"7": {"images": [{"filename": f"{prompt_id}.png", "subfolder": "EVAVO/test", "type": "output"}]}}}})
            return
        if path == "/view":
            self._send_bytes(200, PNG_1X1, "image/png")
            return
        self._send_json(404, {"status": "failed", "error_code": "NOT_FOUND", "path": path})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            payload = self._read_json()
        except OverflowError as exc:
            self._send_json(413, {"status": "failed", "error_code": "REQUEST_TOO_LARGE", "message": str(exc)})
            return
        except ValueError as exc:
            self._send_json(400, {"status": "failed", "error_code": "INVALID_REQUEST", "message": str(exc)})
            return

        if path == "/api/prompt" and not self.native_only:
            prompt = payload.get("prompt")
            project_name = payload.get("project_name", "default")
            if not isinstance(prompt, str) or not prompt.strip():
                self._send_json(400, {"status": "failed", "error_code": "INVALID_PROMPT", "message": "prompt must be a non-empty string"})
                return
            task_id = f"evavo_{uuid.uuid4().hex}"
            with TASKS_LOCK:
                TASKS[task_id] = {"task_id": task_id, "status": "queued", "prompt": prompt, "project_name": project_name, "created_at": now_iso()}
            self._send_json(202, {"service": SERVICE_NAME, "protocol_version": PROTOCOL_VERSION, "status": "queued", "task_id": task_id, "project_name": project_name, "timestamp": now_iso()})
            return

        if path == "/prompt":
            workflow = payload.get("prompt")
            if not isinstance(workflow, dict) or not workflow:
                self._send_json(400, {"error": "invalid_prompt", "node_errors": {"workflow": "workflow must be a non-empty object"}})
                return
            prompt_id = str(uuid.uuid4())
            with TASKS_LOCK:
                TASKS[prompt_id] = {"task_id": prompt_id, "status": "completed", "workflow": workflow, "created_at": now_iso()}
            self._send_json(200, {"prompt_id": prompt_id, "number": 1, "node_errors": {}})
            return

        self._send_json(404, {"status": "failed", "error_code": "NOT_FOUND", "path": path})


def main() -> int:
    parser = argparse.ArgumentParser(description="EVAVO local ComfyUI simulator")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8188)
    parser.add_argument("--native-only", action="store_true", help="Expose only native ComfyUI routes")
    parser.add_argument("--no-checkpoint-loader", action="store_true", help="Simulate a native workflow environment without CheckpointLoaderSimple")
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("mock service is restricted to loopback; use 127.0.0.1")
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    server = ThreadingHTTPServer((args.host, args.port), EvavoMockHandler)
    server.native_only = args.native_only  # type: ignore[attr-defined]
    server.no_checkpoint_loader = args.no_checkpoint_loader  # type: ignore[attr-defined]
    print(f"EVAVO ComfyUI simulator ready at http://{args.host}:{args.port} native_only={args.native_only} no_checkpoint_loader={args.no_checkpoint_loader}")
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
