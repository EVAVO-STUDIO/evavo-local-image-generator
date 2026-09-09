#!/usr/bin/env python3
"""Compatibility setup entry point for the current EVAVO production runtime.

Historical versions rewrote repository files with stale MCP/multimodal setup
content. This script is now non-destructive and delegates to the canonical
Windows updater or cross-platform verifier/agent doctor.
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
    parser = argparse.ArgumentParser(description="Set up the current EVAVO native image-generation runtime")
    parser.add_argument("--verify-only", action="store_true", help="Run verification only; do not repair/provision the image runtime")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    print("setup-production.py is a compatibility shim; it no longer rewrites repository files.")

    if os.name == "nt" and not args.verify_only and not args.json:
        updater = ROOT / "UPDATE-AND-VERIFY-EVAVO.ps1"
        powershell = "powershell.exe"
        return run([powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(updater)])

    verify_command = [sys.executable, str(ROOT / "evavo.py"), "verify", "--full"]
    if os.name == "nt":
        verify_command.append("--require-powershell")
    if args.json:
        verify_command.append("--json")
    code = run(verify_command)
    if code != 0 or args.verify_only:
        return code

    doctor_command = [sys.executable, str(ROOT / "agent-doctor.py"), "--repair", "--provision", "--skip-tests"]
    if args.json:
        doctor_command.append("--json")
    return run(doctor_command)


if __name__ == "__main__":
    raise SystemExit(main())
