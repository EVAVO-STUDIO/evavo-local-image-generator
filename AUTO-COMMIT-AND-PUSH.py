#!/usr/bin/env python3
"""Compatibility entry point for safe EVAVO main-branch commits.

The historical implementation deleted Git lock files, used shell command
interpolation, staged everything blindly and embedded obsolete multimodal commit
claims. All Git mutation now lives in safe_main_git.py.
"""

from __future__ import annotations

from safe_main_git import main


if __name__ == "__main__":
    raise SystemExit(main())
