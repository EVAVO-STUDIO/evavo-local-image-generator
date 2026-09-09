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
from evavo_local_image_generator.comfyui_runtime import (
    _stop_managed_mock as stop_managed_mock,
    discover_comfyui,
    ensure_comfyui,
    load_state as load_native_state,
    native_health,
    stop_managed_comfyui,
)

STATE_DIR = ROOT / ".evavo"
STATE_FILE = STATE_DIR / "operations-service.json"
LOG_FILE = STATE_DIR / "mock-service.log"
SERVER = ROOT / "mock-comfyui-server.py"
REQUIRED_FILES = [
    "evavo.py",
    "verify-evavo.py",
    "safe_main_git.py",
    "evavo_operations.py",
    "evavo-wrapper.py",
    "mock-comfyui-server.py",
    "generate-batch.py",
    "monitor-evavo.py",
    "task-tracker.py",
    "test-operations.py",
    "agent-doctor.py",
    "test-agent-integration.py",
    "test-provisioning.py",
    "test-backend-automation.py",
    "test-batch-workflow-preflight.py",
    "test-agent-doctor-workflows.py",
    "test-chatgpt-tunnel.py",
    "test-gateway.py",
    "test-git-safety.py",
    "test-legacy-compatibility.py",
    "legacy_image_cli.py",
    "provision-comfyui.py",
    "EVAVO-GATEWAY.py",
    "EVAVO-SERVICE-MANAGER.py",
    "gateway-smoke-test.py",
    "UPDATE-AND-VERIFY-EVAVO.ps1",
    "INSTALL-CLAUDE-MCP.ps1",
    "START-AGENT-MCP.ps1",
    "INSTALL-AGENT-MCP-AUTOSTART.ps1",
    "INSTALL-CHATGPT-MCP-TUNNEL.ps1",
    "SAVE-CHATGPT-TUNNEL-KEY.ps1",
    "START-CHATGPT-MCP-TUNNEL.ps1",
    "INSTALL-CHATGPT-MCP-TUNNEL-AUTOSTART.ps1",
    "CHATGPT-TUNNEL-DOCTOR.ps1",
    "START-GATEWAY.ps1",
    "COMMIT-UPGRADE.ps1",
    "COMMIT_AND_PUSH.ps1",
    "PUSH-UPGRADE-TO-MAIN.ps1",
    "COMPLETE_EVAVO_GIT_COMMIT.ps1",
    "create_github_repo.ps1",
    "CHATGPT-TUNNEL.md",
    "README.md",
    "CLAUDE.md",
    "evavo_local_image_generator/backends/comfyui_backend.py",
    "evavo_local_image_generator/comfyui_runtime.py",
    "evavo_local_image_generator/mcp_server.py",
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
    parsed = urllib.parse.urlparse(endpoint.rstrip("/"))
    if parsed.scheme != "http" or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("managed endpoint must be a plain loopback HTTP URL")
    if parsed.path not in {"", "/"}:
        raise ValueError("managed endpoint must not contain a path")
    host = parsed.hostname
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("managed service is restricted to 127.0.0.1/localhost")
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
    except OSError:
        pass


def terminate_pid(pid: int) -> None:
    """Terminate a PID that was just created by this process (startup rollback only)."""
    if pid <= 0:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True, timeout=10)
    else:
        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


def _start_mock(endpoint: str, wait_seconds: float) -> int:
    bind_host, port, endpoint = parse_managed_endpoint(endpoint)
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
        process = subprocess.Popen([sys.executable, str(SERVER), "--host", bind_host, "--port", str(port)], **kwargs)
    finally:
        log_handle.close()
    save_state(process.pid, endpoint)

    deadline = time.monotonic() + wait_seconds
    last_error = "mock service not ready"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            last_error = f"server exited with code {process.returncode}"
            break
        try:
            health = service_health(endpoint)
            print(json.dumps({"ok": True, "status": "started_mock", "pid": process.pid, "endpoint": endpoint, "log_file": str(LOG_FILE), "health": health}, indent=2))
            return 0
        except RuntimeError as exc:
            last_error = str(exc)
            time.sleep(0.25)

    if process.poll() is None:
        terminate_pid(process.pid)
    clear_state()
    print(f"ERROR: EVAVO mock failed to become ready: {last_error}", file=sys.stderr)
    return 3


