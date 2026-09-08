#!/usr/bin/env python3
"""Minimal local ComfyUI-compatible HTTP service for EVAVO operations.

This is intentionally a mock queue service: it validates request shape,
issues task IDs, exposes deterministic health/status endpoints and never binds
outside loopback unless the operator explicitly edits the script.
"""

from __future__ import annotations

import argparse
import json
import threading
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict

from evavo_operations import PROTOCOL_VERSION, SERVICE_NAME, now_iso

TASKS: Dict[str, Dict[str, Any]] = {}
TASKS_LOCK = threading.Lock()
STARTED_AT = now_iso()


class EvavoMockHandler(BaseHTTPRequestHandler):
    server_version = "EVAVOMockComfyUI/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[{datetime.now().astimezone().isoformat()}] {self.client_address[0]} {fmt % args}")

    def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self, max_bytes: int = 1024 * 1024) -> Dict[str, Any]:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length <= 0:
            raise ValueError("request body is required")
        if length > max_bytes:
            raise OverflowError("request body exceeds 1 MiB")
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("request body must be valid UTF-8 JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("request JSON root must be an object")
        return payload

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/system":
            self._send_json(
                200,
                {
                    "service": SERVICE_NAME,
                    "protocol_version": PROTOCOL_VERSION,
                    "status": "ready",
                    "mode": "mock",
                    "started_at": STARTED_AT,
                    "timestamp": now_iso(),
                },
            )
            return

        if self.path == "/api/status":
            with TASKS_LOCK:
                counts: Dict[str, int] = {}
                for task in TASKS.values():
                    state = str(task.get("status", "unknown"))
                    counts[state] = counts.get(state, 0) + 1
                total = len(TASKS)
            self._send_json(
                200,
                {
                    "service": SERVICE_NAME,
                    "protocol_version": PROTOCOL_VERSION,
                    "status": "ready",
                    "mode": "mock",
                    "queue": {"total": total, "by_status": counts},
                    "timestamp": now_iso(),
                },
            )
            return

        self._send_json(404, {"status": "failed", "error_code": "NOT_FOUND", "path": self.path})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/prompt":
            self._send_json(404, {"status": "failed", "error_code": "NOT_FOUND", "path": self.path})
            return

        try:
            payload = self._read_json()
        except OverflowError as exc:
            self._send_json(413, {"status": "failed", "error_code": "REQUEST_TOO_LARGE", "message": str(exc)})
            return
        except ValueError as exc:
            self._send_json(400, {"status": "failed", "error_code": "INVALID_REQUEST", "message": str(exc)})
            return

        prompt = payload.get("prompt")
        project_name = payload.get("project_name", "default")
        if not isinstance(prompt, str) or not prompt.strip():
            self._send_json(400, {"status": "failed", "error_code": "INVALID_PROMPT", "message": "prompt must be a non-empty string"})
            return
        if len(prompt) > 100_000:
            self._send_json(400, {"status": "failed", "error_code": "PROMPT_TOO_LONG", "message": "prompt exceeds 100000 characters"})
            return
        if not isinstance(project_name, str) or not project_name.strip():
            self._send_json(400, {"status": "failed", "error_code": "INVALID_PROJECT", "message": "project_name must be a non-empty string"})
            return

        task_id = f"evavo_{uuid.uuid4().hex}"
        task = {
            "task_id": task_id,
            "status": "queued",
            "prompt": prompt,
            "project_name": project_name,
            "created_at": now_iso(),
        }
        with TASKS_LOCK:
            TASKS[task_id] = task

        self._send_json(
            202,
            {
                "service": SERVICE_NAME,
                "protocol_version": PROTOCOL_VERSION,
                "status": "queued",
                "task_id": task_id,
                "project_name": project_name,
                "timestamp": now_iso(),
            },
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="EVAVO local mock ComfyUI service")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: loopback only)")
    parser.add_argument("--port", type=int, default=8188, help="Bind port")
    args = parser.parse_args()

    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("mock service is restricted to loopback; use 127.0.0.1")
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")

    server = ThreadingHTTPServer((args.host, args.port), EvavoMockHandler)
    print(f"EVAVO mock ComfyUI service ready at http://{args.host}:{args.port}")
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("\nStopping EVAVO mock ComfyUI service...")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
