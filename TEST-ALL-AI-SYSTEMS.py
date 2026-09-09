#!/usr/bin/env python3
"""Compatibility verifier for the historical ``TEST-ALL-AI-SYSTEMS.py`` name.

This image-generator repository no longer treats Ollama, Kokoro or aspirational
multimodal adapters as production dependencies. Repository correctness belongs
to ``verify-evavo.py``; real image-runtime readiness belongs to
``agent-doctor.py``.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent


def run(command: List[str]) -> int:
    return subprocess.run(command, cwd=str(ROOT)).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the current EVAVO image-generation system")
    parser.add_argument("--structural-only", action="store_true", help="Run repository verification without checking a live renderer")
    parser.add_argument("--repair", action="store_true", help="Allow agent doctor to repair/provision the local image runtime")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    verify_command = [sys.executable, str(ROOT / "evavo.py"), "verify", "--full"]
    if os.name == "nt":
        verify_command.append("--require-powershell")
    if args.json:
        verify_command.append("--json")
    verify_code = run(verify_command)
    if verify_code != 0 or args.structural_only:
        return verify_code

    doctor_command = [sys.executable, str(ROOT / "agent-doctor.py")]
    if args.repair:
        doctor_command.extend(["--repair", "--provision", "--skip-tests"])
    if args.json:
        doctor_command.append("--json")
    return run(doctor_command)


if __name__ == "__main__":
    raise SystemExit(main())
