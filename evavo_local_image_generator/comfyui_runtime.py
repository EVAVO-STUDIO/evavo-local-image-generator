"""Local ComfyUI discovery, diagnostics, and lifecycle helpers for agent automation."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from .backends import ComfyUIBackend

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / ".evavo"
STATE_FILE = STATE_DIR / "native-comfyui-service.json"
MOCK_STATE_FILE = STATE_DIR / "operations-service.json"
LOG_FILE = STATE_DIR / "native-comfyui.log"
LAST_FAILURE_FILE = STATE_DIR / "native-comfyui-last-failure.json"
EXTRA_MODEL_CONFIG = STATE_DIR / "extra-model-paths.yaml"

MODEL_PATH_CANDIDATES: Dict[str, Sequence[str]] = {
    "checkpoints": ("checkpoints", "models/checkpoints", "Stable-diffusion", "models/Stable-diffusion"),
    "configs": ("configs", "models/configs", "models/Stable-diffusion"),
    "loras": ("loras", "models/loras", "Lora", "models/Lora", "LyCORIS", "models/LyCORIS"),
    "vae": ("vae", "models/vae", "VAE", "models/VAE"),
    "text_encoders": ("text_encoders", "models/text_encoders", "clip", "models/clip"),
    "diffusion_models": ("diffusion_models", "models/diffusion_models", "unet", "models/unet"),
    "clip_vision": ("clip_vision", "models/clip_vision"),
    "style_models": ("style_models", "models/style_models"),
    "embeddings": ("embeddings", "models/embeddings"),
    "diffusers": ("diffusers", "models/diffusers"),
    "vae_approx": ("vae_approx", "models/vae_approx"),
    "controlnet": ("controlnet", "models/controlnet", "ControlNet", "models/ControlNet", "t2i_adapter", "models/t2i_adapter"),
    "gligen": ("gligen", "models/gligen"),
    "upscale_models": ("upscale_models", "models/upscale_models", "ESRGAN", "models/ESRGAN", "RealESRGAN", "models/RealESRGAN", "SwinIR", "models/SwinIR"),
    "latent_upscale_models": ("latent_upscale_models", "models/latent_upscale_models"),
    "custom_nodes": ("custom_nodes",),
    "datasets": ("datasets",),
    "hypernetworks": ("hypernetworks", "models/hypernetworks"),
    "photomaker": ("photomaker", "models/photomaker"),
    "classifiers": ("classifiers", "models/classifiers"),
    "model_patches": ("model_patches", "models/model_patches"),
    "audio_encoders": ("audio_encoders", "models/audio_encoders"),
    "background_removal": ("background_removal", "models/background_removal"),
    "frame_interpolation": ("frame_interpolation", "models/frame_interpolation"),
    "geometry_estimation": ("geometry_estimation", "models/geometry_estimation"),
    "optical_flow": ("optical_flow", "models/optical_flow"),
    "detection": ("detection", "models/detection"),
}


@dataclass(frozen=True)
class ComfyUIInstall:
    root: Path
    python: Path
    main_py: Path
    portable: bool

    @property
    def workdir(self) -> Path:
        """Directory from which ComfyUI's main.py must be executed."""
        return self.main_py.parent

    def command(
        self,
        host: str = "127.0.0.1",
        port: int = 8188,
        *,
        extra_model_config: Optional[Path] = None,
        cpu: bool = False,
        disable_all_custom_nodes: bool = False,
    ) -> List[str]:
        command = [str(self.python), str(self.main_py)]
        if self.portable:
            command.append("--windows-standalone-build")
        command.extend(["--listen", host, "--port", str(port)])
        if cpu:
            command.append("--cpu")
        if disable_all_custom_nodes:
            command.append("--disable-all-custom-nodes")
        if extra_model_config is not None:
            command.extend(["--extra-model-paths-config", str(extra_model_config)])
        return command

    def to_dict(self) -> Dict[str, Any]:
        return {
            "root": str(self.root),
            "python": str(self.python),
            "main_py": str(self.main_py),
            "workdir": str(self.workdir),
            "portable": self.portable,
        }


