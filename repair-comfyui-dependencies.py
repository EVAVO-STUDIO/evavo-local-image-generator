#!/usr/bin/env python3
"""Repair ComfyUI Python dependencies using the checkout's own requirements.

This command is intentionally narrower than a general package installer:
- discovers the ComfyUI checkout and the Python that actually runs it;
- never installs a guessed package globally;
- syncs the local checkout's requirements.txt only when repair is required;
- verifies pip metadata and the requested import afterwards;
- never starts, stops, or kills ComfyUI/Python processes.

It is designed for EVAVO workstation agents as well as direct CLI use.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Iterable, Sequence


ROOT = Path(__file__).resolve().parent
DEFAULT_COMFY_HOME = Path(r"C:\AI\ComfyUI")
DEFAULT_MODULE = "comfy_aimdo"
DEFAULT_TIMEOUT_SECONDS = 900.0


def _candidate_homes(explicit: str | None = None) -> Iterable[Path]:
    """Yield source/portable ComfyUI workdirs using the same practical search space as runtime discovery."""
    seen: set[str] = set()
    home = Path.home()
    repo_parent = ROOT.parent
    local_appdata = Path(os.getenv("LOCALAPPDATA", str(home / "AppData" / "Local")))
    configured_search = [item.strip() for item in os.getenv("EVAVO_COMFYUI_SEARCH_PATHS", "").split(os.pathsep) if item.strip()]
    values = [
        explicit,
        os.environ.get("EVAVO_COMFYUI_HOME"),
        os.environ.get("COMFYUI_HOME"),
        str(repo_parent / "ComfyUI"),
        str(repo_parent / "comfyui"),
        str(repo_parent / "ComfyUI_windows_portable"),
        r"C:\ComfyUI",
        r"C:\Gitrepos\ComfyUI",
        r"C:\GitRepos\ComfyUI",
        r"C:\Gitrepos\ComfyUI_windows_portable",
        r"C:\GitRepos\ComfyUI_windows_portable",
        r"C:\AI",
        str(DEFAULT_COMFY_HOME),
        r"C:\AI\ComfyUI_windows_portable",
        r"C:\ComfyUI_windows_portable",
        str(home / "ComfyUI"),
        str(home / "Documents" / "ComfyUI"),
        str(home / "Documents" / "ComfyUI_windows_portable"),
        str(home / "Downloads" / "ComfyUI"),
        str(home / "Downloads" / "ComfyUI_windows_portable"),
        str(home / "Desktop" / "ComfyUI"),
        str(home / "Desktop" / "ComfyUI_windows_portable"),
        str(local_appdata / "ComfyUI"),
        str(local_appdata / "Programs" / "ComfyUI"),
        *configured_search,
    ]
    for raw in values:
        if not raw:
            continue
        candidate = Path(raw).expanduser()
        workdirs = [candidate]
        # Windows portable packages commonly keep the real checkout one level
        # below the portable root while the embedded Python lives beside it.
        if candidate.name.lower() != "comfyui":
            workdirs.append(candidate / "ComfyUI")
        for workdir in workdirs:
            try:
                normalized = workdir.resolve(strict=False)
            except OSError:
                normalized = workdir.absolute()
            key = os.path.normcase(str(normalized))
            if key in seen:
                continue
            seen.add(key)
            yield normalized


def _discover_home(explicit: str | None = None) -> Path:
    checked: list[str] = []
    for candidate in _candidate_homes(explicit):
        checked.append(str(candidate))
        if (candidate / "main.py").is_file() and (candidate / "requirements.txt").is_file():
            return candidate.resolve()
    raise FileNotFoundError(
        "Could not find a ComfyUI checkout containing main.py and requirements.txt. "
        f"Checked: {checked}"
    )


def _is_portable_python(python_exe: Path) -> bool:
    parts = {part.lower() for part in python_exe.parts}
    return "python_embeded" in parts or "python_embedded" in parts


def _python_candidates(comfy_home: Path, explicit: str | None = None) -> Iterable[Path]:
    seen: set[str] = set()
    env_override = os.environ.get("EVAVO_COMFYUI_PYTHON") or os.environ.get("COMFYUI_PYTHON")
    candidates = [
        Path(explicit).expanduser() if explicit else None,
        Path(env_override).expanduser() if env_override else None,
        comfy_home / ".venv" / "Scripts" / "python.exe",
        comfy_home / "venv" / "Scripts" / "python.exe",
        comfy_home / ".venv" / "bin" / "python",
        comfy_home / "venv" / "bin" / "python",
        comfy_home / "python_embeded" / "python.exe",
        comfy_home / "python_embedded" / "python.exe",
        comfy_home.parent / "python_embeded" / "python.exe",
        comfy_home.parent / "python_embedded" / "python.exe",
        Path(sys.executable),
    ]
    for candidate in candidates:
        if candidate is None:
            continue
        try:
            normalized = candidate.resolve(strict=False)
        except OSError:
            normalized = candidate.absolute()
        key = os.path.normcase(str(normalized))
        if key in seen:
            continue
        seen.add(key)
        yield normalized


def _select_python(comfy_home: Path, explicit: str | None = None) -> Path:
    checked: list[str] = []
    for candidate in _python_candidates(comfy_home, explicit):
        checked.append(str(candidate))
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(f"Could not find a Python interpreter for ComfyUI. Checked: {checked}")


def _python_prefix(python_exe: Path) -> list[str]:
    prefix = [str(python_exe)]
    if _is_portable_python(python_exe):
        # Keep package inspection/repair isolated from the user's site-packages,
        # matching the portable launcher's isolation intent.
        prefix.append("-s")
    return prefix


def _module_probe_command(python_exe: Path, module: str) -> list[str]:
    code = (
        "import importlib, json, sys; "
        f"m=importlib.import_module({module!r}); "
        "print(json.dumps({'ok': True, 'module': m.__name__, "
        "'version': getattr(m, '__version__', None), 'python': sys.executable}))"
    )
    return [*_python_prefix(python_exe), "-c", code]


def _pip_version_command(python_exe: Path) -> list[str]:
    return [*_python_prefix(python_exe), "-m", "pip", "--version"]


def _pip_install_command(python_exe: Path, requirements: Path) -> list[str]:
    return [
        *_python_prefix(python_exe),
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "-r",
        str(requirements),
    ]


def _pip_check_command(python_exe: Path) -> list[str]:
    return [*_python_prefix(python_exe), "-m", "pip", "check"]


def _run(
    command: Sequence[str],
    *,
    cwd: Path,
    timeout: float,
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            list(command),
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        return {
            "command": list(command),
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "duration_seconds": round(time.monotonic() - started, 3),
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return {
            "command": list(command),
            "returncode": None,
            "stdout": stdout,
            "stderr": stderr,
            "duration_seconds": round(time.monotonic() - started, 3),
            "timed_out": True,
        }


def _trim(value: str, limit: int = 12000) -> str:
    if len(value) <= limit:
        return value
    return value[-limit:]


def _public_result(step: dict[str, Any]) -> dict[str, Any]:
    return {
        "command": step.get("command"),
        "returncode": step.get("returncode"),
        "stdout": _trim(str(step.get("stdout") or "")),
        "stderr": _trim(str(step.get("stderr") or "")),
        "duration_seconds": step.get("duration_seconds"),
        "timed_out": bool(step.get("timed_out")),
    }


def _write_last_result(comfy_home: Path, payload: dict[str, Any]) -> str | None:
    try:
        state_dir = comfy_home / ".evavo"
        state_dir.mkdir(parents=True, exist_ok=True)
        path = state_dir / "dependency-repair-last.json"
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return str(path)
    except OSError:
        return None


def repair_dependencies(
    *,
    comfy_home: str | None = None,
    python_exe: str | None = None,
    module: str = DEFAULT_MODULE,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    force_sync: bool = False,
    verify_only: bool = False,
) -> tuple[int, dict[str, Any]]:
    home = _discover_home(comfy_home)
    python_path = _select_python(home, python_exe)
    requirements = home / "requirements.txt"

    payload: dict[str, Any] = {
        "ok": False,
        "status": "starting",
        "comfy_home": str(home),
        "python": str(python_path),
        "portable_python": _is_portable_python(python_path),
        "requirements": str(requirements),
        "module": module,
        "repair_performed": False,
        "steps": {},
    }

    probe_before = _run(_module_probe_command(python_path, module), cwd=home, timeout=min(timeout, 60.0))
    payload["steps"]["module_before"] = _public_result(probe_before)
    module_ok_before = probe_before["returncode"] == 0 and not probe_before["timed_out"]

    pip_version = _run(_pip_version_command(python_path), cwd=home, timeout=min(timeout, 60.0))
    payload["steps"]["pip"] = _public_result(pip_version)
    if pip_version["returncode"] != 0 or pip_version["timed_out"]:
        payload["status"] = "pip_unavailable"
        payload["message"] = "The selected ComfyUI interpreter cannot run pip; no package mutation was attempted."
        payload["result_file"] = _write_last_result(home, payload)
        return 3, payload

    if verify_only:
        pip_check = _run(_pip_check_command(python_path), cwd=home, timeout=min(timeout, 120.0))
        payload["steps"]["pip_check"] = _public_result(pip_check)
        payload["ok"] = module_ok_before and pip_check["returncode"] == 0 and not pip_check["timed_out"]
        payload["status"] = "verified" if payload["ok"] else "verification_failed"
        payload["message"] = (
            "Dependency verification passed without mutation."
            if payload["ok"]
            else "Dependency verification failed; run again without --verify-only to repair from local requirements.txt."
        )
        payload["result_file"] = _write_last_result(home, payload)
        return (0 if payload["ok"] else 2), payload

    if force_sync or not module_ok_before:
        install = _run(_pip_install_command(python_path, requirements), cwd=home, timeout=timeout)
        payload["steps"]["requirements_sync"] = _public_result(install)
        payload["repair_performed"] = True
        if install["returncode"] != 0 or install["timed_out"]:
            payload["status"] = "requirements_sync_failed"
            payload["message"] = "Failed to synchronize the local ComfyUI requirements with its selected Python interpreter."
            payload["result_file"] = _write_last_result(home, payload)
            return 4, payload

    probe_after = _run(_module_probe_command(python_path, module), cwd=home, timeout=min(timeout, 60.0))
    payload["steps"]["module_after"] = _public_result(probe_after)
    pip_check = _run(_pip_check_command(python_path), cwd=home, timeout=min(timeout, 120.0))
    payload["steps"]["pip_check"] = _public_result(pip_check)

    module_ok_after = probe_after["returncode"] == 0 and not probe_after["timed_out"]
    metadata_ok = pip_check["returncode"] == 0 and not pip_check["timed_out"]
    payload["ok"] = module_ok_after and metadata_ok
    if payload["ok"]:
        payload["status"] = "repaired" if payload["repair_performed"] else "already_healthy"
        payload["message"] = (
            "ComfyUI dependencies were synchronized from the local requirements.txt and verified."
            if payload["repair_performed"]
            else "The requested module and installed dependency metadata are already healthy."
        )
        exit_code = 0
    else:
        payload["status"] = "post_repair_verification_failed"
        payload["message"] = "Dependency repair completed but post-repair import or pip metadata verification still fails."
        exit_code = 5

    payload["result_file"] = _write_last_result(home, payload)
    return exit_code, payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Repair ComfyUI dependencies from the checkout's own requirements.txt using its own Python runtime."
    )
    parser.add_argument("--comfy-home", help=r"Explicit ComfyUI workdir containing main.py + requirements.txt")
    parser.add_argument("--python", dest="python_exe", help="Explicit ComfyUI Python interpreter")
    parser.add_argument("--module", default=DEFAULT_MODULE, help=f"Import used to decide whether repair is needed (default: {DEFAULT_MODULE})")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS, help="Maximum seconds for requirements synchronization")
    parser.add_argument("--force-sync", action="store_true", help="Run pip install -r requirements.txt even when the module already imports")
    parser.add_argument("--verify-only", action="store_true", help="Verify module + pip check without modifying packages")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.timeout <= 0:
        print(json.dumps({"ok": False, "status": "invalid_arguments", "message": "--timeout must be > 0"}, indent=2))
        return 64
    try:
        exit_code, payload = repair_dependencies(
            comfy_home=args.comfy_home,
            python_exe=args.python_exe,
            module=args.module,
            timeout=args.timeout,
            force_sync=args.force_sync,
            verify_only=args.verify_only,
        )
    except (FileNotFoundError, OSError) as exc:
        exit_code = 2
        payload = {"ok": False, "status": "discovery_failed", "message": str(exc)}
    except Exception as exc:  # keep the workstation receipt structured even for unexpected faults
        exit_code = 70
        payload = {"ok": False, "status": "repair_exception", "message": f"{type(exc).__name__}: {exc}"}

    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