def start_service(endpoint: str, wait_seconds: float = 90.0, allow_mock: bool = True) -> int:
    try:
        _, _, endpoint = parse_managed_endpoint(endpoint)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    current_native = native_health(endpoint)
    if current_native:
        try:
            result = ensure_comfyui(endpoint, wait_seconds=wait_seconds, allow_start=True)
        except RuntimeError as exc:
            print(f"ERROR: native ComfyUI is present but its managed configuration could not be reconciled: {exc}", file=sys.stderr)
            return 3
        print(json.dumps({"ok": True, **result}, indent=2))
        return 0

    try:
        result = ensure_comfyui(endpoint, wait_seconds=wait_seconds, allow_start=True)
        print(json.dumps({"ok": True, **result}, indent=2))
        return 0
    except RuntimeError as exc:
        native_error = str(exc)

    try:
        existing = service_health(endpoint)
        if existing.get("mode") == "mock" and allow_mock:
            print(json.dumps({"ok": True, "status": "already_running_mock", "endpoint": endpoint, "health": existing}, indent=2))
            return 0
    except RuntimeError:
        pass

    if not allow_mock:
        print(f"ERROR: native ComfyUI could not be started: {native_error}", file=sys.stderr)
        return 3
    print(f"Native ComfyUI unavailable ({native_error}); starting deterministic mock fallback.", file=sys.stderr)
    return _start_mock(endpoint, min(wait_seconds, 30.0))


def stop_service() -> int:
    native_result = stop_managed_comfyui()
    mock_state = load_state()
    mock_pid = mock_state.get("pid")
    mock_result: Dict[str, Any] = {"status": "not_managed", "stopped": False}
    if isinstance(mock_pid, int) and mock_pid > 0:
        if stop_managed_mock():
            mock_result = {"status": "stopped", "stopped": True, "pid": mock_pid}
        else:
            clear_state()
            mock_result = {"status": "stale_or_identity_mismatch", "stopped": False, "pid": mock_pid}
    print(json.dumps({"ok": True, "status": "stopped", "components": {"native": native_result, "mock": mock_result}}, indent=2))
    return 0


def status_service(endpoint: str) -> int:
    endpoint = endpoint.rstrip("/")
    try:
        health = service_health(endpoint)
        print(json.dumps({"ok": True, "status": "operational", "endpoint": endpoint, "health": health, "managed_mock": load_state(), "managed_native": load_native_state()}, indent=2))
        return 0
    except RuntimeError as exc:
        print(json.dumps({"ok": False, "status": "offline", "endpoint": endpoint, "error": str(exc), "managed_mock": load_state(), "managed_native": load_native_state()}, indent=2))
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

    installs = discover_comfyui()
    add("comfyui_install", bool(installs), "; ".join(str(item.root) for item in installs) if installs else "not found in standard paths; set EVAVO_COMFYUI_HOME", severity="warning")

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
        if health.get("mode") == "native-comfyui":
            try:
                inventory = ComfyUIBackend(normalized_endpoint).model_inventory(20)
                categories = inventory.get("categories", {})
                populated = []
                if isinstance(categories, dict):
                    populated = [f"{name}={entry.get('count', 0)}" for name, entry in categories.items() if isinstance(entry, dict) and entry.get("available")]
                add("model_inventory", True, ", ".join(populated) if populated else "no loader inventories reported", severity="info")
            except RuntimeError as exc:
                add("model_inventory", False, str(exc), severity="warning")
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


