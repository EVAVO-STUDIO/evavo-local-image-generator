#!/usr/bin/env python3
"""Capture reproducible local Kokoro-FastAPI runtime evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from evavo_local_image_generator.backends import KokoroBackend


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run(argv: list[str], cwd: Path | None = None, timeout: float = 15.0) -> dict[str, Any]:
    try:
        result = subprocess.run(argv, cwd=str(cwd) if cwd else None, capture_output=True, text=True, timeout=timeout)
        return {
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout.strip()[:8000],
            "stderr": result.stderr.strip()[:4000],
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": str(exc)}


def _git_snapshot(root: Path) -> dict[str, Any]:
    git = shutil.which("git")
    if not git or not (root / ".git").exists():
        return {"available": False}
    head = _run([git, "rev-parse", "HEAD"], cwd=root)
    status = _run([git, "status", "--porcelain"], cwd=root)
    return {
        "available": bool(head.get("ok")),
        "head": head.get("stdout") if head.get("ok") else None,
        "dirty": bool(status.get("stdout")) if status.get("ok") else None,
        "status_error": None if status.get("ok") else status,
    }


def _important_files(root: Path) -> list[dict[str, Any]]:
    names = (
        "start-gpu.ps1",
        "start-cpu.ps1",
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yml",
        "compose.yaml",
        "pyproject.toml",
        "requirements.txt",
        "Dockerfile",
    )
    result = []
    for name in names:
        path = root / name
        if path.is_file() and not path.is_symlink():
            result.append({"path": str(path.resolve()), "bytes": path.stat().st_size, "sha256": _sha256(path)})
    return result


def _gpu_snapshot() -> dict[str, Any]:
    nvidia = shutil.which("nvidia-smi")
    if not nvidia:
        return {"available": False}
    result = _run(
        [
            nvidia,
            "--query-gpu=name,driver_version,memory.total,memory.free",
            "--format=csv,noheader,nounits",
        ],
        timeout=10.0,
    )
    return {"available": bool(result.get("ok")), **result}


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture Kokoro runtime evidence")
    parser.add_argument("--root", default=os.getenv("KOKORO_DIR") or os.getenv("EVAVO_KOKORO_DIR") or r"C:\AI\Kokoro-FastAPI")
    parser.add_argument("--endpoint", default=os.getenv("KOKORO_ENDPOINT") or os.getenv("EVAVO_KOKORO_ENDPOINT") or "http://127.0.0.1:8880")
    parser.add_argument("--output", required=True)
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    failures: list[str] = []

    if not root.is_dir():
        failures.append(f"Kokoro root not found: {root}")

    health: dict[str, Any]
    try:
        health = KokoroBackend(args.endpoint).health()
        if not health.get("healthy"):
            failures.append("Kokoro endpoint did not report healthy")
    except Exception as exc:
        health = {"healthy": False, "error": str(exc)}
        failures.append(f"Kokoro endpoint unavailable: {exc}")

    git = _git_snapshot(root) if root.is_dir() else {"available": False}
    files = _important_files(root) if root.is_dir() else []
    if root.is_dir() and not git.get("available"):
        failures.append("Kokoro root is not an attestable Git checkout")
    if root.is_dir() and not files:
        failures.append("No recognized Kokoro startup/dependency files were found")

    payload = {
        "schema_version": 1,
        "captured_at": datetime.now().astimezone().isoformat(),
        "root": str(root),
        "endpoint": args.endpoint,
        "host_python": platform.python_version(),
        "platform": platform.platform(),
        "health": health,
        "git": git,
        "important_files": files,
        "gpu": _gpu_snapshot(),
        "complete": not failures,
        "failures": failures,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"ok": not failures or not args.require_complete, "output": str(output), "complete": not failures, "failures": failures}, indent=2))
    return 1 if args.require_complete and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
