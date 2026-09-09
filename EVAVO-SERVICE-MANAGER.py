#!/usr/bin/env python3
"""EVAVO gateway service manager for Windows/Linux local workstations.

Starts and monitors the fixed Gateway (8000) and ComfyUI (8188) contract.
Only processes started by EVAVO are stopped automatically.
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
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "evavo-state"
STATE_FILE = STATE_DIR / "service-manager.json"
LOG_DIR = STATE_DIR / "logs"
GATEWAY_SCRIPT = ROOT / "EVAVO-GATEWAY.py"
MOCK_SCRIPT = ROOT / "mock-comfyui-server.py"
GATEWAY_HOST = "127.0.0.1"
GATEWAY_PORT = 8000
COMFYUI_HOST = "127.0.0.1"
COMFYUI_PORT = 8188
GATEWAY_URL = f"http://{GATEWAY_HOST}:{GATEWAY_PORT}"
COMFYUI_URL = f"http://{COMFYUI_HOST}:{COMFYUI_PORT}"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def truthy(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def http_json(url: str, timeout: float = 2.0) -> Optional[Dict[str, Any]]:
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "EVAVO-Service-Manager/1"})
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
    healthy = payload == {"status": "healthy", "gateway": "ok", "comfyui": "ok"}
    gateway_alive = isinstance(payload, dict) and payload.get("gateway") == "ok"
    return {"healthy": healthy, "gateway_alive": gateway_alive, "latency_ms": latency, "response": payload}


def comfyui_health() -> Dict[str, Any]:
    started = time.perf_counter()
    # EVAVO's deterministic simulator intentionally also implements /system_stats,
    # so check its identity route first to avoid misreporting a mock as native.
    system = http_json(f"{COMFYUI_URL}/system")
    if isinstance(system, dict) and system.get("service") == "evavo-local-image-generator":
        healthy = system.get("status") in {"ready", "ok"}
        return {
            "healthy": healthy,
            "mode": str(system.get("mode", "mock")),
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "response": system,
        }
    stats = http_json(f"{COMFYUI_URL}/system_stats")
    if isinstance(stats, dict) and isinstance(stats.get("system"), dict):
        return {
            "healthy": True,
            "mode": "native-comfyui",
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "response": stats,
        }
    return {
        "healthy": False,
        "mode": "offline",
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        "response": None,
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
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


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


def process_kwargs(log_path: Path) -> tuple[Dict[str, Any], Any]:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handle = log_path.open("ab", buffering=0)
    kwargs: Dict[str, Any] = {
        "cwd": str(ROOT),
        "stdin": subprocess.DEVNULL,
        "stdout": handle,
        "stderr": subprocess.STDOUT,
    }
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            flags |= subprocess.CREATE_NO_WINDOW
        kwargs["creationflags"] = flags
    else:
        kwargs["start_new_session"] = True
    return kwargs, handle


def spawn(command: list[str], log_name: str) -> subprocess.Popen[Any]:
    kwargs, handle = process_kwargs(LOG_DIR / log_name)
    try:
        return subprocess.Popen(command, **kwargs)
    finally:
        handle.close()


def wait_for(predicate, timeout: float, label: str) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.25)
    raise RuntimeError(f"{label} did not become ready within {timeout:g}s")


def ensure_comfyui_service(state: Dict[str, Any]) -> Dict[str, Any]:
    health = comfyui_health()
    if health["healthy"]:
        return {"status": "already_running", "mode": health["mode"]}

    # Prefer a real installed ComfyUI through the repository's hardened runtime.
    try:
        from evavo_local_image_generator.comfyui_runtime import ensure_comfyui

        result = ensure_comfyui(COMFYUI_URL, wait_seconds=float(os.getenv("EVAVO_GATEWAY_COMFYUI_START_TIMEOUT", "90")), allow_start=True)
        state["comfyui"] = {
            "kind": "native",
            "managed": bool(result.get("started")),
            "pid": result.get("pid"),
            "started_at": now_iso(),
        }
        save_state(state)
        return result
    except Exception as native_error:
        if not truthy("EVAVO_GATEWAY_ALLOW_MOCK_COMFYUI", default=True):
            raise RuntimeError(f"Native ComfyUI is unavailable and mock fallback is disabled: {native_error}") from native_error

    if not MOCK_SCRIPT.is_file():
        raise RuntimeError(f"Mock ComfyUI fallback not found: {MOCK_SCRIPT}")
    if port_open(COMFYUI_HOST, COMFYUI_PORT):
        raise RuntimeError("Port 8188 is occupied by an unknown/unhealthy process; refusing to replace it")
    process = spawn([sys.executable, str(MOCK_SCRIPT), "--host", COMFYUI_HOST, "--port", str(COMFYUI_PORT)], "comfyui-mock.log")
    state["comfyui"] = {"kind": "mock", "managed": True, "pid": process.pid, "started_at": now_iso()}
    save_state(state)
    try:
        wait_for(lambda: bool(comfyui_health()["healthy"]), 15.0, "ComfyUI mock")
    except Exception:
        if process.poll() is None:
            terminate_pid(process.pid)
        raise
    return {"status": "started", "mode": "mock", "pid": process.pid}


def ensure_gateway_service(state: Dict[str, Any]) -> Dict[str, Any]:
    existing = gateway_health()
    if existing["gateway_alive"]:
        return {"status": "already_running", "healthy": existing["healthy"]}
    if port_open(GATEWAY_HOST, GATEWAY_PORT):
        raise RuntimeError(
            "Port 8000 is occupied by another process. Gateway must remain on 8000; "
            "move Kokoro or any other service to a different port (recommended Kokoro: 8880)."
        )
    if not GATEWAY_SCRIPT.is_file():
        raise RuntimeError(f"Gateway script not found: {GATEWAY_SCRIPT}")
    process = spawn([sys.executable, str(GATEWAY_SCRIPT)], "gateway.log")
    state["gateway"] = {"kind": "gateway", "managed": True, "pid": process.pid, "started_at": now_iso()}
    save_state(state)
    try:
        wait_for(lambda: bool(gateway_health()["gateway_alive"]), 20.0, "EVAVO Gateway")
    except Exception:
        if process.poll() is None:
            terminate_pid(process.pid)
        raise
    return {"status": "started", "pid": process.pid, "healthy": gateway_health()["healthy"]}


def start_services() -> Dict[str, Any]:
    state = load_state()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    comfy = ensure_comfyui_service(state)
    gateway = ensure_gateway_service(state)
    state["last_start"] = now_iso()
    save_state(state)
    return {"ok": True, "comfyui": comfy, "gateway": gateway, "health": full_health()}


def stop_services() -> Dict[str, Any]:
    state = load_state()
    stopped: Dict[str, Any] = {"gateway": False, "comfyui": False}

    gateway = state.get("gateway") if isinstance(state.get("gateway"), dict) else {}
    gateway_pid = gateway.get("pid")
    if gateway.get("managed") and isinstance(gateway_pid, int) and pid_matches(gateway_pid, GATEWAY_SCRIPT):
        terminate_pid(gateway_pid)
        stopped["gateway"] = True

    comfy = state.get("comfyui") if isinstance(state.get("comfyui"), dict) else {}
    if comfy.get("managed"):
        if comfy.get("kind") == "mock":
            pid = comfy.get("pid")
            if isinstance(pid, int) and pid_matches(pid, MOCK_SCRIPT):
                terminate_pid(pid)
                stopped["comfyui"] = True
        elif comfy.get("kind") == "native":
            try:
                from evavo_local_image_generator.comfyui_runtime import stop_managed_comfyui

                stopped["comfyui"] = bool(stop_managed_comfyui().get("stopped"))
            except Exception:
                stopped["comfyui"] = False

    try:
        STATE_FILE.unlink()
    except OSError:
        pass
    return {"ok": True, "stopped": stopped, "timestamp": now_iso()}


def monitor(interval: float) -> int:
    start_services()
    try:
        while True:
            health = full_health()
            print(json.dumps(health, ensure_ascii=False), flush=True)
            if not health["comfyui"]["healthy"] or not health["gateway"]["gateway_alive"]:
                try:
                    start_services()
                except Exception as exc:
                    print(json.dumps({"status": "restart_failed", "error": str(exc), "timestamp": now_iso()}), file=sys.stderr, flush=True)
            time.sleep(interval)
    except KeyboardInterrupt:
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage EVAVO Unified Gateway services")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("start", help="Start required services")
    subparsers.add_parser("stop", help="Stop EVAVO-managed services")
    subparsers.add_parser("health", help="Print health JSON")
    subparsers.add_parser("status", help="Alias for health")
    monitor_parser = subparsers.add_parser("monitor", help="Start services and continuously monitor/restart EVAVO-managed components")
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
