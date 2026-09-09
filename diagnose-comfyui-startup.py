#!/usr/bin/env python3
"""Run a bounded ComfyUI startup diagnostic and stream full output."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from evavo_local_image_generator.comfyui_runtime import diagnose_comfyui_startup


def _utf8_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def main() -> int:
    _utf8_console()
    parser = argparse.ArgumentParser(description="Capture ComfyUI startup output for a bounded diagnostic window")
    parser.add_argument("--seconds", type=float, default=60.0, help="Diagnostic window in seconds (default: 60)")
    parser.add_argument("--output", default="comfy-startup-output.txt", help="Output log path")
    parser.add_argument("--disable-all-custom-nodes", action="store_true", help="Repeat the probe with all custom nodes disabled")
    parser.add_argument("--no-cpu", action="store_true", help="Do not add ComfyUI --cpu")
    args = parser.parse_args()

    result = diagnose_comfyui_startup(
        seconds=args.seconds,
        cpu=not args.no_cpu,
        disable_all_custom_nodes=args.disable_all_custom_nodes,
        output_file=Path(args.output),
        stream_callback=lambda line: print(line, flush=True),
    )
    print(json.dumps({key: value for key, value in result.items() if key != "log_tail"}, indent=2, ensure_ascii=False), flush=True)
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
