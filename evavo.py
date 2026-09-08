#!/usr/bin/env python3
"""Unified Python control CLI for EVAVO local image generator operations."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

from evavo_operations import DEFAULT_ENDPOINT, ROOT, now_iso, request_json, validate_health

STATE_DIR = ROOT / ".evavo"
STATE_FILE = STATE_DIR / "operations-service.json"
LOG_FILE = STATE_DIR / "mock-service.log"
SERVER = ROOT / "mock-comfyui-server.py"


def service_health(endpoint: str) -> Dict[str, Any]:
    return validate_health(request_json(f"{endpoint.rstrip('/')}/system", timeout=2.0))


def save_state(pid: int, endpoint: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps({"pid": pid, "endpoint": endpoint, "started_at": now_iso()}, indent=2) + "\n",
        encoding="utf-8",
    )


def load_state() -> Dict[str, Any]:
    if not STATE_FILE.exists():
        return {}
    try:
        payload = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def start_service(endpoint: str, wait_seconds: float = 20.0) -> int:
    endpoint = endpoint.rstrip("/")
    try:
        health = service_health(endpoint)
        print(json.dumps({"ok": True, "status": "already_running", "endpoint": endpoint, "health": health}, indent=2))
        return 0
    except RuntimeError:
        pass

    if endpoint != "http://127.0.0.1:8188":
        print("ERROR: managed mock service start currently uses http://127.0.0.1:8188 only.", file=sys.stderr)
        return 2
    if not SERVER.exists():
        print(f"ERROR: missing server: {SERVER}", file=sys.stderr)
        return 2

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    log_handle = LOG_FILE.open("ab", buffering=0)
    kwargs: Dict[str, Any] = {
        "cwd": str(ROOT),
        "stdin": subprocess.DEVNULL,
        "stdout": log_handle,
        "stderr": subprocess.STDOUT,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True

    try:
        process = subprocess.Popen([sys.executable, str(SERVER)], **kwargs)
    finally:
        log_handle.close()
    save_state(process.pid, endpoint)

    deadline = time.monotonic() + wait_seconds
    last_error = "service not ready"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            last_error = f"server exited with code {process.returncode}"
            break
        try:
            health = service_health(endpoint)
            print(
                json.dumps(
                    {
                        "ok": True,
                        "status": "started",
                        "pid": process.pid,
                        "endpoint": endpoint,
                        "log_file": str(LOG_FILE),
                        "health": health,
                    },
                    indent=2,
                )
            )
            return 0
        except RuntimeError as exc:
            last_error = str(exc)
            time.sleep(0.25)

    print(f"ERROR: EVAVO service failed to become ready: {last_error}", file=sys.stderr)
    print(f"Log: {LOG_FILE}", file=sys.stderr)
    return 3


def stop_service() -> int:
    state = load_state()
    pid = state.get("pid")
    if not isinstance(pid, int) or pid <= 0:
        print(json.dumps({"ok": True, "status": "not_managed", "message": "No managed EVAVO service PID is recorded."}, indent=2))
        return 0

    try:
        if os.name == "nt":
            result = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode not in {0, 128} and "not found" not in result.stderr.lower():
                print(f"ERROR: taskkill failed: {result.stderr.strip()}", file=sys.stderr)
                return 1
        else:
            try:
                os.killpg(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    finally:
        try:
            STATE_FILE.unlink()
        except OSError:
            pass
    print(json.dumps({"ok": True, "status": "stopped", "pid": pid}, indent=2))
    return 0


def status_service(endpoint: str) -> int:
    try:
        health = service_health(endpoint)
        print(json.dumps({"ok": True, "status": "operational", "endpoint": endpoint, "health": health, "managed": load_state()}, indent=2))
        return 0
    except RuntimeError as exc:
        print(json.dumps({"ok": False, "status": "offline", "endpoint": endpoint, "error": str(exc), "managed": load_state()}, indent=2))
        return 3


def run_passthrough(script: str, arguments: List[str]) -> int:
    command = [sys.executable, str(ROOT / script), *arguments]
    return subprocess.run(command, cwd=str(ROOT)).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="EVAVO local image generator operations controller")
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="Start and verify the managed local service")
    start.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    start.add_argument("--wait", type=float, default=20.0, help="Readiness timeout in seconds")

    stop = subparsers.add_parser("stop", help="Stop the managed local service")

    status = subparsers.add_parser("status", help="Check the service")
    status.add_argument("--endpoint", default=DEFAULT_ENDPOINT)

    generate = subparsers.add_parser("generate", help="Queue a batch of image prompts")
    generate.add_argument("--prompts", nargs="+")
    generate.add_argument("--examples", action="store_true")
    generate.add_argument("--project", default="batch_gen")
    generate.add_argument("--concurrency", type=int, default=4)
    generate.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    generate.add_argument("--json", action="store_true")

    tasks = subparsers.add_parser("tasks", help="List task history")
    tasks.add_argument("--limit", type=int, default=20)
    tasks.add_argument("--project")
    tasks.add_argument("--json", action="store_true")

    stats = subparsers.add_parser("stats", help="Show task statistics")
    stats.add_argument("--json", action="store_true")

    tests = subparsers.add_parser("test", help="Run operational integration tests")

    args = parser.parse_args()

    if args.command == "start":
        if args.wait <= 0:
            parser.error("--wait must be greater than zero")
        return start_service(args.endpoint, args.wait)
    if args.command == "stop":
        return stop_service()
    if args.command == "status":
        return status_service(args.endpoint.rstrip("/"))
    if args.command == "generate":
        forwarded: List[str] = ["--project", args.project, "--concurrency", str(args.concurrency), "--endpoint", args.endpoint]
        if args.prompts:
            forwarded.extend(["--prompts", *args.prompts])
        elif args.examples:
            forwarded.append("--examples")
        else:
            parser.error("generate requires --prompts or --examples")
        if args.json:
            forwarded.append("--json")
        return run_passthrough("generate-batch.py", forwarded)
    if args.command == "tasks":
        forwarded = ["list", "--limit", str(args.limit)]
        if args.project:
            forwarded.extend(["--project", args.project])
        if args.json:
            forwarded.append("--json")
        return run_passthrough("task-tracker.py", forwarded)
    if args.command == "stats":
        forwarded = ["stats"] + (["--json"] if args.json else [])
        return run_passthrough("task-tracker.py", forwarded)
    if args.command == "test":
        return run_passthrough("test-operations.py", [])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
