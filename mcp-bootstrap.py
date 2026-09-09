#!/usr/bin/env python3
"""Stdlib-only bootstrap into EVAVO's repository-local MCP runtime.

The canonical workstation updater installs dependencies only into ``.venv``.
Project-level MCP clients may initially invoke this file with any Python 3.10+
that can run the standard library; the bootstrap validates the same repository
venv authority as setup, then replaces itself with that interpreter and the
policy-validated MCP production entry.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from evavo_venv import inspect_venv

ROOT = Path(__file__).resolve().parent


def _venv_python() -> Path:
    result = inspect_venv(ROOT / ".venv")
    if not result.get("ok"):
        status = str(result.get("status") or "invalid")
        detail = str(result.get("message") or "repository .venv is not ready")
        code = "MCP_BOOTSTRAP_VENV_MISSING" if status == "missing" else "MCP_BOOTSTRAP_INVALID_VENV"
        raise RuntimeError(f"{code}:{detail}; run UPDATE-AND-VERIFY-EVAVO.ps1")
    raw = result.get("python")
    if not isinstance(raw, str) or not raw:
        raise RuntimeError("MCP_BOOTSTRAP_INVALID_VENV:validated venv did not return a Python path")
    return Path(raw)


def main() -> None:
    if sys.version_info < (3, 10):
        print("MCP_BOOTSTRAP_PYTHON:Python 3.10+ is required", file=sys.stderr)
        raise SystemExit(78)
    try:
        python = _venv_python()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(78) from exc

    # MCP hosts are not required to preserve the repository as their working
    # directory. Normalize it before `-m` so the local package and repo-owned
    # recovery/provision scripts remain discoverable regardless of caller cwd.
    os.chdir(ROOT)
    argv = [
        str(python),
        "-m",
        "evavo_local_image_generator.mcp_entry",
        *sys.argv[1:],
    ]
    os.execv(str(python), argv)


if __name__ == "__main__":
    main()
