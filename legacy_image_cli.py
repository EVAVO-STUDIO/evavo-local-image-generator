#!/usr/bin/env python3
"""Shared compatibility CLI for historical EVAVO generation entry points.

All old runner/launcher filenames call this module so they cannot maintain their
own ComfyUI lifecycle, unrelated services, hardcoded storage paths, or implicit
sample generation. Verification/readiness and image generation are delegated to
the canonical EVAVO controller.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Sequence

ROOT = Path(__file__).resolve().parent
CONTROLLER = ROOT / "evavo.py"
DOCTOR = ROOT / "agent-doctor.py"


def _run(command: Sequence[str]) -> int:
    return subprocess.run(list(command), cwd=str(ROOT)).returncode


def _verify() -> int:
    command = [sys.executable, str(CONTROLLER), "verify", "--full"]
    if os.name == "nt":
        command.append("--require-powershell")
    return _run(command)


def _repair() -> int:
    return _run([sys.executable, str(DOCTOR), "--repair", "--provision", "--skip-tests"])


def compatibility_main(
    *,
    default_project: str,
    description: str,
    verify_first: bool = False,
    repair_first: bool = False,
) -> int:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--prompts", nargs="+")
    parser.add_argument("--examples", action="store_true")
    parser.add_argument("--project", default=default_project)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8188")
    parser.add_argument("--output-dir")
    parser.add_argument("--workflow")
    parser.add_argument("--no-wait", action="store_true")
    parser.add_argument("--verify", action="store_true", help="Run authoritative full repository verification first")
    parser.add_argument("--repair", action="store_true", help="Run strict image-runtime repair/readiness first")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if not CONTROLLER.is_file() or not DOCTOR.is_file():
        print("ERROR: canonical EVAVO controller/doctor is missing.", file=sys.stderr)
        return 2
    if args.concurrency < 1 or args.concurrency > 16:
        parser.error("--concurrency must be between 1 and 16")

    generation_requested = bool(args.prompts or args.examples)
    explicit_maintenance = bool(args.verify or args.repair)
    if not generation_requested and not explicit_maintenance:
        parser.error("provide --prompts or explicit --examples; legacy launchers no longer start surprise generation or provisioning jobs")

    if verify_first or args.verify:
        code = _verify()
        if code != 0:
            return code
    if repair_first or args.repair:
        code = _repair()
        if code != 0:
            return code

    if not generation_requested:
        print("EVAVO verification/readiness completed. No image generation was requested.")
        return 0

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
    return _run(command)


if __name__ == "__main__":
    raise SystemExit(
        compatibility_main(
            default_project="legacy-generation",
            description="Run explicit real EVAVO native image generation through the canonical compatibility CLI",
        )
    )
