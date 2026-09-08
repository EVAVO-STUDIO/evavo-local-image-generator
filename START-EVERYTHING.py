#!/usr/bin/env python3
"""Compatibility startup shim.

This filename is retained for old shortcuts. The former implementation opened
new consoles, hardcoded C:\\AI\\ComfyUI, used obsolete endpoints and launched
legacy autonomous generation. All lifecycle ownership now belongs to evavo.py
and agent-doctor.py.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run(script: str, *args: str) -> int:
    return subprocess.run([sys.executable, str(ROOT / script), *args], cwd=str(ROOT)).returncode


def main() -> int:
    print("START-EVERYTHING.py is a compatibility shim; using the canonical EVAVO lifecycle.")
    code = run("evavo.py", "start", "--no-mock")
    if code != 0:
        return code
    code = run("agent-doctor.py", "--repair", "--skip-tests")
    if code != 0:
        return code
    return run("evavo.py", "status")


if __name__ == "__main__":
    raise SystemExit(main())
