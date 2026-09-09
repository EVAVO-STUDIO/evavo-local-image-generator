#!/usr/bin/env python3
"""Compatibility automation entry point for the current EVAVO image runtime.

Historical versions launched ComfyUI/Ollama/Kokoro consoles, ran an unverified
multimodal suite and copied folders to a hardcoded BeeStation path. This version
has no independent service graph: it delegates verification/readiness/generation
to the canonical EVAVO controller and only generates when explicitly requested.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parent
CONTROLLER = ROOT / "evavo.py"
DOCTOR = ROOT / "agent-doctor.py"


def run(command: List[str]) -> int:
    return subprocess.run(command, cwd=str(ROOT)).returncode


def verify() -> int:
    command = [sys.executable, str(CONTROLLER), "verify", "--full"]
    if os.name == "nt":
        command.append("--require-powershell")
    return run(command)


def ensure_ready() -> int:
    return run([sys.executable, str(DOCTOR), "--repair", "--provision", "--skip-tests"])


def generate(args: argparse.Namespace) -> int:
    if not args.prompts and not args.examples:
        print("ERROR: generation requires --prompts or explicit --examples; no surprise generation is started.", file=sys.stderr)
        return 2
    command: List[str] = [
        sys.executable,
        str(CONTROLLER),
        "generate",
        "--project",
        args.project,
        "--concurrency",
        str(args.concurrency),
        "--endpoint",
        args.endpoint,
    ]
    if args.prompts:
        command.extend(["--prompts", *args.prompts])
    else:
        command.append("--examples")
    if not args.no_wait:
        command.append("--wait")
    if args.output_dir:
        command.extend(["--output-dir", args.output_dir])
    if args.workflow:
        command.extend(["--workflow", args.workflow])
    if args.json:
        command.append("--json")
    return run(command)


def main() -> int:
    parser = argparse.ArgumentParser(description="EVAVO canonical image automation compatibility entry point")
    parser.add_argument("--mode", choices=["full", "test", "generate"], default="full")
    parser.add_argument("--prompts", nargs="+")
    parser.add_argument("--examples", action="store_true")
    parser.add_argument("--project", default="automation")
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8188")
    parser.add_argument("--output-dir")
    parser.add_argument("--workflow")
    parser.add_argument("--no-wait", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if not CONTROLLER.is_file() or not DOCTOR.is_file():
        print("ERROR: canonical EVAVO controller/doctor files are missing.", file=sys.stderr)
        return 2
    if args.concurrency < 1 or args.concurrency > 16:
        parser.error("--concurrency must be between 1 and 16")

    if args.mode in {"full", "test"}:
        code = verify()
        if code != 0:
            return code
    if args.mode == "test":
        return 0

    if args.mode == "full":
        code = ensure_ready()
        if code != 0:
            return code
        if not args.prompts and not args.examples:
            print("EVAVO verified and real image backend ready. No generation requested.")
            return 0

    return generate(args)


if __name__ == "__main__":
    raise SystemExit(main())
