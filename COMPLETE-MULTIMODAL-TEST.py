#!/usr/bin/env python3
"""Compatibility capability report for the historical multimodal test filename.

This repository's verified production contract is local **image generation**.
Older versions of this file printed aspirational multimodal claims without
executing those systems. It now reports the real boundary and can invoke the
authoritative repository verifier on request.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parent


def capability_report() -> Dict[str, Any]:
    return {
        "ok": True,
        "repository": "evavo-local-image-generator",
        "production_contract": "native local image generation",
        "capabilities": {
            "image": {
                "status": "implemented",
                "backend": "native-comfyui",
                "interfaces": ["CLI", "Python wrapper", "MCP v2 stdio", "MCP v2 Streamable HTTP", "loopback HTTP gateway"],
            },
            "video": {"status": "not_implemented", "reason": "not part of the verified image-generator runtime"},
            "audio": {"status": "not_implemented", "reason": "not part of the verified image-generator runtime"},
            "3d": {"status": "not_implemented", "reason": "not part of the verified image-generator runtime"},
            "text": {"status": "out_of_scope", "reason": "use a dedicated text/LLM system rather than this image repository"},
            "particles": {"status": "out_of_scope", "reason": "belongs in dedicated asset/game tooling"},
            "textures": {"status": "out_of_scope", "reason": "belongs in texture-studio rather than this image repository"},
        },
        "verification_command": "python evavo.py verify --full",
        "generation_command": "python evavo.py generate --prompts \"your prompt\" --project demo --wait",
        "agent_runbook": "AGENT-INTEGRATION.md",
    }


def run_verifier(json_output: bool) -> int:
    command = [sys.executable, str(ROOT / "evavo.py"), "verify", "--full"]
    if os.name == "nt":
        command.append("--require-powershell")
    if json_output:
        command.append("--json")
    return subprocess.run(command, cwd=str(ROOT)).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Report the truthful EVAVO image-generator capability boundary")
    parser.add_argument("--verify", action="store_true", help="Run the authoritative full verifier after printing/reporting capabilities")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = capability_report()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("EVAVO Local Image Generator capability report")
        print("=" * 72)
        for name, details in report["capabilities"].items():
            print(f"{name:12} {details['status']:16} {details.get('reason', details.get('backend', ''))}")
        print("=" * 72)
        print("Historical multimodal production-ready claims from this filename are retired.")
        print(f"Verify:   {report['verification_command']}")
        print(f"Generate: {report['generation_command']}")

    if args.verify:
        return run_verifier(args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
