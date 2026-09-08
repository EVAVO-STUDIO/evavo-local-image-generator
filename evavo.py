#!/usr/bin/env python3
"""Unified Python control CLI for EVAVO local image generator operations."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import signal
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Tuple

from evavo_operations import DEFAULT_ENDPOINT, ROOT, now_iso, request_json, validate_health
from evavo_local_image_generator.backends import ComfyUIBackend

STATE_DIR = ROOT / ".evavo"
STATE_FILE = STATE_DIR / "operations-service.json"
LOG_FILE = STATE_DIR / "mock-service.log"
SERVER = ROOT / "mock-comfyui-server.py"
REQUIRED_FILES = [
    "evavo.py",
    "evavo_operations.py",
    "evavo-wrapper.py",
    "mock-comfyui-server.py",
    "generate-batch.py",
    "monitor-evavo.py",
    "task-tracker.py",
    "test-operations.py",
    "evavo_local_image_generator/backends/comfyui_backend.py",
]


def service_health(endpoint: str) -> Dict[str, Any]:
    """Return health for EVAVO compatibility service or native ComfyUI."""
    endpoint = endpoint.rstrip("/")
    try:
        health = validate_health(request_json(f"{endpoint}/system", timeout=2.0))
        return {"healthy": True, "service": health.get("service"), "mode": health.get("mode", "mock"), **health}
    except RuntimeError as evavo_error:
        try:
            return ComfyUIBackend(endpoint).health()
        except RuntimeError as native_error:
            raise RuntimeError(f"BACKEND_UNAVAILABLE:EVAVO={evavo_error}; ComfyUI={native_error}") from native_error


def parse_managed_endpoint(endpoint: str) -> Tuple[str, int, str]:
    """Validate a local-only HTTP endpoint and return host, port, normalized URL."""
    parsed = urllib.parse.urlparse(endpoint.rstrip("/"))
    if parsed.scheme != "http" or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("managed endpoint must be a plain loopback HTTP URL")
    if parsed.path not in {"", "/"}:
        raise ValueError("managed endpoint must not contain a path")
    host = parsed.hostname
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("managed mock service is restricted to 127.0.0.1/localhost")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("managed endpoint contains an invalid port") from exc
    if port is None or not 1 <= port <= 65535:
        raise ValueError("managed endpoint must include a valid port")
    bind_host = "127.0.0.1" if host == "localhost" else host
    return bind_host, port, f"http://{bind_host}:{port}"


def save_state(pid: int, endpoint: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps({"pid": pid, "endpoint": endpoint, "started_at": now_iso()}, indent=2) + "\n", encoding="utf-8")


def load_state() -> Dict[str, Any]:
    if not STATE_FILE.exists():
        return {}
    try:
        payload = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def clear_state() -> None:
    try:
        STATE_FILE.unlink()
    except (FileNotFoundError, OSError):
        pass


def terminate_pid(pid: int) -> None:
    if pid <= 0:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True, timeout=10)
    else:
        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


def start_service(endpoint: str, wait_seconds: float = 20.0) -> int:
    try:
        bind_host, port, endpoint = parse_managed_endpoint(endpoint)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    try:
        health = service_health(endpoint)
        print(json.dumps({"ok": True, "status": "already_running", "endpoint": endpoint, "health": health}, indent=2))
        return 0
    except RuntimeError:
        pass

    if not SERVER.exists():
        print(f"ERROR: missing server: {SERVER}", file=sys.stderr)
        return 2

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    log_handle = LOG_FILE.open("ab", buffering=0)
    kwargs: Dict[str, Any] = {"cwd": str(ROOT), "stdin": subprocess.DEVNULL, "stdout": log_handle, "stderr": subprocess.STDOUT}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True

    try:
        process = subprocess.Popen([sys.executable, str(SERVER), "--host", bind_host, "--port", str(port)], **kwargs)
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
            print(json.dumps({"ok": True, "status": "started", "pid": process.pid, "endpoint": endpoint, "log_file": str(LOG_FILE), "health": health}, indent=2))
            return 0
        except RuntimeError as exc:
            last_error = str(exc)
            time.sleep(0.25)

    if process.poll() is None:
        terminate_pid(process.pid)
    clear_state()
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
            result = subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True, timeout=10)
            combined = f"{result.stdout}\n{result.stderr}".lower()
            if result.returncode != 0 and not any(text in combined for text in ("not found", "no running instance", "not running")):
                print(f"ERROR: taskkill failed: {(result.stderr or result.stdout).strip()}", file=sys.stderr)
                return 1
        else:
            try:
                os.killpg(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    finally:
        clear_state()
    print(json.dumps({"ok": True, "status": "stopped", "pid": pid}, indent=2))
    return 0


def status_service(endpoint: str) -> int:
    endpoint = endpoint.rstrip("/")
    try:
        health = service_health(endpoint)
        print(json.dumps({"ok": True, "status": "operational", "endpoint": endpoint, "health": health, "managed": load_state()}, indent=2))
        return 0
    except RuntimeError as exc:
        print(json.dumps({"ok": False, "status": "offline", "endpoint": endpoint, "error": str(exc), "managed": load_state()}, indent=2))
        return 3


def run_passthrough(script: str, arguments: List[str]) -> int:
    return subprocess.run([sys.executable, str(ROOT / script), *arguments], cwd=str(ROOT)).returncode


def run_git(*arguments: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *arguments], cwd=str(ROOT), capture_output=True, text=True, timeout=timeout)


def git_value(*arguments: str) -> str | None:
    try:
        result = run_git(*arguments, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def doctor(endpoint: str, json_output: bool = False) -> int:
    checks: List[Dict[str, Any]] = []
    def add(name: str, ok: bool, detail: str, severity: str = "error") -> None:
        checks.append({"name": name, "ok": ok, "severity": severity, "detail": detail})

    add("python", sys.version_info >= (3, 10), f"{sys.version.split()[0]} at {sys.executable}")
    missing = [name for name in REQUIRED_FILES if not (ROOT / name).is_file()]
    add("required_files", not missing, "all present" if not missing else f"missing: {', '.join(missing)}")

    asyncio_spec = importlib.util.find_spec("asyncio")
    asyncio_origin = str(asyncio_spec.origin) if asyncio_spec and asyncio_spec.origin else "unknown"
    asyncio_shadowed = "site-packages" in asyncio_origin.lower()
    add("asyncio", not asyncio_shadowed, f"stdlib origin: {asyncio_origin}" if not asyncio_shadowed else f"WARNING: asyncio resolves from site-packages: {asyncio_origin}; uninstall the PyPI asyncio package", severity="warning" if asyncio_shadowed else "info")

    try:
        _, _, normalized_endpoint = parse_managed_endpoint(endpoint)
        add("endpoint", True, normalized_endpoint, severity="info")
    except ValueError as exc:
        add("endpoint", False, str(exc))
        normalized_endpoint = endpoint.rstrip("/")

    git_dir = (ROOT / ".git").exists()
    add("git_repository", git_dir, str(ROOT))
    if git_dir:
        branch = git_value("branch", "--show-current")
        head = git_value("rev-parse", "HEAD")
        upstream = git_value("rev-parse", "@{u}")
        dirty = git_value("status", "--porcelain")
        add("git_branch", branch == "main", branch or "unknown")
        if head and upstream:
            add("git_sync", head == upstream, f"HEAD={head[:12]} upstream={upstream[:12]}", severity="warning")
        add("git_worktree", dirty == "", "clean" if dirty == "" else "local changes present", severity="warning")

    try:
        health = service_health(normalized_endpoint)
        add("service", True, f"ready ({health.get('mode', 'unknown')}) at {normalized_endpoint}", severity="info")
    except RuntimeError as exc:
        add("service", False, str(exc), severity="warning")

    hard_failures = [check for check in checks if not check["ok"] and check["severity"] == "error"]
    payload = {"ok": not hard_failures, "status": "ready_to_operate" if not hard_failures else "needs_attention", "root": str(ROOT), "timestamp": now_iso(), "checks": checks}
    if json_output:
        print(json.dumps(payload, indent=2))
    else:
        print("EVAVO operations doctor")
        print("=" * 72)
        for check in checks:
            marker = "OK" if check["ok"] else ("WARN" if check["severity"] == "warning" else "FAIL")
            print(f"[{marker:<4}] {check['name']:<16} {check['detail']}")
        print("=" * 72)
        print(payload["status"])
    return 0 if not hard_failures else 2


def sync_main() -> int:
    try:
        branch = git_value("branch", "--show-current")
        if branch != "main":
            print(f"ERROR: bootstrap requires branch main; current branch is {branch or 'unknown'}.", file=sys.stderr)
            return 2
        dirty = git_value("status", "--porcelain")
        if dirty:
            print("ERROR: local changes are present; refusing to overwrite them during bootstrap.", file=sys.stderr)
            print(dirty, file=sys.stderr)
            return 2
        result = run_git("pull", "--ff-only", "origin", "main", timeout=120)
    except FileNotFoundError:
        print("ERROR: git is not installed or not on PATH.", file=sys.stderr)
        return 2
    except subprocess.TimeoutExpired:
        print("ERROR: git pull timed out.", file=sys.stderr)
        return 3
    if result.returncode != 0:
        print(f"ERROR: git pull failed:\n{(result.stderr or result.stdout).strip()}", file=sys.stderr)
        return result.returncode or 1
    print((result.stdout or "Already up to date.").strip())
    return 0


def bootstrap(endpoint: str, skip_pull: bool = False) -> int:
    if not skip_pull:
        code = sync_main()
        if code != 0:
            return code
    controller = str(ROOT / "evavo.py")
    steps = [
        [sys.executable, controller, "doctor", "--endpoint", endpoint],
        [sys.executable, controller, "test"],
        [sys.executable, controller, "start", "--endpoint", endpoint],
        [sys.executable, controller, "status", "--endpoint", endpoint],
    ]
    for command in steps:
        print(f"\n>>> {' '.join(command)}")
        result = subprocess.run(command, cwd=str(ROOT))
        if result.returncode != 0:
            print(f"ERROR: bootstrap stopped because exit code was {result.returncode}.", file=sys.stderr)
            return result.returncode
    print("\nEVAVO bootstrap completed successfully.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="EVAVO local image generator operations controller")
    subparsers = parser.add_subparsers(dest="command", required=True)
    start = subparsers.add_parser("start", help="Use an existing native ComfyUI or start the managed mock fallback")
    start.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    start.add_argument("--wait", type=float, default=20.0, help="Readiness timeout in seconds")
    subparsers.add_parser("stop", help="Stop only the managed mock service")
    status = subparsers.add_parser("status", help="Check the generation backend")
    status.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    doctor_parser = subparsers.add_parser("doctor", help="Diagnose Python, files, Git state and generation backend")
    doctor_parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    doctor_parser.add_argument("--json", action="store_true")
    bootstrap_parser = subparsers.add_parser("bootstrap", help="Sync main, test, start and verify EVAVO")
    bootstrap_parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    bootstrap_parser.add_argument("--skip-pull", action="store_true", help="Do not git pull before validation")
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
    subparsers.add_parser("test", help="Run operational integration tests")
    subparsers.add_parser("sync", help="Fast-forward the local checkout to origin/main")

    args = parser.parse_args()
    if args.command == "start":
        if args.wait <= 0:
            parser.error("--wait must be greater than zero")
        return start_service(args.endpoint, args.wait)
    if args.command == "stop":
        return stop_service()
    if args.command == "status":
        return status_service(args.endpoint.rstrip("/"))
    if args.command == "doctor":
        return doctor(args.endpoint, args.json)
    if args.command == "bootstrap":
        return bootstrap(args.endpoint, args.skip_pull)
    if args.command == "sync":
        return sync_main()
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
        return run_passthrough("task-tracker.py", ["stats"] + (["--json"] if args.json else []))
    if args.command == "test":
        return run_passthrough("test-operations.py", [])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
