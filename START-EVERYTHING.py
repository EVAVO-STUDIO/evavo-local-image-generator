#!/usr/bin/env python3
"""Compatibility startup shim for the canonical EVAVO image runtime."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run(script: str, *args: str) -> int:
    return subprocess.run([sys.executable, str(ROOT / script), *args], cwd=str(ROOT)).returncode


def main() -> int:
    print("START-EVERYTHING.py is a compatibility shim; using canonical EVAVO lifecycle.")
    code = run("agent-doctor.py", "--repair", "--provision", "--skip-tests")
    if code != 0:
        return code
    return run("evavo.py", "status")


if __name__ == "__main__":
    raise SystemExit(main())
