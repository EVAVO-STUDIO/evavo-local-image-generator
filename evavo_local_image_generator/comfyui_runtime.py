"""Local ComfyUI discovery and lifecycle helpers for agent automation."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .backends import ComfyUIBackend

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / ".evavo"
STATE_FILE = STATE_DIR / "native-comfyui-service.json"
MOCK_STATE_FILE = STATE_DIR / "operations-service.json"
LOG_FILE = STATE_DIR / "native-comfyui.log"
EXTRA_MODEL_CONFIG = STATE_DIR / "extra-model-paths.yaml"

# Canonical ComfyUI model folder keys, with common source/portable/A1111-style
# relative directory variants. Only directories that actually exist are emitted.
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

    def command(
        self,
        host: str = "127.0.0.1",
        port: int = 8188,
        *,
        extra_model_config: Optional[Path] = None,
    ) -> List[str]:
        command = [str(self.python), str(self.main_py)]
        if self.portable:
            command.append("--windows-standalone-build")
        command.extend(["--listen", host, "--port", str(port)])
        if extra_model_config is not None:
            command.extend(["--extra-model-paths-config", str(extra_model_config)])
        return command

    def to_dict(self) -> Dict[str, Any]:
        return {"root": str(self.root), "python": str(self.python), "main_py": str(self.main_py), "portable": self.portable}


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
    raw = os.getenv("EVAVO_COMFYUI_PYTHON")
    if not raw:
        return None
    candidate = Path(raw).expanduser().resolve()
    if not candidate.is_file():
        raise RuntimeError(f"COMFYUI_PYTHON_NOT_FOUND:{candidate}")
    return candidate


def inspect_install(root: Path) -> Optional[ComfyUIInstall]:
    root = root.expanduser().resolve()
    main_py = root / "main.py"
    if main_py.is_file():
        configured_python = _configured_python()
        python_candidates = [
            root / ".venv" / "Scripts" / "python.exe",
            root / "venv" / "Scripts" / "python.exe",
            root / "python_embeded" / "python.exe",
            root / ".venv" / "bin" / "python",
            root / "venv" / "bin" / "python",
        ]
        python = configured_python or next((candidate for candidate in python_candidates if candidate.is_file()), Path(sys.executable))
        return ComfyUIInstall(root=root, python=python, main_py=main_py, portable=False)

    portable_main = root / "ComfyUI" / "main.py"
    portable_python = root / "python_embeded" / "python.exe"
    if portable_main.is_file() and portable_python.is_file():
        return ComfyUIInstall(root=root, python=portable_python, main_py=portable_main, portable=True)
    return None


def discover_comfyui() -> List[ComfyUIInstall]:
    installs: List[ComfyUIInstall] = []
    seen = set()
    for candidate in _candidate_roots():
        install = inspect_install(candidate)
        if install is not None:
            key = os.path.normcase(str(install.root))
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
    # JSON strings are valid YAML scalars and safely escape Windows backslashes,
    # quotes and control characters without depending on PyYAML.
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


def write_extra_model_paths_config(
    roots: Optional[Sequence[Path]] = None,
    destination: Path = EXTRA_MODEL_CONFIG,
) -> Optional[Path]:
    """Atomically write EVAVO's extra model-path config, or return None when unused."""
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


def load_state() -> Dict[str, Any]:
    return _load_json(STATE_FILE)


def _save_state(pid: int, endpoint: str, install: ComfyUIInstall, *, extra_model_config: Optional[Path] = None) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    payload: Dict[str, Any] = {"pid": pid, "endpoint": endpoint, "install": install.to_dict()}
    if extra_model_config is not None:
        payload["extra_model_paths_config"] = str(extra_model_config)
        payload["shared_model_roots"] = [str(item) for item in configured_shared_model_roots()]
    STATE_FILE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


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

    if _evavo_mock_running(endpoint):
        if not _stop_managed_mock():
            raise RuntimeError("COMFYUI_PORT_OCCUPIED:EVAVO mock is running but is not managed by the current checkout")
        time.sleep(0.75)

    install = installs[0]
    extra_model_config = write_extra_model_paths_config()
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
        process = subprocess.Popen(
            install.command(extra_model_config=extra_model_config),
            **kwargs,
        )
    finally:
        log_handle.close()
    _save_state(process.pid, endpoint, install, extra_model_config=extra_model_config)

    deadline = time.monotonic() + max(1.0, wait_seconds)
    last_error = "not ready"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            last_error = f"process exited with code {process.returncode}"
            break
        health = native_health(endpoint)
        if health:
            result: Dict[str, Any] = {
                "status": "started",
                "started": True,
                "pid": process.pid,
                "endpoint": endpoint,
                "install": install.to_dict(),
                "log_file": str(LOG_FILE),
                "health": health,
            }
            if extra_model_config is not None:
                result["extra_model_paths_config"] = str(extra_model_config)
                result["shared_model_roots"] = [str(item) for item in configured_shared_model_roots()]
            return result
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
