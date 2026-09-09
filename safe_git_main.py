#!/usr/bin/env python3
"""Safe local Git helper for EVAVO main-branch commits.

This compatibility helper exists because the repository historically accumulated
multiple scripts that deleted Git locks, recreated repositories, staged stale
artifacts, or used hard-coded misleading commit messages. This implementation:

- operates only on branch ``main``;
- never deletes lock files or rewrites ``.git``;
- never force-pushes;
- fetches ``origin/main`` before mutating the index;
- refuses divergent/ahead-remote states instead of guessing a merge strategy;
- stages with ``git add -A`` only after synchronization safety checks;
- accepts a normal commit message argument;
- pushes only with a normal ``git push origin main``.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parent


class GitFailure(RuntimeError):
    pass


def run(args: Sequence[str], *, capture: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(ROOT),
            capture_output=capture,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitFailure(f"git {' '.join(args)} failed to execute: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise GitFailure(f"git {' '.join(args)} failed: {detail or f'exit {result.returncode}'}")
    return result


def value(*args: str) -> str:
    return run(args).stdout.strip()


def is_ancestor(older: str, newer: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", older, newer],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    detail = (result.stderr or result.stdout or "").strip()
    raise GitFailure(f"git merge-base --is-ancestor failed: {detail or result.returncode}")


def ensure_repository() -> None:
    if not (ROOT / ".git").exists():
        raise GitFailure(f"not a Git worktree: {ROOT}")
    branch = value("branch", "--show-current")
    if branch != "main":
        raise GitFailure(f"refusing to commit/push from branch {branch or '<detached>'}; expected main")


def ensure_remote_safe() -> tuple[str, str]:
    run(["fetch", "origin", "main"])
    local = value("rev-parse", "HEAD")
    remote = value("rev-parse", "origin/main")
    if local == remote:
        return local, remote
    if is_ancestor(remote, local):
        # Local already contains remote and may simply be ahead.
        return local, remote
    if is_ancestor(local, remote):
        raise GitFailure(
            "origin/main is ahead of the local checkout. Pull/fast-forward before committing local changes; "
            "this helper will not merge or rebase a dirty worktree automatically."
        )
    raise GitFailure("local main and origin/main have diverged; manual reconciliation is required before any push")


def status_porcelain() -> str:
    return value("status", "--porcelain")


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely commit and push the current EVAVO worktree to origin/main")
    parser.add_argument("message", nargs="?", default="chore: update EVAVO local image generator")
    parser.add_argument("--no-push", action="store_true", help="Create the commit but do not push it")
    parser.add_argument("--status-only", action="store_true", help="Only perform repository/remote safety checks and print status")
    args = parser.parse_args()

    try:
        ensure_repository()
        local_before, remote_before = ensure_remote_safe()
        dirty = status_porcelain()

        if args.status_only:
            print(f"branch: main")
            print(f"local:  {local_before}")
            print(f"remote: {remote_before}")
            print("worktree: dirty" if dirty else "worktree: clean")
            return 0

        if dirty:
            run(["add", "-A"])
            staged = value("diff", "--cached", "--name-only")
            if not staged:
                print("No staged changes after git add -A; nothing to commit.")
            else:
                run(["commit", "-m", args.message])
                print(value("log", "-1", "--oneline"))
        else:
            print("Working tree is clean; no new commit required.")

        if args.no_push:
            return 0

        # Re-fetch immediately before push and prove remote is still contained in
        # local HEAD. This catches a concurrent remote update without force.
        run(["fetch", "origin", "main"])
        local_now = value("rev-parse", "HEAD")
        remote_now = value("rev-parse", "origin/main")
        if local_now != remote_now and not is_ancestor(remote_now, local_now):
            raise GitFailure("origin/main changed during this operation; refusing to push a non-fast-forward update")
        if local_now == remote_now:
            print("origin/main is already up to date.")
            return 0
        run(["push", "origin", "main"], capture=False)
        print("Successfully pushed a fast-forward update to origin/main.")
        return 0
    except GitFailure as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
