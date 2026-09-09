#!/usr/bin/env python3
"""Capture read-only runtime evidence for EVAVO Atmosphere or 3D Studio.

This utility intentionally does not execute production jobs or mutate sibling
repositories. It records repository/runtime identity and delegates readiness to
the Studio's own doctor/toolchain surfaces.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_receipt(path: Path) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    return {"path": str(resolved), "bytes": resolved.stat().st_size, "sha256": _sha256(resolved)}


def _subprocess_kwargs() -> dict[str, Any]:
    if os.name != "nt":
        return {}
    flags = 0
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        flags |= subprocess.CREATE_NO_WINDOW
    return {"creationflags": flags} if flags else {}


def _run(argv: list[str], *, cwd: Path | None = None, timeout: float = 60.0) -> dict[str, Any]:
    try:
        result = subprocess.run(
            argv,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            **_subprocess_kwargs(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "argv": argv, "error": str(exc)}
    return {
        "ok": result.returncode == 0,
        "argv": argv,
        "returncode": result.returncode,
        "stdout": result.stdout.strip()[:20000],
        "stderr": result.stderr.strip()[:8000],
    }


def _resolve_repo_python(root: Path, explicit: str = "") -> str:
    requested = str(explicit or "").strip()
    if requested:
        candidate = Path(requested).expanduser()
        if candidate.is_file():
            return str(candidate.resolve())
        resolved = shutil.which(requested)
        if resolved:
            return resolved
        raise ValueError(f"requested Python executable was not found: {requested}")

    for candidate in (
        root / ".venv" / "Scripts" / "python.exe",
        root / "venv" / "Scripts" / "python.exe",
        root / ".venv" / "bin" / "python",
        root / "venv" / "bin" / "python",
    ):
        if candidate.is_file() and not candidate.is_symlink():
            return str(candidate.resolve())
    return sys.executable


def _json_from_command(result: dict[str, Any]) -> dict[str, Any] | None:
    stdout = str(result.get("stdout", "")).strip()
    if not stdout:
        return None
    try:
        value = json.loads(stdout)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        start = stdout.find("{")
        end = stdout.rfind("}")
        if start >= 0 and end > start:
            try:
                value = json.loads(stdout[start : end + 1])
                return value if isinstance(value, dict) else None
            except json.JSONDecodeError:
                return None
        return None


def _git_snapshot(root: Path) -> dict[str, Any]:
    git = shutil.which("git")
    if not git or not (root / ".git").exists():
        return {"available": False, "head": None, "dirty": None}
    head = _run([git, "rev-parse", "HEAD"], cwd=root, timeout=15.0)
    status = _run([git, "status", "--porcelain"], cwd=root, timeout=15.0)
    remote = _run([git, "remote", "get-url", "origin"], cwd=root, timeout=15.0)
    return {
        "available": bool(head.get("ok")),
        "head": head.get("stdout") if head.get("ok") else None,
        "dirty": bool(status.get("stdout")) if status.get("ok") else None,
        "origin": remote.get("stdout") if remote.get("ok") else None,
        "head_error": None if head.get("ok") else head,
        "status_error": None if status.get("ok") else status,
    }


def _command_version(executable: str, *args: str) -> dict[str, Any]:
    path = shutil.which(executable)
    if not path:
        return {"available": False, "executable": executable}
    result = _run([path, *args], timeout=20.0)
    return {"available": bool(result.get("ok")), "path": path, **result}


def _nvidia_snapshot() -> dict[str, Any]:
    path = shutil.which("nvidia-smi")
    if not path:
        return {"available": False}
    result = _run(
        [
            path,
            "--query-gpu=name,driver_version,memory.total,memory.free",
            "--format=csv,noheader,nounits",
        ],
        timeout=15.0,
    )
    return {"available": bool(result.get("ok")), **result}


def _loopback_http(value: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(value)
        _ = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "http"
        and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        and not parsed.username
        and not parsed.password
        and not parsed.query
        and not parsed.fragment
    )


def _http_json(url: str, timeout: float = 5.0) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "EVAVO-Studio-Attestation/1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            value = json.loads(response.read().decode("utf-8"))
    except (OSError, TimeoutError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError(f"HTTP JSON request failed for {url}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"HTTP JSON response was not an object: {url}")
    return value


def _atmosphere(root: Path) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    package = root / "package.json"
    if not package.is_file():
        failures.append(f"Atmosphere package.json not found: {package}")
        return {}, failures

    npm = shutil.which("npm.cmd") or shutil.which("npm")
    files = [_file_receipt(package)]
    for name in ("package-lock.json", "pnpm-lock.yaml", "yarn.lock"):
        candidate = root / name
        if candidate.is_file() and not candidate.is_symlink():
            files.append(_file_receipt(candidate))

    node = _command_version("node", "--version")
    npm_version = _command_version("npm.cmd" if os.name == "nt" else "npm", "--version")
    ffmpeg = _command_version(os.getenv("FFMPEG_PATH", "ffmpeg"), "-version")
    ffprobe = _command_version(os.getenv("FFPROBE_PATH", "ffprobe"), "-version")
    for label, receipt in (("node", node), ("npm", npm_version), ("ffmpeg", ffmpeg), ("ffprobe", ffprobe)):
        if not receipt.get("available"):
            failures.append(f"Atmosphere required runtime unavailable: {label}")

    doctor_command: dict[str, Any]
    doctor_payload: dict[str, Any] | None = None
    if npm:
        doctor_command = _run([npm, "--silent", "run", "doctor"], cwd=root, timeout=180.0)
        doctor_payload = _json_from_command(doctor_command)
        if not doctor_command.get("ok"):
            failures.append("Atmosphere doctor command failed")
        elif not isinstance(doctor_payload, dict) or doctor_payload.get("passes") is not True:
            failures.append("Atmosphere doctor did not return passes=true JSON")
    else:
        doctor_command = {"ok": False, "error": "npm unavailable"}
        failures.append("Atmosphere npm unavailable")

    return {
        "files": files,
        "node": node,
        "npm": npm_version,
        "ffmpeg": ffmpeg,
        "ffprobe": ffprobe,
        "doctor": doctor_payload,
        "doctor_command": doctor_command,
    }, failures


def _three_d(root: Path, python: str, worker_endpoint: str | None) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        failures.append(f"3D Studio pyproject.toml not found: {pyproject}")
        return {}, failures

    files = [_file_receipt(pyproject)]
    for relative in (
        Path("contracts") / "capabilities-v1.json",
        Path("contracts") / "provider-registry-v1.json",
        Path("contracts") / "quality-profiles-v1.json",
    ):
        candidate = root / relative
        if candidate.is_file() and not candidate.is_symlink():
            files.append(_file_receipt(candidate))

    python_receipt = _run([python, "--version"], cwd=root, timeout=15.0)
    if not python_receipt.get("ok"):
        failures.append("3D Studio Python runtime failed")

    doctor_command = _run([python, "-m", "evavo_3d_studio", "doctor"], cwd=root, timeout=120.0)
    doctor = _json_from_command(doctor_command)
    if not doctor_command.get("ok"):
        failures.append("3D Studio doctor command failed")
    elif not isinstance(doctor, dict) or doctor.get("ok") is not True:
        failures.append("3D Studio doctor did not return ok=true JSON")

    toolchain_command = _run([python, "-m", "evavo_3d_studio", "toolchain", "inspect"], cwd=root, timeout=120.0)
    toolchain = _json_from_command(toolchain_command)
    if not toolchain_command.get("ok") or not isinstance(toolchain, dict):
        failures.append("3D Studio toolchain inspection failed")

    providers_command = _run([python, "-m", "evavo_3d_studio", "providers", "list"], cwd=root, timeout=120.0)
    providers = _json_from_command(providers_command)
    if not providers_command.get("ok") or not isinstance(providers, dict):
        failures.append("3D Studio provider inspection failed")

    worker: dict[str, Any] | None = None
    if worker_endpoint:
        base = worker_endpoint.rstrip("/")
        if not _loopback_http(base):
            failures.append("3D worker endpoint must be loopback HTTP")
        else:
            try:
                health = _http_json(base + "/api/v1/health")
                capabilities = _http_json(base + "/api/v1/capabilities")
                authority_ok = (
                    health.get("ok") is True
                    and health.get("service") == "evavo-3d-agent-worker"
                    and health.get("executionEnabled") is True
                    and health.get("authority") == "token-gated-candidate-production-only"
                    and capabilities.get("automaticApproval") is False
                    and capabilities.get("canonicalPromotion") is False
                    and capabilities.get("gitMutation") is False
                    and capabilities.get("deployment") is False
                    and capabilities.get("publication") is False
                    and capabilities.get("clientRelease") is False
                )
                worker = {"endpoint": base, "health": health, "capabilities": capabilities, "authority_ok": authority_ok}
                if not authority_ok:
                    failures.append("3D worker exceeds or does not satisfy bounded candidate-production authority")
            except RuntimeError as exc:
                worker = {"endpoint": base, "error": str(exc)}
                failures.append(str(exc))

    return {
        "files": files,
        "python_executable": python,
        "python": python_receipt,
        "doctor": doctor,
        "doctor_command": doctor_command,
        "toolchain": toolchain,
        "toolchain_command": toolchain_command,
        "providers": providers,
        "providers_command": providers_command,
        "worker": worker,
    }, failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture EVAVO sibling-Studio runtime evidence")
    parser.add_argument("studio", choices=["atmosphere", "3d"])
    parser.add_argument("--root", required=True)
    parser.add_argument("--python", default="", help="3D Python override; default resolves the repo .venv first")
    parser.add_argument("--worker-endpoint", default="")
    parser.add_argument("--output", required=True)
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    failures: list[str] = []
    if not root.is_dir():
        failures.append(f"Studio root not found: {root}")
        detail: dict[str, Any] = {}
    elif args.studio == "atmosphere":
        detail, studio_failures = _atmosphere(root)
        failures.extend(studio_failures)
    else:
        try:
            three_d_python = _resolve_repo_python(root, args.python)
        except ValueError as exc:
            three_d_python = args.python or sys.executable
            failures.append(str(exc))
        detail, studio_failures = _three_d(root, three_d_python, args.worker_endpoint.strip() or None)
        failures.extend(studio_failures)

    git = _git_snapshot(root) if root.is_dir() else {"available": False, "head": None, "dirty": None}
    if root.is_dir() and not git.get("available"):
        failures.append(f"{args.studio} root is not an attestable Git checkout")

    payload = {
        "schema_version": 2,
        "captured_at": datetime.now().astimezone().isoformat(),
        "studio": args.studio,
        "root": str(root),
        "git": git,
        "gpu": _nvidia_snapshot(),
        "detail": detail,
        "complete": not failures,
        "failures": failures,
        "authority": "read-only runtime attestation; no production jobs or repository mutation",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"ok": not failures or not args.require_complete, "output": str(output), "complete": not failures, "failures": failures}, indent=2))
    return 1 if args.require_complete and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