def _env_true(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _candidate_roots() -> List[Path]:
    candidates: List[Path] = []
    configured = os.getenv("EVAVO_COMFYUI_HOME")
    if configured:
        candidates.append(Path(configured).expanduser())

    home = Path.home()
    repo_parent = ROOT.parent
    local_appdata = Path(os.getenv("LOCALAPPDATA", str(home / "AppData" / "Local")))
    candidates.extend([
        repo_parent / "ComfyUI",
        repo_parent / "comfyui",
        repo_parent / "ComfyUI_windows_portable",
        Path("C:/ComfyUI"),
        Path("C:/Gitrepos/ComfyUI"),
        Path("C:/GitRepos/ComfyUI"),
        Path("C:/Gitrepos/ComfyUI_windows_portable"),
        Path("C:/GitRepos/ComfyUI_windows_portable"),
        Path("C:/AI"),
        Path("C:/AI/ComfyUI"),
        Path("C:/AI/ComfyUI_windows_portable"),
        Path("C:/ComfyUI_windows_portable"),
        home / "ComfyUI",
        home / "Documents" / "ComfyUI",
        home / "Documents" / "ComfyUI_windows_portable",
        home / "Downloads" / "ComfyUI",
        home / "Downloads" / "ComfyUI_windows_portable",
        home / "Desktop" / "ComfyUI",
        home / "Desktop" / "ComfyUI_windows_portable",
        local_appdata / "ComfyUI",
        local_appdata / "Programs" / "ComfyUI",
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


def _configured_python() -> Optional[Path]:
    raw = os.getenv("EVAVO_COMFYUI_PYTHON") or os.getenv("COMFYUI_PYTHON")
    if not raw:
        return None
    candidate = Path(raw).expanduser().resolve()
    if not candidate.is_file():
        raise RuntimeError(f"COMFYUI_PYTHON_NOT_FOUND:{candidate}")
    return candidate


def _is_embedded_python(path: Path) -> bool:
    return path.parent.name.lower() in {"python_embeded", "python_embedded"}


def inspect_install(root: Path) -> Optional[ComfyUIInstall]:
    """Inspect a ComfyUI checkout, including the common parent-level portable Python layout."""
    root = root.expanduser().resolve()
    configured_python = _configured_python()

    main_py = root / "main.py"
    if main_py.is_file():
        python_candidates = [
            root / ".venv" / "Scripts" / "python.exe",
            root / "venv" / "Scripts" / "python.exe",
            root / "python_embeded" / "python.exe",
            root / "python_embedded" / "python.exe",
            root.parent / "python_embeded" / "python.exe",
            root.parent / "python_embedded" / "python.exe",
            root / ".venv" / "bin" / "python",
            root / "venv" / "bin" / "python",
        ]
        python = configured_python or next((candidate for candidate in python_candidates if candidate.is_file()), Path(sys.executable))
        return ComfyUIInstall(root=root, python=python, main_py=main_py, portable=_is_embedded_python(python))

    portable_main = root / "ComfyUI" / "main.py"
    portable_python_candidates = [
        root / "python_embeded" / "python.exe",
        root / "python_embedded" / "python.exe",
    ]
    portable_python = configured_python or next((candidate for candidate in portable_python_candidates if candidate.is_file()), None)
    if portable_main.is_file() and portable_python is not None:
        return ComfyUIInstall(root=root, python=portable_python, main_py=portable_main, portable=True)
    return None


def discover_comfyui() -> List[ComfyUIInstall]:
    installs: List[ComfyUIInstall] = []
    seen = set()
    for candidate in _candidate_roots():
        install = inspect_install(candidate)
        if install is not None:
            key = (
                os.path.normcase(str(install.main_py.resolve())),
                os.path.normcase(str(install.python.resolve())),
            )
            if key not in seen:
                seen.add(key)
                installs.append(install)
    return installs


def configured_shared_model_roots() -> List[Path]:
    """Return validated local/shared model-library roots configured by the operator."""
    raw = os.getenv("EVAVO_SHARED_MODEL_ROOTS") or os.getenv("EVAVO_COMFYUI_MODEL_ROOTS") or ""
    roots: List[Path] = []
    seen = set()
    for item in raw.split(os.pathsep):
        if not item.strip():
            continue
        root = Path(item.strip()).expanduser().resolve()
        if not root.is_dir():
            raise RuntimeError(f"SHARED_MODEL_ROOT_NOT_FOUND:{root}")
        key = os.path.normcase(str(root))
        if key not in seen:
            seen.add(key)
            roots.append(root)
    return roots


def _relative_existing_paths(root: Path, candidates: Sequence[str]) -> List[str]:
    found: List[str] = []
    seen = set()
    for relative in candidates:
        path = root / Path(relative)
        if not path.is_dir():
            continue
        normalized = Path(relative).as_posix().rstrip("/")
        key = normalized.lower()
        if key not in seen:
            seen.add(key)
            found.append(normalized)
    return found


def _yaml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def render_extra_model_paths_yaml(roots: Sequence[Path]) -> str:
    """Render an EVAVO-owned ComfyUI extra_model_paths YAML document."""
    lines = [
        "# EVAVO managed ComfyUI extra model paths.",
        "# Generated from EVAVO_SHARED_MODEL_ROOTS / EVAVO_COMFYUI_MODEL_ROOTS.",
        "# Do not edit this file; change the environment setting instead.",
        "",
    ]
    emitted = 0
    for root in roots:
        categories: Dict[str, List[str]] = {}
        for key, candidates in MODEL_PATH_CANDIDATES.items():
            paths = _relative_existing_paths(root, candidates)
            if paths:
                categories[key] = paths
        if not categories:
            continue
        emitted += 1
        lines.append(f"evavo_shared_{emitted}:")
        lines.append(f"  base_path: {_yaml_string(root.as_posix())}")
        for key, paths in categories.items():
            if len(paths) == 1:
                lines.append(f"  {key}: {_yaml_string(paths[0])}")
            else:
                lines.append(f"  {key}: |")
                lines.extend(f"    {path}" for path in paths)
        lines.append("")
    if emitted == 0:
        raise RuntimeError("SHARED_MODEL_ROOT_EMPTY:no supported ComfyUI model directories were found in configured roots")
    return "\n".join(lines).rstrip() + "\n"


def shared_model_configuration() -> Dict[str, Any]:
    roots = configured_shared_model_roots()
    if not roots:
        return {"roots": [], "yaml": None, "sha256": None}
    text = render_extra_model_paths_yaml(roots)
    return {
        "roots": roots,
        "yaml": text,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def write_extra_model_paths_config(
    roots: Optional[Sequence[Path]] = None,
    destination: Path = EXTRA_MODEL_CONFIG,
) -> Optional[Path]:
    configured = list(roots) if roots is not None else configured_shared_model_roots()
    destination = destination.expanduser().resolve()
    if not configured:
        try:
            destination.unlink()
        except OSError:
            pass
        return None

    text = render_extra_model_paths_yaml(configured)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=destination.name + ".", suffix=".tmp", dir=str(destination.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, destination)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    return destination


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json_atomic(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def load_state() -> Dict[str, Any]:
    return _load_json(STATE_FILE)


def load_last_failure() -> Dict[str, Any]:
    """Return the last structured ComfyUI startup failure, if one exists."""
    return _load_json(LAST_FAILURE_FILE)


def _process_command_line(pid: int) -> Optional[str]:
    if pid <= 0:
        return None
    if os.name == "nt":
        powershell = shutil.which("powershell.exe") or shutil.which("pwsh.exe") or shutil.which("powershell") or shutil.which("pwsh")
        if not powershell:
            return None
        script = f"$p=Get-CimInstance Win32_Process -Filter 'ProcessId = {pid}' -ErrorAction SilentlyContinue; if ($p) {{ $p.CommandLine }}"
        try:
            result = subprocess.run([powershell, "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            return None
        value = result.stdout.strip()
        return value or None

    proc_cmdline = Path(f"/proc/{pid}/cmdline")
    if proc_cmdline.is_file():
        try:
            data = proc_cmdline.read_bytes().replace(b"\x00", b" ").decode("utf-8", errors="replace").strip()
            if data:
                return data
        except OSError:
            pass
    try:
        result = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = result.stdout.strip()
    return value or None


def _command_contains_path(command_line: Optional[str], path: Path) -> bool:
    if not command_line:
        return False
    command = command_line.replace("\\", "/").lower()
    expected = str(path.expanduser().resolve()).replace("\\", "/").lower()
    return expected in command


def _native_state_identity_matches(state: Dict[str, Any]) -> bool:
    pid = state.get("pid")
    install = state.get("install")
    if not isinstance(pid, int) or pid <= 0 or not isinstance(install, dict):
        return False
    main_py = install.get("main_py")
    if not isinstance(main_py, str) or not main_py:
        return False
    return _command_contains_path(_process_command_line(pid), Path(main_py))


def _save_state(
    pid: int,
    endpoint: str,
    install: ComfyUIInstall,
    command: Sequence[str],
    *,
    extra_model_config: Optional[Path],
    shared_roots: Sequence[Path],
    config_sha256: Optional[str],
) -> None:
    payload: Dict[str, Any] = {
        "pid": pid,
        "endpoint": endpoint,
        "started_at": datetime.now().astimezone().isoformat(),
        "install": install.to_dict(),
        "command": list(command),
        "shared_model_roots": [str(item) for item in shared_roots],
        "extra_model_paths_sha256": config_sha256,
    }
    if extra_model_config is not None:
        payload["extra_model_paths_config"] = str(extra_model_config)
    _write_json_atomic(STATE_FILE, payload)


def _clear_state() -> None:
    try:
        STATE_FILE.unlink()
    except OSError:
        pass


def _clear_last_failure() -> None:
    try:
        LAST_FAILURE_FILE.unlink()
    except OSError:
        pass


def _evavo_mock_running(endpoint: str) -> bool:
    try:
        with urllib.request.urlopen(f"{endpoint.rstrip('/')}/system", timeout=0.75) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError):
        return False
    return isinstance(payload, dict) and payload.get("service") == "evavo-local-image-generator" and payload.get("mode") == "mock"


def _terminate_pid(pid: int) -> None:
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True, timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
    else:
        try:
            os.killpg(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass


def _stop_managed_mock() -> bool:
    state = _load_json(MOCK_STATE_FILE)
    pid = state.get("pid")
    if not isinstance(pid, int) or pid <= 0:
        return False
    expected = ROOT / "mock-comfyui-server.py"
    if not _command_contains_path(_process_command_line(pid), expected):
        return False
    try:
        _terminate_pid(pid)
    finally:
        try:
            MOCK_STATE_FILE.unlink()
        except OSError:
            pass
    return True


def native_health(endpoint: str = "http://127.0.0.1:8188") -> Optional[Dict[str, Any]]:
    if _evavo_mock_running(endpoint):
        return None
    try:
        return ComfyUIBackend(endpoint).health()
    except RuntimeError:
        return None


def stop_managed_comfyui() -> Dict[str, Any]:
    state = load_state()
    pid = state.get("pid")
    if not isinstance(pid, int) or pid <= 0:
        return {"status": "not_managed", "stopped": False}
    if not _native_state_identity_matches(state):
        _clear_state()
        return {"status": "stale_or_identity_mismatch", "stopped": False, "pid": pid}
    try:
        _terminate_pid(pid)
    finally:
        _clear_state()
    return {"status": "stopped", "stopped": True, "pid": pid}


def _endpoint_host_port(endpoint: str) -> tuple[str, int]:
    parsed = urllib.parse.urlparse(endpoint)
    if parsed.scheme != "http" or not parsed.hostname:
        raise RuntimeError(f"COMFYUI_ENDPOINT_INVALID:{endpoint}")
    try:
        port = parsed.port or 80
    except ValueError as exc:
        raise RuntimeError(f"COMFYUI_ENDPOINT_INVALID:{endpoint}") from exc
    return parsed.hostname, port


def _port_open(host: str, port: int, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _windows_port_owners(port: int) -> List[Dict[str, Any]]:
    if os.name != "nt":
        return []
    try:
        result = subprocess.run(["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return []
    owners: List[Dict[str, Any]] = []
    seen = set()
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[0].upper() != "TCP" or parts[3].upper() != "LISTENING":
            continue
        local = parts[1]
        if not local.endswith(f":{port}"):
            continue
        try:
            pid = int(parts[-1])
        except ValueError:
            continue
        if pid in seen:
            continue
        seen.add(pid)
        owners.append({"pid": pid, "command_line": _process_command_line(pid)})
    return owners


def _read_log_since(path: Path, start_offset: int, max_bytes: int = 128 * 1024) -> str:
    try:
        with path.open("rb") as handle:
            handle.seek(max(0, start_offset))
            data = handle.read()
    except OSError:
        return ""
    if len(data) > max_bytes:
        data = data[-max_bytes:]
    return data.decode("utf-8", errors="replace")


def _meaningful_tail(text: str, limit: int = 60) -> str:
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n") if line.strip()]
    return "\n".join(lines[-max(1, limit):])


def _extract_missing_modules(text: str) -> List[str]:
    modules: List[str] = []
    patterns = [
        r"ModuleNotFoundError:\s*No module named ['\"]([^'\"]+)['\"]",
        r"ImportError:\s*No module named ['\"]([^'\"]+)['\"]",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            module = match.group(1).strip()
            if module and module not in modules:
                modules.append(module)
    return modules


def _extract_error_summary(text: str, fallback: str) -> str:
    lines = [line.strip() for line in text.replace("\r\n", "\n").split("\n") if line.strip()]
    preferred = []
    for line in lines:
        lower = line.lower()
        if (
            "modulenotfounderror" in lower
            or "importerror" in lower
            or "runtimeerror" in lower
            or "oserror" in lower
            or "winerror" in lower
            or "address already in use" in lower
            or "failed to" in lower
            or "error:" in lower
            or "exception:" in lower
        ):
            preferred.append(line)
    summary = preferred[-1] if preferred else (lines[-1] if lines else fallback)
    return summary[-1200:]


def classify_startup_output(
    text: str,
    *,
    returncode: Optional[int],
    health_ready: bool,
    timed_out: bool,
    port_was_open: bool = False,
) -> Dict[str, Any]:
    """Classify ComfyUI startup output into a stable agent-readable failure category."""
    lowered = text.lower()
    missing_modules = _extract_missing_modules(text)
    custom_node_signal = any(token in lowered for token in ("custom_nodes", "custom node", "prestartup script", "prestartup_script"))
    port_signal = port_was_open or any(
        token in lowered
        for token in ("address already in use", "winerror 10048", "errno 98", "eaddrinuse", "only one usage of each socket address")
    )
    torch_signal = any(token in lowered for token in ("torch.cuda", "cuda error", "cuda runtime", "pytorch", "torch not compiled", "cuda initialization"))

    if health_ready:
        category = "ready"
        summary = "ComfyUI bound to the HTTP endpoint and responded to /system_stats."
    elif port_signal:
        category = "port_in_use"
        summary = _extract_error_summary(text, "Port 8188 was already occupied before or during ComfyUI startup.")
    elif missing_modules and custom_node_signal:
        category = "custom_node_dependency"
        summary = _extract_error_summary(text, f"Missing custom-node dependency: {', '.join(missing_modules)}")
    elif missing_modules:
        category = "missing_dependency"
        summary = _extract_error_summary(text, f"Missing Python dependency: {', '.join(missing_modules)}")
    elif torch_signal:
        category = "torch_or_cuda_initialization"
        summary = _extract_error_summary(text, "PyTorch/CUDA initialization failed.")
    elif "traceback (most recent call last)" in lowered or "fatal error" in lowered or "unhandled exception" in lowered:
        category = "startup_exception"
        summary = _extract_error_summary(text, "ComfyUI raised an exception during startup.")
    elif returncode is not None:
        category = "process_exited"
        summary = _extract_error_summary(text, f"ComfyUI exited before binding (exit code {returncode}).")
    elif timed_out:
        category = "startup_timeout"
        summary = _extract_error_summary(text, "ComfyUI stayed alive but did not respond before the startup deadline.")
    else:
        category = "not_ready"
        summary = _extract_error_summary(text, "ComfyUI did not become ready.")

    return {
        "category": category,
        "summary": summary,
        "missing_modules": missing_modules,
        "custom_node_signal": custom_node_signal,
        "torch_or_cuda_signal": torch_signal,
        "port_signal": port_signal,
        "returncode": returncode,
        "health_ready": health_ready,
        "timed_out": timed_out,
        "log_tail": _meaningful_tail(text),
        "recommended_isolation": (
            not health_ready and category in {"custom_node_dependency", "startup_exception", "startup_timeout", "not_ready"}
        ),
    }


def _record_failure(
    install: Optional[ComfyUIInstall],
    command: Sequence[str],
    endpoint: str,
    diagnostic: Dict[str, Any],
    *,
    log_file: Path,
    port_owners: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "timestamp": datetime.now().astimezone().isoformat(),
        "endpoint": endpoint,
        "install": install.to_dict() if install is not None else None,
        "command": list(command),
        "log_file": str(log_file),
        **diagnostic,
    }
    if port_owners:
        payload["port_owners"] = port_owners
    _write_json_atomic(LAST_FAILURE_FILE, payload)
    return payload


def ensure_comfyui(endpoint: str = "http://127.0.0.1:8188", *, wait_seconds: float = 90.0, allow_start: bool = True) -> Dict[str, Any]:
    """Return healthy native ComfyUI and provide structured startup failure evidence on failure."""
    endpoint = endpoint.rstrip("/")
    desired = shared_model_configuration()
    desired_roots = list(desired["roots"])
    desired_hash = desired["sha256"]

    existing = native_health(endpoint)
    if existing:
        _clear_last_failure()
        state = load_state()
        managed_here = bool(state) and state.get("endpoint") == endpoint and _native_state_identity_matches(state)
        if state and not managed_here:
            _clear_state()
            state = {}

        if managed_here and state.get("extra_model_paths_sha256") != desired_hash:
            if not allow_start:
                raise RuntimeError("COMFYUI_RESTART_REQUIRED:EVAVO shared model configuration changed")
            stopped = stop_managed_comfyui()
            if not stopped.get("stopped"):
                raise RuntimeError(f"COMFYUI_RESTART_FAILED:{stopped.get('status')}")
            time.sleep(0.75)
        else:
            result: Dict[str, Any] = {"status": "already_running", "started": False, "health": existing, "endpoint": endpoint}
            if desired_roots:
                result["shared_model_roots"] = [str(item) for item in desired_roots]
                result["shared_model_config_verified"] = managed_here and state.get("extra_model_paths_sha256") == desired_hash
                if not managed_here:
                    result["shared_model_config_note"] = "ComfyUI is user-managed; EVAVO cannot verify whether these shared roots were loaded"
            return result

    if not allow_start:
        raise RuntimeError("COMFYUI_OFFLINE:native ComfyUI is not running")

    installs = discover_comfyui()
    if not installs:
        diagnostic = {
            "category": "comfyui_not_found",
            "summary": "No ComfyUI main.py installation was found in configured or standard locations.",
            "missing_modules": [],
            "custom_node_signal": False,
            "torch_or_cuda_signal": False,
            "port_signal": False,
            "returncode": None,
            "health_ready": False,
            "timed_out": False,
            "log_tail": "",
            "recommended_isolation": False,
        }
        _record_failure(None, [], endpoint, diagnostic, log_file=LOG_FILE)
        raise RuntimeError("COMFYUI_NOT_FOUND:set EVAVO_COMFYUI_HOME or install ComfyUI in a standard location")
    if endpoint != "http://127.0.0.1:8188":
        raise RuntimeError("COMFYUI_AUTOSTART_ENDPOINT:auto-start currently manages http://127.0.0.1:8188 only")

    if _evavo_mock_running(endpoint):
        if not _stop_managed_mock():
            raise RuntimeError("COMFYUI_PORT_OCCUPIED:EVAVO mock is running but its recorded process identity could not be verified")
        time.sleep(0.75)

    host, port = _endpoint_host_port(endpoint)
    if _port_open(host, port):
        owners = _windows_port_owners(port)
        diagnostic = classify_startup_output("", returncode=None, health_ready=False, timed_out=False, port_was_open=True)
        _record_failure(installs[0], [], endpoint, diagnostic, log_file=LOG_FILE, port_owners=owners)
        owner_text = ", ".join(str(item.get("pid")) for item in owners) if owners else "unknown"
        raise RuntimeError(f"COMFYUI_PORT_OCCUPIED:{host}:{port}; owner_pids={owner_text}; diagnostics={LAST_FAILURE_FILE}")

    install = installs[0]
    extra_model_config = write_extra_model_paths_config(desired_roots)
    cpu_mode = _env_true("EVAVO_COMFYUI_CPU", False)
    disable_custom_nodes = _env_true("EVAVO_COMFYUI_DISABLE_ALL_CUSTOM_NODES", False)
    command = install.command(
        extra_model_config=extra_model_config,
        cpu=cpu_mode,
        disable_all_custom_nodes=disable_custom_nodes,
    )
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    log_offset = LOG_FILE.stat().st_size if LOG_FILE.exists() else 0
    log_handle = LOG_FILE.open("ab", buffering=0)
    child_env = os.environ.copy()
    child_env.setdefault("PYTHONUNBUFFERED", "1")
    child_env.setdefault("PYTHONUTF8", "1")
    child_env.setdefault("PYTHONIOENCODING", "utf-8")
    kwargs: Dict[str, Any] = {
        "cwd": str(install.workdir),
        "stdin": subprocess.DEVNULL,
        "stdout": log_handle,
        "stderr": subprocess.STDOUT,
        "env": child_env,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True

    try:
        process = subprocess.Popen(command, **kwargs)
    finally:
        log_handle.close()
    _save_state(
        process.pid,
        endpoint,
        install,
        command,
        extra_model_config=extra_model_config,
        shared_roots=desired_roots,
        config_sha256=desired_hash,
    )

    deadline = time.monotonic() + max(1.0, wait_seconds)
    health: Optional[Dict[str, Any]] = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            break
        health = native_health(endpoint)
        if health:
            _clear_last_failure()
            result = {
                "status": "started",
                "started": True,
                "pid": process.pid,
                "endpoint": endpoint,
                "install": install.to_dict(),
                "log_file": str(LOG_FILE),
                "health": health,
                "shared_model_roots": [str(item) for item in desired_roots],
                "shared_model_config_sha256": desired_hash,
                "cpu_mode": cpu_mode,
                "custom_nodes_disabled": disable_custom_nodes,
            }
            if extra_model_config is not None:
                result["extra_model_paths_config"] = str(extra_model_config)
            return result
        time.sleep(0.5)

    returncode = process.poll()
    timed_out = returncode is None
    if process.poll() is None:
        try:
            _terminate_pid(process.pid)
        except Exception:
            pass
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
    _clear_state()
    text = _read_log_since(LOG_FILE, log_offset)
    diagnostic = classify_startup_output(
        text,
        returncode=returncode,
        health_ready=False,
        timed_out=timed_out,
    )
    failure = _record_failure(install, command, endpoint, diagnostic, log_file=LOG_FILE)
    summary = str(failure.get("summary", "ComfyUI failed to start")).replace("\r", " ").replace("\n", " ")[:1200]
    raise RuntimeError(
        f"COMFYUI_START_FAILED:{failure['category']}:{summary}; "
        f"python={install.python}; log={LOG_FILE}; diagnostics={LAST_FAILURE_FILE}"
    )


def _diagnostic_health(endpoint: str) -> bool:
    try:
        with urllib.request.urlopen(f"{endpoint.rstrip('/')}/system_stats", timeout=0.8) as response:
            return 200 <= int(getattr(response, "status", 200)) < 300
    except (OSError, TimeoutError, urllib.error.URLError, urllib.error.HTTPError):
        return False


def diagnose_comfyui_startup(
    *,
    seconds: float = 60.0,
    endpoint: str = "http://127.0.0.1:8188",
    listen_host: str = "0.0.0.0",
    cpu: bool = True,
    disable_all_custom_nodes: bool = False,
    output_file: Optional[Path] = None,
    stream_callback: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Run an owned ComfyUI process for a bounded diagnostic window and capture both output streams.

    The function never terminates a pre-existing process. It terminates only the child it
    creates. Callers such as MCP should leave ``stream_callback`` unset so stdout remains
    protocol-safe; the standalone CLI supplies a callback for real-time console output.
    """
    try:
        duration = float(seconds)
    except (TypeError, ValueError) as exc:
        raise ValueError("seconds must be a number") from exc
    if not 0.1 <= duration <= 600.0:
        raise ValueError("seconds must be between 0.1 and 600")

    endpoint = endpoint.rstrip("/")
    host, port = _endpoint_host_port(endpoint)
    installs = discover_comfyui()
    if not installs:
        return {
            "ok": False,
            "status": "failed",
            "category": "comfyui_not_found",
            "summary": "No ComfyUI installation was found.",
            "duration_seconds": duration,
            "endpoint": endpoint,
        }

    install = installs[0]
    command = install.command(host=listen_host, port=port, cpu=cpu, disable_all_custom_nodes=disable_all_custom_nodes)
    target = (output_file or (STATE_DIR / "comfy-startup-output.txt")).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    preexisting_port = _port_open(host, port)
    port_owners = _windows_port_owners(port) if preexisting_port else []

    child_env = os.environ.copy()
    child_env["PYTHONUNBUFFERED"] = "1"
    child_env["PYTHONUTF8"] = "1"
    child_env["PYTHONIOENCODING"] = "utf-8"

    popen_kwargs: Dict[str, Any] = {
        "cwd": str(install.workdir),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "bufsize": 1,
        "env": child_env,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True

    captured: List[str] = []
    capture_lock = threading.Lock()
    file_lock = threading.Lock()

    def emit(channel: str, message: str) -> None:
        stamp = datetime.now().astimezone().isoformat(timespec="milliseconds")
        rendered = f"[{stamp}] [{channel}] {message.rstrip()}"
        with capture_lock:
            captured.append(rendered)
        with file_lock:
            with target.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(rendered + "\n")
        if stream_callback is not None:
            stream_callback(rendered)

    target.write_text("", encoding="utf-8")
    emit("DIAG", f"ComfyUI startup diagnostic window: {duration:.3f}s")
    emit("DIAG", f"Install: {install.main_py}")
    emit("DIAG", f"Python: {install.python}")
    emit("DIAG", f"Portable interpreter: {install.portable}")
    emit("DIAG", f"Command: {subprocess.list2cmdline(command)}")
    emit("DIAG", f"Endpoint probe: {endpoint}")
    emit("DIAG", f"Port occupied before launch: {preexisting_port}")
    if port_owners:
        for owner in port_owners:
            emit("DIAG", f"Existing port owner PID={owner.get('pid')} command={owner.get('command_line') or 'unknown'}")

    start = time.monotonic()
    process: Optional[subprocess.Popen[str]] = None
    launch_error: Optional[str] = None
    health_ready = False
    ready_after: Optional[float] = None
    alive_at_deadline = False
    reader_threads: List[threading.Thread] = []

    try:
        process = subprocess.Popen(command, **popen_kwargs)
        emit("DIAG", f"Spawned PID {process.pid}")

        def reader(channel: str, stream: Any) -> None:
            try:
                for raw in iter(stream.readline, ""):
                    if raw == "":
                        break
                    emit(channel, raw)
            finally:
                try:
                    stream.close()
                except Exception:
                    pass

        assert process.stdout is not None and process.stderr is not None
        for channel, stream in (("STDOUT", process.stdout), ("STDERR", process.stderr)):
            thread = threading.Thread(target=reader, args=(channel, stream), daemon=True, name=f"comfy-diag-{channel.lower()}")
            thread.start()
            reader_threads.append(thread)

        deadline = start + duration
        while time.monotonic() < deadline:
            if not preexisting_port and not health_ready and _diagnostic_health(endpoint):
                health_ready = True
                ready_after = time.monotonic() - start
                emit("DIAG", f"HTTP /system_stats became ready after {ready_after:.3f}s")
            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(min(0.25, remaining))
    except OSError as exc:
        launch_error = f"{type(exc).__name__}: {exc}"
        emit("DIAG", f"Launch failure: {launch_error}")
    finally:
        elapsed = time.monotonic() - start
        if elapsed < duration:
            time.sleep(duration - elapsed)
        alive_at_deadline = process is not None and process.poll() is None
        if alive_at_deadline and process is not None:
            emit("DIAG", f"Diagnostic window complete; terminating owned PID {process.pid}")
            _terminate_pid(process.pid)
        if process is not None:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                except OSError:
                    pass
        for thread in reader_threads:
            thread.join(timeout=2)

    elapsed = time.monotonic() - start
    returncode = process.returncode if process is not None else None
    text = "\n".join(captured)
    if launch_error:
        text += "\n" + launch_error
    diagnostic = classify_startup_output(
        text,
        returncode=returncode,
        health_ready=health_ready,
        timed_out=not health_ready and alive_at_deadline and launch_error is None,
        port_was_open=preexisting_port,
    )
    result: Dict[str, Any] = {
        "ok": health_ready and not preexisting_port,
        "status": "ready" if health_ready and not preexisting_port else "failed",
        "duration_seconds": duration,
        "elapsed_seconds": round(elapsed, 3),
        "endpoint": endpoint,
        "install": install.to_dict(),
        "command": command,
        "pid": process.pid if process is not None else None,
        "returncode": returncode,
        "ready_after_seconds": round(ready_after, 3) if ready_after is not None else None,
        "output_file": str(target),
        "preexisting_port": preexisting_port,
        "port_owners": port_owners,
        "custom_nodes_disabled": disable_all_custom_nodes,
        "cpu_mode": cpu,
        **diagnostic,
    }
    emit("SUMMARY", f"Category: {result['category']}")
    emit("SUMMARY", f"Summary: {result['summary']}")
    emit("SUMMARY", f"Health ready: {result['health_ready']}")
    emit("SUMMARY", f"Return code: {result['returncode']}")
    if result.get("missing_modules"):
        emit("SUMMARY", f"Missing modules: {', '.join(result['missing_modules'])}")
    if result.get("recommended_isolation") and not disable_all_custom_nodes:
        emit("SUMMARY", "Recommended next probe: repeat with --disable-all-custom-nodes to isolate custom-node startup faults")
    result["log_tail"] = _meaningful_tail("\n".join(captured))
    return result
