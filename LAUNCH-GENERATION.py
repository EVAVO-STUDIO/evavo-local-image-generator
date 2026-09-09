#!/usr/bin/env python3
"""Compatibility launcher for explicit EVAVO image generation.

This file no longer launches hardcoded ComfyUI/Ollama processes or claims
multimodal outputs. It delegates readiness and generation to the canonical
controller/agent doctor.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parent
CONTROLLER = ROOT / "evavo.py"
DOCTOR = ROOT / "agent-doctor.py"


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch the canonical EVAVO native image pipeline")
    parser.add_argument("--prompts", nargs="+")
    parser.add_argument("--examples", action="store_true")
    parser.add_argument("--project", default="launch-generation")
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8188")
    parser.add_argument("--output-dir")
    parser.add_argument("--workflow")
    parser.add_argument("--no-wait", action="store_true")
    parser.add_argument("--skip-ready-check", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if not args.prompts and not args.examples:
        parser.error("provide --prompts or explicit --examples; this launcher no longer starts sample/multimodal generation automatically")
    if args.concurrency < 1 or args.concurrency > 16:
        parser.error("--concurrency must be between 1 and 16")

    if not args.skip_ready_check:
        ready = subprocess.run(
            [sys.executable, str(DOCTOR), "--repair", "--provision", "--skip-tests"],
            cwd=str(ROOT),
        )
        if ready.returncode != 0:
            return ready.returncode

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
    return subprocess.run(command, cwd=str(ROOT)).returncode


if __name__ == "__main__":
    raise SystemExit(main())
