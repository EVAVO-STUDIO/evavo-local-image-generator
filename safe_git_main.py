#!/usr/bin/env python3
"""Compatibility CLI for the authoritative :mod:`safe_main_git` helper.

Historical callers used ``safe_git_main.py [message] [--no-push|--status-only]``.
The implementation now delegates every mutation/safety decision to
``safe_main_git.py`` so there is exactly one Git authority in this repository.
"""

from __future__ import annotations

import argparse
import sys

import safe_main_git


def main() -> int:
    parser = argparse.ArgumentParser(description="Compatibility wrapper for safe_main_git.py")
    parser.add_argument("message", nargs="?", default=safe_main_git.DEFAULT_MESSAGE)
    parser.add_argument("--no-push", action="store_true", help="Create the commit but do not push it")
    parser.add_argument("--status-only", action="store_true", help="Validate repository/remote state without staging or committing")
    args = parser.parse_args()

    forwarded = ["safe_main_git.py", "--message", args.message]
    if args.no_push:
        forwarded.append("--no-push")
    if args.status_only:
        forwarded.append("--dry-run")

    previous = sys.argv
    try:
        sys.argv = forwarded
        return safe_main_git.main()
    finally:
        sys.argv = previous


if __name__ == "__main__":
    raise SystemExit(main())
