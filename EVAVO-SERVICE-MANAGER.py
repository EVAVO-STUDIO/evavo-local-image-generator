#!/usr/bin/env python3
"""Manage the EVAVO loopback HTTP gateway and first-party local providers.

Native ComfyUI remains the required image renderer. Audio Studio is configured as a
bounded CLI provider when its sibling checkout is available. 3D Studio's separately
enabled token-gated execution worker is optionally managed on loopback. The manager
never starts deterministic mocks and stops only processes whose command identity
proves EVAVO owns them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from evavo_local_image_generator.comfyui_runtime import ensure_comfyui, native_health, stop_managed_comfyui

ROOT = Path(__file__).resolve().parent
STATE_DIR = Path(os.getenv("EVAVO_GATEWAY_STATE_DIR", str(ROOT / ".evavo" / "gateway"))).expanduser().resolve()
STATE_FILE = STATE_DIR / "service-manager.json"
TOKEN_FILE = STATE_DIR / "3d-worker.token"
LOG_DIR = STATE_DIR / "logs"
GATEWAY_SCRIPT = ROOT / "EVAVO-GATEWAY.py"
GATEWAY_HOST = os.getenv("EVAVO_GATEWAY_HOST", "127.0.0.1")
GATEWAY_PORT = int(os.getenv("EVAVO_GATEWAY_PORT", "8000"))
COMFYUI_URL = (os.getenv("COMFYUI_ENDPOINT") or os.getenv("EVAVO_COMFYUI_ENDPOINT") or "http://127.0.0.1:8188").rstrip("/")
GATEWAY_URL = f"http://{GATEWAY_HOST}:{GATEWAY_PORT}"
THREE_D_URL = os.getenv("EVAVO_3D_ENDPOINT", "http://127.0.0.1:4314").rstrip("/")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def env_true(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def http_json(url: str, timeout: float = 2.0) -> Optional[Dict[str, Any]]:
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "EVAVO-Gateway-Manager/4"})
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


def endpoint_host_port(url: str, *, expected_default_port: int) -> tuple[str, int]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "http" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise RuntimeError(f"Unsupported local provider endpoint: {url}")
    host = parsed.hostname
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError(f"Local provider endpoint must use loopback: {url}")
    if parsed.path not in {"", "/"}:
        raise RuntimeError(f"Local provider endpoint must not contain a path: {url}")
    try:
        port = parsed.port or expected_default_port
    except ValueError as exc:
        raise RuntimeError(f"Local provider endpoint contains an invalid port: {url}") from exc
    if not 1 <= port <= 65535:
        raise RuntimeError("Local provider port must be between 1 and 65535")
    return host, port


def gateway_health() -> Dict[str, Any]:
    started = time.perf_counter()
    payload = http_json(f"{GATEWAY_URL}/health")
    latency = round((time.perf_counter() - started) * 1000, 1)
    gateway_alive = isinstance(payload, dict) and payload.get("gateway") == "ok"
    healthy = payload == {"status": "healthy", "gateway": "ok", "comfyui": "ok"}
    return {"healthy": healthy, "gateway_alive": gateway_alive, "latency_ms": latency, "response": payload}


def gateway_services() -> Optional[Dict[str, Any]]:
    return http_json(f"{GATEWAY_URL}/services")


def comfyui_health() -> Dict[str, Any]:
    started = time.perf_counter()
    health = native_health(COMFYUI_URL)
    return {
        "healthy": bool(health),
        "mode": "native-comfyui" if health else "offline_or_not_native",
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        "response": health,
    }


def three_d_health() -> Dict[str, Any]:
    started = time.perf_counter()
    payload = http_json(f"{THREE_D_URL}/api/v1/health")
    healthy = (
        isinstance(payload, dict)
        and payload.get("ok") is True
        and payload.get("service") == "evavo-3d-agent-worker"
        and payload.get("executionEnabled") is True
    )
    return {
        "healthy": healthy,
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        "endpoint": THREE_D_URL,
        "response": payload,
    }


def three_d_token_ready(token: str) -> bool:
    """Prove a bearer token against a non-mutating first-party worker route."""
    if len(token) < 32 or "\r" in token or "\n" in token:
        return False
    request = urllib.request.Request(
        f"{THREE_D_URL}/api/v1/jobs/gateway-token-probe",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "EVAVO-Gateway-Manager/4",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=2.0) as response:
            return response.status == 200
    except urllib.error.HTTPError as exc:
        return exc.code in {404, 422}
    except (OSError, TimeoutError, urllib.error.URLError):
        return False


def audio_provider_status() -> Dict[str, Any]:
    raw = os.getenv("EVAVO_AUDIO_PROVIDER_ARGV", "").strip()
    if not raw:
        return {"configured": False, "backend": "evavo-audio-studio"}
    try:
        argv = json.loads(raw)
    except json.JSONDecodeError:
        return {"configured": False, "backend": "evavo-audio-studio", "error": "invalid argv JSON"}
    ready = isinstance(argv, list) and len(argv) >= 2 and all(isinstance(item, str) and item for item in argv)
    return {"configured": ready, "backend": "evavo-audio-studio", "argv0": argv[0] if ready else None}


def provider_configuration_fingerprint() -> str:
    """Hash effective provider settings without persisting bearer-token plaintext."""
    token = os.getenv("EVAVO_3D_AGENT_EXECUTION_TOKEN", "")
    values = {
        "audio_argv": os.getenv("EVAVO_AUDIO_PROVIDER_ARGV", ""),
        "audio_studio": os.getenv("EVAVO_AUDIO_STUDIO_DIR", ""),
        "video_argv": os.getenv("EVAVO_VIDEO_PROVIDER_ARGV", ""),
        "video_studio": os.getenv("EVAVO_VIDEO_STUDIO_DIR", ""),
        "wan_model": os.getenv("EVAVO_WAN21_MODEL_DIR", ""),
        "wan_manifest_sha256": os.getenv("EVAVO_WAN21_MODEL_MANIFEST_SHA256", ""),
        "3d_endpoint": THREE_D_URL,
        "3d_workspace": os.getenv("EVAVO_3D_AGENT_WORKSPACE_ROOT", ""),
        "3d_token_sha256": hashlib.sha256(token.encode("utf-8")).hexdigest() if token else "",
        "3d_manage": os.getenv("EVAVO_GATEWAY_MANAGE_3D", "1"),
    }
    encoded = json.dumps(values, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _read_state_strict() -> Dict[str, Any]:
    """Read manager ownership state without treating corruption as 'no state'."""
    if not STATE_FILE.exists():
        return {}
    if STATE_FILE.is_symlink():
        raise RuntimeError(f"SERVICE_MANAGER_STATE_UNSAFE:{STATE_FILE}:state file must not be a symlink")
    try:
        payload = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"SERVICE_MANAGER_STATE_CORRUPT:{STATE_FILE}:{exc}") from exc
    except OSError as exc:
        raise RuntimeError(f"SERVICE_MANAGER_STATE_READ_ERROR:{STATE_FILE}:{exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"SERVICE_MANAGER_STATE_CORRUPT:{STATE_FILE}:root must be a JSON object")
    return payload


def load_state() -> Dict[str, Any]:
    """Read lifecycle-authority state; malformed state is a hard safety error."""
    return _read_state_strict()


def manager_state_health() -> Dict[str, Any]:
    """Read-only state diagnosis used by health/status without mutating anything."""
    if not STATE_FILE.exists():
        return {"healthy": True, "status": "missing", "path": str(STATE_FILE)}
    try:
        state = _read_state_strict()
    except RuntimeError as exc:
        message = str(exc)
        status = "unsafe" if message.startswith("SERVICE_MANAGER_STATE_UNSAFE:") else "corrupt"
        if message.startswith("SERVICE_MANAGER_STATE_READ_ERROR:"):
            status = "read_error"
        return {"healthy": False, "status": status, "path": str(STATE_FILE), "error": message}
    return {
        "healthy": True,
        "status": "ok",
        "path": str(STATE_FILE),
        "managed_gateway": bool(isinstance(state.get("gateway"), dict) and state["gateway"].get("managed")),
        "managed_3d_worker": bool(isinstance(state.get("3d_worker"), dict) and state["3d_worker"].get("managed")),
    }


def full_health() -> Dict[str, Any]:
    comfy = comfyui_health()
    gateway = gateway_health()
    providers = gateway_services() if gateway["gateway_alive"] else None
    manager_state = manager_state_health()
    core_ready = bool(comfy["healthy"] and gateway["healthy"])
    return {
        "status": "healthy" if core_ready and manager_state["healthy"] else "degraded",
        "core_ready": core_ready,
        "timestamp": now_iso(),
        "gateway": gateway,
        "comfyui": comfy,
        "providers": providers,
        "manager_state": manager_state,
        "audio_provider": audio_provider_status(),
        "3d_worker": three_d_health(),
    }


def save_state(state: Dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if STATE_FILE.is_symlink():
        raise RuntimeError(f"SERVICE_MANAGER_STATE_UNSAFE:{STATE_FILE}:state file must not be a symlink")
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


def pid_matches_tokens(pid: int, *tokens: str) -> bool:
    line = command_line(pid)
    if not line:
        return False
    normalized = line.replace("\\", "/").lower()
    return all(token.replace("\\", "/").lower() in normalized for token in tokens)


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


def detached_kwargs(*, cwd: Path, log_name: str, env: Dict[str, str]) -> tuple[Dict[str, Any], Any]:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handle = (LOG_DIR / log_name).open("ab", buffering=0)
    kwargs: Dict[str, Any] = {
        "cwd": str(cwd),
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
    return kwargs, handle


def spawn_gateway() -> subprocess.Popen[Any]:
    env = os.environ.copy()
    env["EVAVO_GATEWAY_HOST"] = GATEWAY_HOST
    env["EVAVO_GATEWAY_PORT"] = str(GATEWAY_PORT)
    env["COMFYUI_ENDPOINT"] = COMFYUI_URL
    env["EVAVO_COMFYUI_ENDPOINT"] = COMFYUI_URL
    kwargs, handle = detached_kwargs(cwd=ROOT, log_name="gateway.log", env=env)
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


def wait_for_port_close(host: str, port: int, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not port_open(host, port):
            return
        time.sleep(0.1)
    raise RuntimeError(f"port {port} did not close after managed gateway termination")


def _candidate_repos(env_name: str, names: tuple[str, ...]) -> list[Path]:
    values: list[Path] = []
    explicit = os.getenv(env_name, "").strip()
    if explicit:
        values.append(Path(explicit).expanduser())
    values.extend(ROOT.parent / name for name in names)
    return values


def discover_audio_repo() -> Optional[Path]:
    for candidate in _candidate_repos("EVAVO_AUDIO_STUDIO_DIR", ("evavo-audio-studio", "audio-studio")):
        worker = candidate / "worker_provider.py"
        if worker.is_file() and not worker.is_symlink():
            return candidate.resolve()
    return None


def repo_python(repo: Path, override_env: str) -> str:
    explicit = os.getenv(override_env, "").strip()
    if explicit:
        return explicit
    for candidate in (repo / ".venv" / "Scripts" / "python.exe", repo / ".venv" / "bin" / "python"):
        if candidate.is_file() and not candidate.is_symlink():
            return str(candidate.resolve())
    return sys.executable


def configure_audio_provider() -> Dict[str, Any]:
    if os.getenv("EVAVO_AUDIO_PROVIDER_ARGV", "").strip():
        return {"status": "explicit", **audio_provider_status()}
    repo = discover_audio_repo()
    if repo is None:
        return {"status": "not_found", "configured": False}
    worker = repo / "worker_provider.py"
    argv = [
        repo_python(repo, "EVAVO_AUDIO_PYTHON"),
        str(worker),
        "--request-json", "{request_json}",
        "--output-dir", "{output_dir}",
        "--task-id", "{task_id}",
    ]
    os.environ["EVAVO_AUDIO_PROVIDER_ARGV"] = json.dumps(argv, separators=(",", ":"))
    os.environ["EVAVO_AUDIO_STUDIO_DIR"] = str(repo)
    os.environ.setdefault("EVAVO_AUDIO_PROVIDER_TIMEOUT", "7200")
    return {"status": "configured", "configured": True, "repo": str(repo), "worker": str(worker)}


def discover_3d_repo() -> Optional[Path]:
    for candidate in _candidate_repos("EVAVO_3D_STUDIO_DIR", ("evavo-3d-studio", "3d-studio")):
        worker = candidate / "evavo_3d_studio" / "agent_worker.py"
        pyproject = candidate / "pyproject.toml"
        if worker.is_file() and pyproject.is_file() and not worker.is_symlink() and not pyproject.is_symlink():
            return candidate.resolve()
    return None


def _read_token_file() -> Optional[str]:
    try:
        if TOKEN_FILE.is_file() and not TOKEN_FILE.is_symlink():
            token = TOKEN_FILE.read_text(encoding="utf-8").strip()
            if len(token) >= 32 and "\r" not in token and "\n" not in token:
                return token
    except OSError:
        pass
    return None


def ensure_3d_token(*, allow_create: bool) -> tuple[Optional[str], str]:
    explicit = os.getenv("EVAVO_3D_AGENT_EXECUTION_TOKEN", "")
    if len(explicit) >= 32 and "\r" not in explicit and "\n" not in explicit:
        return explicit, "environment"
    stored = _read_token_file()
    if stored:
        os.environ["EVAVO_3D_AGENT_EXECUTION_TOKEN"] = stored
        return stored, "managed-state"
    if not allow_create:
        return None, "unavailable"
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(48)
    fd, temp_name = tempfile.mkstemp(prefix="3d-worker.token.", suffix=".tmp", dir=str(STATE_DIR))
    try:
        os.write(fd, (token + "\n").encode("utf-8"))
        os.fsync(fd)
        os.close(fd)
        fd = -1
        try:
            os.chmod(temp_name, 0o600)
        except OSError:
            pass
        os.replace(temp_name, TOKEN_FILE)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            Path(temp_name).unlink()
        except OSError:
            pass
    os.environ["EVAVO_3D_AGENT_EXECUTION_TOKEN"] = token
    return token, "generated-managed-state"


def three_d_workspace(repo: Path) -> Path:
    raw = os.getenv("EVAVO_3D_AGENT_WORKSPACE_ROOT", "").strip()
    selected = Path(raw).expanduser() if raw else ROOT.parent / "evavo-3d-work"
    resolved = selected.resolve(strict=False)
    repo_resolved = repo.resolve()
    if resolved == repo_resolved or repo_resolved in resolved.parents:
        raise RuntimeError("3D agent workspace must remain outside the 3D Studio source tree")
    resolved.mkdir(parents=True, exist_ok=True)
    os.environ["EVAVO_3D_AGENT_WORKSPACE_ROOT"] = str(resolved)
    return resolved


def spawn_3d_worker(repo: Path, workspace: Path, token: str) -> subprocess.Popen[Any]:
    host, port = endpoint_host_port(THREE_D_URL, expected_default_port=4314)
    if host == "localhost":
        host = "127.0.0.1"
    env = os.environ.copy()
    env["EVAVO_3D_AGENT_EXECUTION_ENABLED"] = "1"
    env["EVAVO_3D_AGENT_EXECUTION_TOKEN"] = token
    env["EVAVO_3D_AGENT_WORKSPACE_ROOT"] = str(workspace)
    env["EVAVO_3D_ENDPOINT"] = THREE_D_URL
    command = [
        repo_python(repo, "EVAVO_3D_PYTHON"),
        "-m", "evavo_3d_studio.agent_worker", "serve",
        "--host", host,
        "--port", str(port),
        "--workspace-root", str(workspace),
    ]
    kwargs, handle = detached_kwargs(cwd=repo, log_name="3d-worker.log", env=env)
    try:
        return subprocess.Popen(command, **kwargs)
    finally:
        handle.close()


def ensure_3d_worker_service(state: Dict[str, Any]) -> Dict[str, Any]:
    if not env_true("EVAVO_GATEWAY_MANAGE_3D", True):
        return {"status": "disabled", "ready": three_d_health()["healthy"]}
    repo = discover_3d_repo()
    if repo is None:
        return {"status": "not_found", "ready": False}
    os.environ["EVAVO_3D_STUDIO_DIR"] = str(repo)
    current = three_d_health()

    if current["healthy"]:
        token, token_source = ensure_3d_token(allow_create=False)
        if token is None:
            return {"status": "already_running_token_unavailable", "ready": False, "endpoint": THREE_D_URL}
        if not three_d_token_ready(token):
            return {"status": "already_running_token_rejected", "ready": False, "endpoint": THREE_D_URL}

        workspace_raw = os.getenv("EVAVO_3D_AGENT_WORKSPACE_ROOT", "").strip()
        if not workspace_raw:
            managed = state.get("3d_worker") if isinstance(state.get("3d_worker"), dict) else {}
            managed_pid = managed.get("pid")
            if (
                managed.get("managed")
                and managed.get("endpoint") == THREE_D_URL
                and isinstance(managed_pid, int)
                and pid_matches_tokens(managed_pid, "evavo_3d_studio.agent_worker", "serve")
                and isinstance(managed.get("workspace"), str)
                and managed.get("workspace")
            ):
                workspace_raw = str(managed["workspace"])
            else:
                return {"status": "already_running_workspace_unavailable", "ready": False, "endpoint": THREE_D_URL}
        os.environ["EVAVO_3D_AGENT_WORKSPACE_ROOT"] = workspace_raw
        workspace = three_d_workspace(repo)
        os.environ["EVAVO_3D_AGENT_EXECUTION_ENABLED"] = "1"
        os.environ["EVAVO_3D_ENDPOINT"] = THREE_D_URL
        return {
            "status": "already_running",
            "ready": True,
            "endpoint": THREE_D_URL,
            "workspace": str(workspace),
            "token_source": token_source,
        }

    workspace = three_d_workspace(repo)
    token, token_source = ensure_3d_token(allow_create=True)
    if token is None:
        raise RuntimeError("3D worker token is unavailable")
    host, port = endpoint_host_port(THREE_D_URL, expected_default_port=4314)
    if port_open(host, port):
        raise RuntimeError(f"3D worker port {port} is occupied by another service; refusing to replace it")
    process = spawn_3d_worker(repo, workspace, token)
    state["3d_worker"] = {
        "managed": True,
        "pid": process.pid,
        "started_at": now_iso(),
        "repo": str(repo),
        "workspace": str(workspace),
        "endpoint": THREE_D_URL,
    }
    save_state(state)
    try:
        wait_for(lambda: three_d_health()["healthy"], 15.0, "EVAVO 3D worker")
    except Exception:
        if process.poll() is None and pid_matches_tokens(process.pid, "evavo_3d_studio.agent_worker", "serve"):
            terminate_pid(process.pid)
        raise
    return {
        "status": "started",
        "ready": True,
        "pid": process.pid,
        "endpoint": THREE_D_URL,
        "workspace": str(workspace),
        "token_source": token_source,
    }


def ensure_comfyui_service() -> Dict[str, Any]:
    result = ensure_comfyui(
        COMFYUI_URL,
        wait_seconds=float(os.getenv("EVAVO_GATEWAY_COMFYUI_START_TIMEOUT", "120")),
        allow_start=True,
    )
    if not native_health(COMFYUI_URL):
        raise RuntimeError("Native ComfyUI did not become ready; mock backends are not accepted by the production gateway")
    return result


def _managed_gateway_state(state: Dict[str, Any]) -> Dict[str, Any]:
    value = state.get("gateway")
    return value if isinstance(value, dict) else {}


def ensure_gateway_service(state: Dict[str, Any]) -> Dict[str, Any]:
    desired_fingerprint = provider_configuration_fingerprint()
    existing = gateway_health()
    if existing["gateway_alive"]:
        managed = _managed_gateway_state(state)
        managed_pid = managed.get("pid")
        identity_ok = managed.get("managed") and isinstance(managed_pid, int) and pid_matches(managed_pid, GATEWAY_SCRIPT)
        applied = managed.get("provider_fingerprint") == desired_fingerprint
        if identity_ok and not applied:
            terminate_pid(managed_pid)
            wait_for_port_close(GATEWAY_HOST, GATEWAY_PORT)
            state.pop("gateway", None)
            save_state(state)
        else:
            return {
                "status": "already_running" if identity_ok else "already_running_external",
                "healthy": existing["healthy"],
                "provider_configuration_applied": bool(applied) if identity_ok else False,
            }

    if port_open(GATEWAY_HOST, GATEWAY_PORT):
        raise RuntimeError(f"Port {GATEWAY_PORT} is occupied by another process; refusing to replace it")
    if not GATEWAY_SCRIPT.is_file():
        raise RuntimeError(f"Gateway script not found: {GATEWAY_SCRIPT}")
    process = spawn_gateway()
    state["gateway"] = {
        "managed": True,
        "pid": process.pid,
        "started_at": now_iso(),
        "provider_fingerprint": desired_fingerprint,
    }
    save_state(state)
    try:
        wait_for(lambda: gateway_health()["gateway_alive"], 20.0, "EVAVO Gateway")
    except Exception:
        if process.poll() is None and pid_matches(process.pid, GATEWAY_SCRIPT):
            terminate_pid(process.pid)
        raise
    return {
        "status": "started",
        "pid": process.pid,
        "healthy": gateway_health()["healthy"],
        "provider_configuration_applied": True,
    }


def start_services() -> Dict[str, Any]:
    if GATEWAY_HOST not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("Gateway manager is restricted to loopback")
    if not 1 <= GATEWAY_PORT <= 65535:
        raise RuntimeError("Gateway port must be between 1 and 65535")
    endpoint_host_port(THREE_D_URL, expected_default_port=4314)
    state = load_state()
    audio = configure_audio_provider()
    try:
        model3d = ensure_3d_worker_service(state)
    except Exception as exc:
        model3d = {"status": "unavailable", "ready": False, "error": str(exc)}
    comfy = ensure_comfyui_service()
    gateway = ensure_gateway_service(state)
    state["last_start"] = now_iso()
    state["comfyui_endpoint"] = COMFYUI_URL
    state["audio_provider"] = audio
    state["3d_last_start"] = model3d
    save_state(state)
    health = full_health()
    if health["status"] != "healthy":
        raise RuntimeError(f"Gateway stack started but is not healthy: {health}")
    return {"ok": True, "comfyui": comfy, "gateway": gateway, "audio": audio, "3d": model3d, "health": health}


def stop_services() -> Dict[str, Any]:
    state = load_state()
    stopped: Dict[str, Any] = {"gateway": False, "comfyui": False, "3d_worker": False}
    gateway = _managed_gateway_state(state)
    pid = gateway.get("pid")
    if gateway.get("managed") and isinstance(pid, int) and pid_matches(pid, GATEWAY_SCRIPT):
        terminate_pid(pid)
        stopped["gateway"] = True
    model3d = state.get("3d_worker") if isinstance(state.get("3d_worker"), dict) else {}
    model3d_pid = model3d.get("pid")
    if (
        model3d.get("managed")
        and isinstance(model3d_pid, int)
        and pid_matches_tokens(model3d_pid, "evavo_3d_studio.agent_worker", "serve")
    ):
        terminate_pid(model3d_pid)
        stopped["3d_worker"] = True
    native = stop_managed_comfyui()
    stopped["comfyui"] = bool(native.get("stopped"))
    try:
        STATE_FILE.unlink()
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise RuntimeError(f"SERVICE_MANAGER_STATE_DELETE_ERROR:{STATE_FILE}:{exc}") from exc
    return {"ok": True, "stopped": stopped, "native": native, "timestamp": now_iso()}


def monitor(interval: float) -> int:
    start_services()
    try:
        while True:
            health = full_health()
            print(json.dumps(health, ensure_ascii=False), flush=True)
            if not health["manager_state"]["healthy"]:
                raise RuntimeError(str(health["manager_state"].get("error") or "SERVICE_MANAGER_STATE_UNHEALTHY"))
            if not health["comfyui"]["healthy"]:
                ensure_comfyui_service()
            if not health["3d_worker"]["healthy"] and discover_3d_repo() is not None:
                try:
                    ensure_3d_worker_service(load_state())
                except Exception as exc:
                    print(json.dumps({"provider": "3d", "status": "unavailable", "error": str(exc)}), file=sys.stderr, flush=True)
            configure_audio_provider()
            ensure_gateway_service(load_state())
            time.sleep(interval)
    except KeyboardInterrupt:
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage the EVAVO native-image HTTP gateway and local providers")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("start", help="Start/ensure native ComfyUI, local providers and the loopback gateway")
    subparsers.add_parser("stop", help="Stop only identity-verified EVAVO-managed components")
    subparsers.add_parser("health", help="Print core health plus auxiliary provider and manager-state readiness JSON")
    subparsers.add_parser("status", help="Alias for health")
    monitor_parser = subparsers.add_parser("monitor", help="Monitor and restore managed local service health")
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
