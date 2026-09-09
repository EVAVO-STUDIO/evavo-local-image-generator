#!/usr/bin/env python3
"""Compatibility entry point for the historical production-package generator.

Older revisions recreated obsolete package files, including the deleted fake MCP
server and fake multimodal generators. This script is now strictly
non-destructive: it verifies the current repository and optionally repairs the
real native image runtime.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parent


def run(command: List[str]) -> int:
    return subprocess.run(command, cwd=str(ROOT)).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the current EVAVO production package without rewriting source files")
    parser.add_argument("--repair", action="store_true", help="Also run strict native image-runtime repair/provisioning")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    print("create-complete-production.py is a compatibility shim; source regeneration has been retired.")

    command = [sys.executable, str(ROOT / "evavo.py"), "verify", "--full"]
    if os.name == "nt":
        command.append("--require-powershell")
    if args.json:
        command.append("--json")
    code = run(command)
    if code != 0 or not args.repair:
        return code

    doctor = [sys.executable, str(ROOT / "agent-doctor.py"), "--repair", "--provision", "--skip-tests"]
    if args.json:
        doctor.append("--json")
    return run(doctor)


if __name__ == "__main__":
    raise SystemExit(main())
