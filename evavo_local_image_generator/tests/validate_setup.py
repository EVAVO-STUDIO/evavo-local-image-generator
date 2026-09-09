"""Compatibility entry point for EVAVO repository/setup validation.

The authoritative validation implementation lives at ``verify-evavo.py``. This
wrapper exists so older package-oriented commands continue to work without
maintaining a second, stale definition of production readiness.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERIFIER = ROOT / "verify-evavo.py"


def main() -> int:
    if not VERIFIER.is_file():
        print(f"ERROR: authoritative verifier is missing: {VERIFIER}", file=sys.stderr)
        return 2
    arguments = sys.argv[1:]
    if not arguments:
        arguments = ["--full"]
        if sys.platform.startswith("win"):
            arguments.append("--require-powershell")
    return subprocess.run([sys.executable, str(VERIFIER), *arguments], cwd=str(ROOT)).returncode


if __name__ == "__main__":
    raise SystemExit(main())
