#!/usr/bin/env python3
"""Stdlib-only EVAVO repository virtual-environment authority.

This module defines one fail-closed contract for ``<repo>/.venv`` so the
canonical Windows updater and project MCP bootstrap cannot disagree about which
Python runtime owns EVAVO's installed dependencies.

It never installs packages. ``--ensure`` may create a missing venv with a
caller-selected Python, but an existing malformed/redirected ``.venv`` is never
deleted or repaired implicitly.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parent
VENV_ROOT = ROOT / ".venv"
MIN_PYTHON = (3, 10)


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(os.path.normpath(str(left))) == os.path.normcase(os.path.normpath(str(right)))


def _ordinary_resolved(path: Path, *, label: str, directory: bool | None = None) -> Path:
    lexical = path.absolute()
    if lexical.is_symlink():
        raise RuntimeError(f"VENV_INVALID:{label} must not be a symlink: {lexical}")
    try:
        resolved = lexical.resolve(strict=True)
    except OSError as exc:
        raise RuntimeError(f"VENV_INVALID:{label} cannot be resolved: {lexical}:{exc}") from exc
    if not _same_path(lexical, resolved):
        raise RuntimeError(f"VENV_INVALID:{label} traverses a redirected path: {lexical}")
    if directory is True and not resolved.is_dir():
        raise RuntimeError(f"VENV_INVALID:{label} must be a directory: {resolved}")
    if directory is False and not resolved.is_file():
        raise RuntimeError(f"VENV_INVALID:{label} must be an ordinary file: {resolved}")
    return resolved


def _python_candidates(venv_root: Path) -> tuple[Path, ...]:
    return (venv_root / "Scripts" / "python.exe", venv_root / "bin" / "python")


def inspect_venv(root: Path = VENV_ROOT, *, probe: bool = True) -> dict[str, Any]:
    root = root.absolute()
    if not root.exists() and not root.is_symlink():
        return {"ok": False, "status": "missing", "venv": str(root), "python": None}

    try:
        resolved_root = _ordinary_resolved(root, label=".venv", directory=True)
        config = _ordinary_resolved(resolved_root / "pyvenv.cfg", label="pyvenv.cfg", directory=False)
    except RuntimeError as exc:
        return {"ok": False, "status": "invalid", "venv": str(root), "python": None, "message": str(exc)}

    python: Path | None = None
    errors: list[str] = []
    for candidate in _python_candidates(resolved_root):
        if not candidate.exists() and not candidate.is_symlink():
            continue
        try:
            python = _ordinary_resolved(candidate, label="venv Python", directory=False)
        except RuntimeError as exc:
            errors.append(str(exc))
            continue
        break
    if python is None:
        detail = "; ".join(errors) or "venv Python executable is missing"
        return {
            "ok": False,
            "status": "invalid",
            "venv": str(resolved_root),
            "python": None,
            "config": str(config),
            "message": f"VENV_INVALID:{detail}",
        }

    result: dict[str, Any] = {
        "ok": True,
        "status": "ready",
        "venv": str(resolved_root),
        "python": str(python),
        "config": str(config),
    }
    if not probe:
        return result

    code = (
        "import json,sys; "
        "print(json.dumps({'version':[sys.version_info.major,sys.version_info.minor,sys.version_info.micro],"
        "'executable':sys.executable,'prefix':sys.prefix,'base_prefix':sys.base_prefix}))"
    )
    try:
        completed = subprocess.run(
            [str(python), "-c", code],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {**result, "ok": False, "status": "invalid", "message": f"VENV_PROBE_FAILED:{exc}"}
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[-1200:]
        return {**result, "ok": False, "status": "invalid", "message": f"VENV_PROBE_FAILED:{detail or completed.returncode}"}
    try:
        probe_data = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {**result, "ok": False, "status": "invalid", "message": "VENV_PROBE_INVALID_JSON"}
    version = probe_data.get("version") if isinstance(probe_data, dict) else None
    if not isinstance(version, list) or len(version) < 2 or tuple(version[:2]) < MIN_PYTHON:
        return {
            **result,
            "ok": False,
            "status": "unsupported_python",
            "version": version,
            "message": f"VENV_PYTHON_TOO_OLD:Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ is required",
        }
    try:
        prefix = Path(str(probe_data.get("prefix"))).resolve(strict=True)
    except (OSError, TypeError):
        return {**result, "ok": False, "status": "invalid", "message": "VENV_PREFIX_INVALID"}
    if not _same_path(prefix, resolved_root):
        return {
            **result,
            "ok": False,
            "status": "invalid",
            "prefix": str(prefix),
            "message": f"VENV_PREFIX_MISMATCH:{prefix} != {resolved_root}",
        }
    return {**result, "version": version, "prefix": str(prefix), "base_prefix": probe_data.get("base_prefix")}


def ensure_venv(*, bootstrap_python: str | Path = sys.executable, root: Path = VENV_ROOT) -> dict[str, Any]:
    current = inspect_venv(root)
    if current.get("ok"):
        return {**current, "created": False}
    if current.get("status") != "missing":
        return {**current, "created": False}

    lexical_bootstrap = Path(str(bootstrap_python)).expanduser().absolute()
    if lexical_bootstrap.is_symlink():
        return {
            "ok": False,
            "status": "bootstrap_invalid",
            "venv": str(root.absolute()),
            "message": f"VENV_BOOTSTRAP_INVALID:bootstrap Python must not be a symlink: {lexical_bootstrap}",
        }
    try:
        bootstrap = lexical_bootstrap.resolve(strict=True)
    except OSError as exc:
        return {"ok": False, "status": "bootstrap_missing", "venv": str(root.absolute()), "message": f"VENV_BOOTSTRAP_MISSING:{exc}"}
    if not _same_path(lexical_bootstrap, bootstrap) or not bootstrap.is_file():
        return {
            "ok": False,
            "status": "bootstrap_invalid",
            "venv": str(root.absolute()),
            "message": f"VENV_BOOTSTRAP_INVALID:bootstrap Python traverses a redirected path or is not a file: {lexical_bootstrap}",
        }

    try:
        version_check = subprocess.run(
            [str(bootstrap), "-c", "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 2)"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "ok": False,
            "status": "bootstrap_probe_failed",
            "venv": str(root.absolute()),
            "message": f"VENV_BOOTSTRAP_PROBE_FAILED:{exc}",
        }
    if version_check.returncode != 0:
        detail = (version_check.stderr or version_check.stdout).strip()[-1200:]
        return {
            "ok": False,
            "status": "bootstrap_unsupported",
            "venv": str(root.absolute()),
            "message": f"VENV_BOOTSTRAP_PYTHON_TOO_OLD:{detail or version_check.returncode}",
        }

    try:
        created = subprocess.run(
            [str(bootstrap), "-m", "venv", str(root.absolute())],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "status": "create_failed", "venv": str(root.absolute()), "message": f"VENV_CREATE_FAILED:{exc}"}
    if created.returncode != 0:
        detail = (created.stderr or created.stdout).strip()[-2000:]
        return {"ok": False, "status": "create_failed", "venv": str(root.absolute()), "message": f"VENV_CREATE_FAILED:{detail or created.returncode}"}
    verified = inspect_venv(root)
    return {**verified, "created": bool(verified.get("ok"))}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate or create EVAVO's repository-local .venv without installing packages")
    parser.add_argument("--ensure", action="store_true", help="Create the venv only when it is completely missing")
    parser.add_argument("--bootstrap-python", default=sys.executable, help="Python used only to create a missing .venv")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = ensure_venv(bootstrap_python=args.bootstrap_python) if args.ensure else inspect_venv()
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"EVAVO venv: {result.get('status')}")
        if result.get("python"):
            print("Python:", result["python"])
        if result.get("message"):
            print("ERROR:", result["message"])
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
