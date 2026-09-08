"""Local ComfyUI discovery and lifecycle helpers for agent automation."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .backends import ComfyUIBackend

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / ".evavo"
STATE_FILE = STATE_DIR / "native-comfyui-service.json"
MOCK_STATE_FILE = STATE_DIR / "operations-service.json"
LOG_FILE = STATE_DIR / "native-comfyui.log"


@dataclass(frozen=True)
class ComfyUIInstall:
    root: Path
    python: Path
    main_py: Path
    portable: bool

    def command(self, host: str = "127.0.0.1", port: int = 8188) -> List[str]:
        command = [str(self.python), str(self.main_py), "--listen", host, "--port", str(port)]
        if self.portable:
            command.insert(2, "--windows-standalone-build")
        return command

    def to_dict(self) -> Dict[str, Any]:
        return {"root": str(self.root), "python": str(self.python), "main_py": str(self.main_py), "portable": self.portable}


def _candidate_roots() -> List[Path]:
    candidates: List[Path] = []
    configured = os.getenv("EVAVO_COMFYUI_HOME")
    if configured:
        candidates.append(Path(configured).expanduser())

    home = Path.home()
    candidates.extend([
        Path("C:/ComfyUI"),
        Path("C:/Gitrepos/ComfyUI"),
        Path("C:/GitRepos/ComfyUI"),
        Path("C:/AI/ComfyUI"),
        Path("C:/ComfyUI_windows_portable"),
        home / "ComfyUI",
        home / "Documents" / "ComfyUI",
        home / "Downloads" / "ComfyUI_windows_portable",
        home / "Desktop" / "ComfyUI",
    ])

    extra = os.getenv("EVAVO_COMFYUI_SEARCH_PATHS", "")
    for raw in extra.split(os.pathsep):
        if raw.strip():
            candidates.append(Path(raw.strip()).expanduser())

    unique: List[Path] = []
    seen = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = candidate.absolute()
        key = os.path.normcase(str(resolved))
        if key not in seen:
            seen.add(key)
            unique.append(resolved)
    return unique


def inspect_install(root: Path) -> Optional[ComfyUIInstall]:
    root = root.expanduser().resolve()
    main_py = root / "main.py"
    if main_py.is_file():
        python_candidates = [
            root / ".venv" / "Scripts" / "python.exe",
            root / "venv" / "Scripts" / "python.exe",
            root / ".venv" / "bin" / "python",
            root / "venv" / "bin" / "python",
        ]
        python = next((candidate for candidate in python_candidates if candidate.is_file()), Path(sys.executable))
        return ComfyUIInstall(root=root, python=python, main_py=main_py, portable=False)

    portable_main = root / "ComfyUI" / "main.py"
    portable_python = root / "python_embeded" / "python.exe"
    if portable_main.is_file() and portable_python.is_file():
        return ComfyUIInstall(root=root, python=portable_python, main_py=portable_main, portable=True)
    return None


def discover_comfyui() -> List[ComfyUIInstall]:
    installs: List[ComfyUIInstall] = []
    for candidate in _candidate_roots():
        install = inspect_install(candidate)
        if install is not None:
            installs.append(install)
    return installs


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def load_state() -> Dict[str, Any]:
    return _load_json(STATE_FILE)


def _save_state(pid: int, endpoint: str, install: ComfyUIInstall) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps({"pid": pid, "endpoint": endpoint, "install": install.to_dict()}, indent=2) + "\n", encoding="utf-8")


def _clear_state() -> None:
    try:
        STATE_FILE.unlink()
    except OSError:
        pass


def _evavo_mock_running(endpoint: str) -> bool:
    try:
        with urllib.request.urlopen(f"{endpoint.rstrip('/')}/system", timeout=0.75) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError):
        return False
    return isinstance(payload, dict) and payload.get("service") == "evavo-local-image-generator" and payload.get("mode") == "mock"


def _stop_managed_mock() -> bool:
    state = _load_json(MOCK_STATE_FILE)
    pid = state.get("pid")
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=10)
        else:
            try:
                os.kill(pid, 15)
            except ProcessLookupError:
                pass
    finally:
        try:
            MOCK_STATE_FILE.unlink()
        except OSError:
            pass
    return True


def native_health(endpoint: str = "http://127.0.0.1:8188") -> Optional[Dict[str, Any]]:
    # The deterministic EVAVO test/mock service intentionally exposes native-like
    # routes for integration testing; never classify that compatibility service as
    # a real renderer.
    if _evavo_mock_running(endpoint):
        return None
    try:
        return ComfyUIBackend(endpoint).health()
    except RuntimeError:
        return None


def ensure_comfyui(endpoint: str = "http://127.0.0.1:8188", *, wait_seconds: float = 90.0, allow_start: bool = True) -> Dict[str, Any]:
    """Return healthy native ComfyUI, starting a discovered local install if needed."""
    endpoint = endpoint.rstrip("/")
    existing = native_health(endpoint)
    if existing:
        return {"status": "already_running", "started": False, "health": existing, "endpoint": endpoint}
    if not allow_start:
        raise RuntimeError("COMFYUI_OFFLINE:native ComfyUI is not running")

    installs = discover_comfyui()
    if not installs:
        raise RuntimeError("COMFYUI_NOT_FOUND:set EVAVO_COMFYUI_HOME or install ComfyUI in a standard location")
    if endpoint != "http://127.0.0.1:8188":
        raise RuntimeError("COMFYUI_AUTOSTART_ENDPOINT:auto-start currently manages http://127.0.0.1:8188 only")

    # If EVAVO itself started the mock fallback earlier, safely retire only that
    # managed process before bringing up the real renderer on the same port.
    if _evavo_mock_running(endpoint):
        if not _stop_managed_mock():
            raise RuntimeError("COMFYUI_PORT_OCCUPIED:EVAVO mock is running but is not managed by the current checkout")
        time.sleep(0.75)

    install = installs[0]
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    log_handle = LOG_FILE.open("ab", buffering=0)
    kwargs: Dict[str, Any] = {
        "cwd": str(install.root if not install.portable else install.root / "ComfyUI"),
        "stdin": subprocess.DEVNULL,
        "stdout": log_handle,
        "stderr": subprocess.STDOUT,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True

    try:
        process = subprocess.Popen(install.command(), **kwargs)
    finally:
        log_handle.close()
    _save_state(process.pid, endpoint, install)

    deadline = time.monotonic() + max(1.0, wait_seconds)
    last_error = "not ready"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            last_error = f"process exited with code {process.returncode}"
            break
        health = native_health(endpoint)
        if health:
            return {
                "status": "started",
                "started": True,
                "pid": process.pid,
                "endpoint": endpoint,
                "install": install.to_dict(),
                "log_file": str(LOG_FILE),
                "health": health,
            }
        last_error = "waiting for /system_stats"
        time.sleep(0.5)

    if process.poll() is None:
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=10)
            else:
                process.terminate()
        except Exception:
            pass
    _clear_state()
    raise RuntimeError(f"COMFYUI_START_FAILED:{last_error}; log={LOG_FILE}")


def stop_managed_comfyui() -> Dict[str, Any]:
    state = load_state()
    pid = state.get("pid")
    if not isinstance(pid, int) or pid <= 0:
        return {"status": "not_managed", "stopped": False}
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=10)
        else:
            try:
                os.kill(pid, 15)
            except ProcessLookupError:
                pass
    finally:
        _clear_state()
    return {"status": "stopped", "stopped": True, "pid": pid}
