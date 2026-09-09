#!/usr/bin/env python3
"""Manage the optional EVAVO HTTP compatibility gateway.

The manager shares the canonical native-ComfyUI lifecycle used by CLI/MCP.
It never starts the deterministic mock as a production renderer and only stops
processes whose identity proves EVAVO owns them.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from evavo_local_image_generator.comfyui_runtime import ensure_comfyui, native_health, stop_managed_comfyui

ROOT = Path(__file__).resolve().parent
STATE_DIR = Path(os.getenv("EVAVO_GATEWAY_STATE_DIR", str(ROOT / ".evavo" / "gateway"))).expanduser().resolve()
STATE_FILE = STATE_DIR / "service-manager.json"
LOG_DIR = STATE_DIR / "logs"
GATEWAY_SCRIPT = ROOT / "EVAVO-GATEWAY.py"
GATEWAY_HOST = os.getenv("EVAVO_GATEWAY_HOST", "127.0.0.1")
GATEWAY_PORT = int(os.getenv("EVAVO_GATEWAY_PORT", "8000"))
COMFYUI_URL = (os.getenv("COMFYUI_ENDPOINT") or os.getenv("EVAVO_COMFYUI_ENDPOINT") or "http://127.0.0.1:8188").rstrip("/")
GATEWAY_URL = f"http://{GATEWAY_HOST}:{GATEWAY_PORT}"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def http_json(url: str, timeout: float = 2.0) -> Optional[Dict[str, Any]]:
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "EVAVO-Gateway-Manager/2"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except (OSError, TimeoutError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def port_open(host: str, port: int, timeout: float = 0.35) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def gateway_health() -> Dict[str, Any]:
    started = time.perf_counter()
    payload = http_json(f"{GATEWAY_URL}/health")
    latency = round((time.perf_counter() - started) * 1000, 1)
    gateway_alive = isinstance(payload, dict) and payload.get("gateway") == "ok"
    healthy = payload == {"status": "healthy", "gateway": "ok", "comfyui": "ok"}
    return {"healthy": healthy, "gateway_alive": gateway_alive, "latency_ms": latency, "response": payload}


def comfyui_health() -> Dict[str, Any]:
    started = time.perf_counter()
    health = native_health(COMFYUI_URL)
    return {
        "healthy": bool(health),
        "mode": "native-comfyui" if health else "offline_or_not_native",
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        "response": health,
    }


def full_health() -> Dict[str, Any]:
    comfy = comfyui_health()
    gateway = gateway_health()
    return {
        "status": "healthy" if comfy["healthy"] and gateway["healthy"] else "degraded",
        "timestamp": now_iso(),
        "gateway": gateway,
        "comfyui": comfy,
    }


def load_state() -> Dict[str, Any]:
    if not STATE_FILE.is_file():
        return {}
    try:
        payload = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def save_state(state: Dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=STATE_FILE.name + ".", suffix=".tmp", dir=str(STATE_DIR))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(state, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, STATE_FILE)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def command_line(pid: int) -> Optional[str]:
    if pid <= 0:
        return None
    if os.name == "nt":
        powershell = shutil.which("powershell.exe") or shutil.which("pwsh.exe") or shutil.which("powershell") or shutil.which("pwsh")
        if not powershell:
            return None
        script = f"$p=Get-CimInstance Win32_Process -Filter 'ProcessId = {pid}' -ErrorAction SilentlyContinue; if ($p) {{ $p.CommandLine }}"
        try:
            result = subprocess.run([powershell, "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, text=True, timeout=8)
        except (OSError, subprocess.TimeoutExpired):
            return None
        return result.stdout.strip() or None
    proc = Path(f"/proc/{pid}/cmdline")
    if proc.is_file():
        try:
            return proc.read_bytes().replace(b"\x00", b" ").decode("utf-8", errors="replace").strip() or None
        except OSError:
            return None
    return None


def pid_matches(pid: int, expected: Path) -> bool:
    line = command_line(pid)
    if not line:
        return False
    normalized = line.replace("\\", "/").lower()
    target = str(expected.resolve()).replace("\\", "/").lower()
    return target in normalized


def terminate_pid(pid: int) -> None:
    if pid <= 0:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True, timeout=12)
    else:
        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            return


def spawn_gateway() -> subprocess.Popen[Any]:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handle = (LOG_DIR / "gateway.log").open("ab", buffering=0)
    env = os.environ.copy()
    env["EVAVO_GATEWAY_HOST"] = GATEWAY_HOST
    env["EVAVO_GATEWAY_PORT"] = str(GATEWAY_PORT)
    env["COMFYUI_ENDPOINT"] = COMFYUI_URL
    kwargs: Dict[str, Any] = {
        "cwd": str(ROOT),
        "stdin": subprocess.DEVNULL,
        "stdout": handle,
        "stderr": subprocess.STDOUT,
        "env": env,
    }
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            flags |= subprocess.CREATE_NO_WINDOW
        kwargs["creationflags"] = flags
    else:
        kwargs["start_new_session"] = True
    try:
        return subprocess.Popen([sys.executable, str(GATEWAY_SCRIPT)], **kwargs)
    finally:
        handle.close()


def wait_for(predicate, timeout: float, label: str) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.25)
    raise RuntimeError(f"{label} did not become ready within {timeout:g}s")


def ensure_comfyui_service() -> Dict[str, Any]:
    result = ensure_comfyui(
        COMFYUI_URL,
        wait_seconds=float(os.getenv("EVAVO_GATEWAY_COMFYUI_START_TIMEOUT", "120")),
        allow_start=True,
    )
    if not native_health(COMFYUI_URL):
        raise RuntimeError("Native ComfyUI did not become ready; mock backends are not accepted by the production gateway")
    return result


def ensure_gateway_service(state: Dict[str, Any]) -> Dict[str, Any]:
    existing = gateway_health()
    if existing["gateway_alive"]:
        return {"status": "already_running", "healthy": existing["healthy"]}
    if port_open(GATEWAY_HOST, GATEWAY_PORT):
        raise RuntimeError(f"Port {GATEWAY_PORT} is occupied by another process; refusing to replace it")
    if not GATEWAY_SCRIPT.is_file():
        raise RuntimeError(f"Gateway script not found: {GATEWAY_SCRIPT}")
    process = spawn_gateway()
    state["gateway"] = {"managed": True, "pid": process.pid, "started_at": now_iso()}
    save_state(state)
    try:
        wait_for(lambda: gateway_health()["gateway_alive"], 20.0, "EVAVO Gateway")
    except Exception:
        if process.poll() is None and pid_matches(process.pid, GATEWAY_SCRIPT):
            terminate_pid(process.pid)
        raise
    return {"status": "started", "pid": process.pid, "healthy": gateway_health()["healthy"]}


def start_services() -> Dict[str, Any]:
    if GATEWAY_HOST not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("Gateway manager is restricted to loopback")
    if not 1 <= GATEWAY_PORT <= 65535:
        raise RuntimeError("Gateway port must be between 1 and 65535")
    state = load_state()
    comfy = ensure_comfyui_service()
    gateway = ensure_gateway_service(state)
    state["last_start"] = now_iso()
    state["comfyui_endpoint"] = COMFYUI_URL
    save_state(state)
    health = full_health()
    if health["status"] != "healthy":
        raise RuntimeError(f"Gateway stack started but is not healthy: {health}")
    return {"ok": True, "comfyui": comfy, "gateway": gateway, "health": health}


def stop_services() -> Dict[str, Any]:
    state = load_state()
    stopped: Dict[str, Any] = {"gateway": False, "comfyui": False}
    gateway = state.get("gateway") if isinstance(state.get("gateway"), dict) else {}
    pid = gateway.get("pid")
    if gateway.get("managed") and isinstance(pid, int) and pid_matches(pid, GATEWAY_SCRIPT):
        terminate_pid(pid)
        stopped["gateway"] = True
    native = stop_managed_comfyui()
    stopped["comfyui"] = bool(native.get("stopped"))
    try:
        STATE_FILE.unlink()
    except OSError:
        pass
    return {"ok": True, "stopped": stopped, "native": native, "timestamp": now_iso()}


def monitor(interval: float) -> int:
    start_services()
    try:
        while True:
            health = full_health()
            print(json.dumps(health, ensure_ascii=False), flush=True)
            if not health["comfyui"]["healthy"]:
                ensure_comfyui_service()
            if not health["gateway"]["gateway_alive"]:
                ensure_gateway_service(load_state())
            time.sleep(interval)
    except KeyboardInterrupt:
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage the EVAVO native-image HTTP gateway")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("start", help="Start/ensure native ComfyUI and the loopback gateway")
    subparsers.add_parser("stop", help="Stop only identity-verified EVAVO-managed components")
    subparsers.add_parser("health", help="Print health JSON")
    subparsers.add_parser("status", help="Alias for health")
    monitor_parser = subparsers.add_parser("monitor", help="Monitor and restore native ComfyUI/gateway health")
    monitor_parser.add_argument("--interval", type=float, default=5.0)
    args = parser.parse_args()

    try:
        if args.command == "start":
            print(json.dumps(start_services(), ensure_ascii=False, indent=2))
            return 0
        if args.command == "stop":
            print(json.dumps(stop_services(), ensure_ascii=False, indent=2))
            return 0
        if args.command in {"health", "status"}:
            result = full_health()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["status"] == "healthy" else 3
        if args.command == "monitor":
            if args.interval < 1.0:
                parser.error("--interval must be at least 1 second")
            return monitor(args.interval)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc), "timestamp": now_iso()}, ensure_ascii=False), file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
