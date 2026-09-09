#!/usr/bin/env python3
"""Stdlib-only bootstrap into EVAVO's repository-local MCP runtime.

The canonical workstation updater installs dependencies only into ``.venv``.
Project-level MCP clients may initially invoke this file with any Python 3.10+
that can run the standard library; the bootstrap then replaces itself with the
repository-local venv interpreter and the policy-validated MCP production entry.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(os.path.normpath(str(left))) == os.path.normcase(os.path.normpath(str(right)))


def _venv_python() -> Path:
    venv = ROOT / ".venv"
    if venv.is_symlink():
        raise RuntimeError(f"MCP_BOOTSTRAP_INVALID_VENV:.venv must not be a symlink: {venv}")
    candidates = (
        venv / "Scripts" / "python.exe",
        venv / "bin" / "python",
    )
    for candidate in candidates:
        if candidate.is_symlink():
            raise RuntimeError(f"MCP_BOOTSTRAP_INVALID_VENV:venv Python must not be a symlink: {candidate}")
        if not candidate.is_file():
            continue
        resolved = candidate.resolve(strict=True)
        if not _same_path(candidate.absolute(), resolved):
            raise RuntimeError(f"MCP_BOOTSTRAP_INVALID_VENV:venv Python traverses a redirected path: {candidate}")
        return resolved
    raise RuntimeError(
        "MCP_BOOTSTRAP_VENV_MISSING:repository .venv Python was not found; run UPDATE-AND-VERIFY-EVAVO.ps1 first"
    )


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
