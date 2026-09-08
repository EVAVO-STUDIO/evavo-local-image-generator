#!/usr/bin/env python3
"""Provision an isolated local ComfyUI runtime for EVAVO.

The provisioner installs the application/runtime only. It deliberately does
not download diffusion checkpoints because model files are large and may have
separate licenses or access requirements.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from evavo_operations import ROOT, now_iso

OFFICIAL_COMFYUI_REPOSITORY = "https://github.com/Comfy-Org/ComfyUI.git"
DEFAULT_NVIDIA_TORCH_INDEX = "https://download.pytorch.org/whl/cu130"
STATE_FILE = ROOT / ".evavo" / "comfyui-provision.json"


def run(command: List[str], *, cwd: Optional[Path] = None, timeout: int = 1800) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"COMMAND_NOT_FOUND:{command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"COMMAND_TIMEOUT:{' '.join(command[:3])}") from exc


def require_ok(result: subprocess.CompletedProcess[str], action: str) -> None:
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "unknown error").strip()[-3000:]
        raise RuntimeError(f"{action}:{detail}")


def default_target() -> Path:
    configured = os.getenv("EVAVO_COMFYUI_HOME")
    if configured:
        return Path(configured).expanduser().resolve()
    return (ROOT.parent / "ComfyUI").resolve()


def venv_python(target: Path) -> Path:
    if os.name == "nt":
        return target / ".venv" / "Scripts" / "python.exe"
    return target / ".venv" / "bin" / "python"


def git_dirty(target: Path) -> bool:
    result = run(["git", "status", "--porcelain"], cwd=target, timeout=30)
    return result.returncode == 0 and bool(result.stdout.strip())


def ensure_checkout(target: Path, repository: str, update: bool) -> Dict[str, Any]:
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        result = run(["git", "clone", "--depth", "1", repository, str(target)], timeout=600)
        require_ok(result, "COMFYUI_CLONE_FAILED")
        return {"status": "cloned", "repository": repository}

    main_py = target / "main.py"
    if not main_py.is_file():
        raise RuntimeError(f"COMFYUI_TARGET_CONFLICT:{target} exists but does not contain main.py")

    if not (target / ".git").exists() or not update:
        return {"status": "existing", "repository": repository}

    if git_dirty(target):
        return {"status": "existing_dirty_not_updated", "repository": repository}

    result = run(["git", "pull", "--ff-only"], cwd=target, timeout=180)
    require_ok(result, "COMFYUI_UPDATE_FAILED")
    return {"status": "updated", "repository": repository}


def ensure_venv(target: Path) -> Path:
    python = venv_python(target)
    if python.is_file():
        return python
    result = run([sys.executable, "-m", "venv", str(target / ".venv")], cwd=target, timeout=300)
    require_ok(result, "COMFYUI_VENV_FAILED")
    if not python.is_file():
        raise RuntimeError(f"COMFYUI_VENV_FAILED:interpreter missing at {python}")
    return python


def nvidia_available() -> bool:
    command = shutil.which("nvidia-smi")
    if not command:
        return False
    try:
        result = run([command, "--query-gpu=name", "--format=csv,noheader"], timeout=15)
    except RuntimeError:
        return False
    return result.returncode == 0 and bool(result.stdout.strip())


def install_runtime(target: Path, python: Path, *, install_pytorch: bool, torch_index_url: str) -> Dict[str, Any]:
    result = run([str(python), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"], cwd=target, timeout=600)
    require_ok(result, "PIP_BOOTSTRAP_FAILED")

    nvidia = nvidia_available()
    if nvidia and install_pytorch:
        result = run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "torch",
                "torchvision",
                "torchaudio",
                "--extra-index-url",
                torch_index_url,
            ],
            cwd=target,
            timeout=1800,
        )
        require_ok(result, "PYTORCH_INSTALL_FAILED")

    requirements = target / "requirements.txt"
    if not requirements.is_file():
        raise RuntimeError(f"COMFYUI_REQUIREMENTS_MISSING:{requirements}")
    result = run([str(python), "-m", "pip", "install", "-r", str(requirements)], cwd=target, timeout=1800)
    require_ok(result, "COMFYUI_REQUIREMENTS_FAILED")

    return {"nvidia_detected": nvidia, "pytorch_special_install": bool(nvidia and install_pytorch), "torch_index_url": torch_index_url if nvidia and install_pytorch else None}


def verify_runtime(target: Path, python: Path) -> Dict[str, Any]:
    code = (
        "import json, torch; "
        "print(json.dumps({'torch_version': torch.__version__, 'cuda_available': bool(torch.cuda.is_available()), "
        "'cuda_version': getattr(torch.version, 'cuda', None), 'device_count': int(torch.cuda.device_count())}))"
    )
    result = run([str(python), "-c", code], cwd=target, timeout=60)
    require_ok(result, "COMFYUI_TORCH_VERIFY_FAILED")
    try:
        torch_info = json.loads(result.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as exc:
        raise RuntimeError(f"COMFYUI_TORCH_VERIFY_FAILED:{result.stdout[-1000:]}") from exc

    main_py = target / "main.py"
    if not main_py.is_file():
        raise RuntimeError(f"COMFYUI_VERIFY_FAILED:missing {main_py}")

    checkpoints = target / "models" / "checkpoints"
    checkpoints.mkdir(parents=True, exist_ok=True)
    existing_models = [path.name for path in checkpoints.iterdir() if path.is_file() and path.suffix.lower() in {".safetensors", ".ckpt", ".pt", ".pth"}]
    return {
        "main_py": str(main_py),
        "python": str(python),
        "torch": torch_info,
        "checkpoint_directory": str(checkpoints),
        "checkpoint_files": sorted(existing_models),
    }


def save_state(payload: Dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp = STATE_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, STATE_FILE)


def provision(args: argparse.Namespace) -> Dict[str, Any]:
    target = Path(args.target).expanduser().resolve() if args.target else default_target()
    checkout = ensure_checkout(target, args.repository, not args.skip_update)
    python = ensure_venv(target)
    install = install_runtime(
        target,
        python,
        install_pytorch=not args.skip_pytorch,
        torch_index_url=args.torch_index_url,
    )
    verification = verify_runtime(target, python)
    payload = {
        "ok": True,
        "status": "provisioned",
        "timestamp": now_iso(),
        "target": str(target),
        "checkout": checkout,
        "install": install,
        "verification": verification,
        "environment": {
            "EVAVO_COMFYUI_HOME": str(target),
            "EVAVO_COMFYUI_PYTHON": str(python),
        },
        "model_required": not bool(verification["checkpoint_files"]),
    }
    save_state(payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision official ComfyUI for EVAVO")
    parser.add_argument("--target", help="ComfyUI installation directory; defaults to sibling C:/Gitrepos/ComfyUI-style location")
    parser.add_argument("--repository", default=os.getenv("EVAVO_COMFYUI_REPOSITORY", OFFICIAL_COMFYUI_REPOSITORY))
    parser.add_argument("--skip-update", action="store_true", help="Do not git pull an existing clean checkout")
    parser.add_argument("--skip-pytorch", action="store_true", help="Do not perform NVIDIA-specific PyTorch install before ComfyUI requirements")
    parser.add_argument("--torch-index-url", default=os.getenv("EVAVO_TORCH_INDEX_URL", DEFAULT_NVIDIA_TORCH_INDEX))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        payload = provision(args)
    except RuntimeError as exc:
        payload = {"ok": False, "status": "failed", "message": str(exc), "timestamp": now_iso()}
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(f"ERROR: {payload['message']}", file=sys.stderr)
        return 3

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print("EVAVO ComfyUI provisioner")
        print("=" * 72)
        print(f"Target:     {payload['target']}")
        print(f"Checkout:   {payload['checkout']['status']}")
        print(f"Python:     {payload['verification']['python']}")
        print(f"Torch:      {payload['verification']['torch']['torch_version']}")
        print(f"CUDA:       {payload['verification']['torch']['cuda_available']}")
        print(f"Checkpoints:{len(payload['verification']['checkpoint_files'])}")
        if payload["model_required"]:
            print("A diffusion checkpoint is still required before real generation can pass readiness checks.")
        print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