def bootstrap(endpoint: str, skip_pull: bool = False, skip_verify: bool = False) -> int:
    if not skip_pull:
        code = sync_main()
        if code != 0:
            return code
    controller = str(ROOT / "evavo.py")
    steps: List[List[str]] = [[sys.executable, controller, "doctor", "--endpoint", endpoint]]
    if not skip_verify:
        verify_command = [sys.executable, controller, "verify", "--full"]
        if os.name == "nt":
            verify_command.append("--require-powershell")
        steps.append(verify_command)
    steps.extend([
        [sys.executable, controller, "start", "--endpoint", endpoint, "--no-mock"],
        [sys.executable, controller, "status", "--endpoint", endpoint],
    ])
    for command in steps:
        print(f"\n>>> {' '.join(command)}")
        result = subprocess.run(command, cwd=str(ROOT))
        if result.returncode != 0:
            print(f"ERROR: bootstrap stopped because exit code was {result.returncode}.", file=sys.stderr)
            return result.returncode
    print("\nEVAVO bootstrap completed successfully with a native renderer.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="EVAVO local image generator operations controller")
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="Use/start native ComfyUI; optionally fall back to the test mock")
    start.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    start.add_argument("--wait", type=float, default=90.0, help="Native ComfyUI readiness timeout")
    start.add_argument("--no-mock", action="store_true", help="Fail instead of starting the deterministic mock fallback")

    subparsers.add_parser("stop", help="Stop only identity-verified EVAVO-managed native/mock processes")

    status = subparsers.add_parser("status", help="Check the generation backend")
    status.add_argument("--endpoint", default=DEFAULT_ENDPOINT)

    doctor_parser = subparsers.add_parser("doctor", help="Diagnose Python, files, Git, ComfyUI install/backend and model inventory")
    doctor_parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    doctor_parser.add_argument("--json", action="store_true")

    verify_parser = subparsers.add_parser("verify", help="Run read-only structural/Python/PowerShell contract verification")
    verify_parser.add_argument("--full", action="store_true", help="Also run all Python safety/integration suites")
    verify_parser.add_argument("--require-powershell", action="store_true", help="Fail if PowerShell is unavailable")
    verify_parser.add_argument("--json", action="store_true")

    bootstrap_parser = subparsers.add_parser("bootstrap", help="Sync main, fully verify, require native ComfyUI, and verify backend health")
    bootstrap_parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    bootstrap_parser.add_argument("--skip-pull", action="store_true")
    bootstrap_parser.add_argument("--skip-verify", action="store_true", help="Skip full verifier only when it already passed in the caller")

    generate = subparsers.add_parser("generate", help="Generate image prompts through the active backend")
    generate.add_argument("--prompts", nargs="+")
    generate.add_argument("--examples", action="store_true")
    generate.add_argument("--project", default="batch_gen")
    generate.add_argument("--concurrency", type=int, default=4)
    generate.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    generate.add_argument("--wait", action="store_true")
    generate.add_argument("--wait-timeout", type=float, default=600.0)
    generate.add_argument("--output-dir")
    generate.add_argument("--workflow")
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
        return start_service(args.endpoint, args.wait, allow_mock=not args.no_mock)
    if args.command == "stop":
        return stop_service()
    if args.command == "status":
        return status_service(args.endpoint.rstrip("/"))
    if args.command == "doctor":
        return doctor(args.endpoint, args.json)
    if args.command == "verify":
        forwarded: List[str] = []
        if args.full:
            forwarded.append("--full")
        if args.require_powershell:
            forwarded.append("--require-powershell")
        if args.json:
            forwarded.append("--json")
        return run_passthrough("verify-evavo.py", forwarded)
    if args.command == "bootstrap":
        return bootstrap(args.endpoint, args.skip_pull, args.skip_verify)
    if args.command == "sync":
        return sync_main()
    if args.command == "generate":
        forwarded = ["--project", args.project, "--concurrency", str(args.concurrency), "--endpoint", args.endpoint]
        if args.prompts:
            forwarded.extend(["--prompts", *args.prompts])
        elif args.examples:
            forwarded.append("--examples")
        else:
            parser.error("generate requires --prompts or --examples")
        if args.wait:
            forwarded.extend(["--wait", "--wait-timeout", str(args.wait_timeout)])
        if args.output_dir:
            forwarded.extend(["--output-dir", args.output_dir])
        if args.workflow:
            forwarded.extend(["--workflow", args.workflow])
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
