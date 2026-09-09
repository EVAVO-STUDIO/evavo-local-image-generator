#!/usr/bin/env python3
"""Safe local Git commit/push helper for EVAVO repository maintenance.

This helper deliberately refuses repository surgery. It never deletes Git lock
files, rewrites .git, force-pushes, creates remotes, changes Git identity, or
tries to resolve divergent history automatically.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Sequence

ROOT = Path(__file__).resolve().parent
DEFAULT_MESSAGE = "chore(repo): update local EVAVO image-generator changes"

# Runtime/generated paths that should never be swept into a generic local commit.
# .evavo/capabilities.json is an intentional checked-in repository capability
# manifest; other .evavo files are runtime state and remain excluded.
FORBIDDEN_PREFIXES = (
    ".git/",
    ".git.",
    ".evavo/outputs/",
    ".evavo/logs/",
    ".evavo/gateway/",
    ".evavo/tools/",
    "evavo-images/",
    "evavo-videos/",
    "evavo-audio/",
    "evavo-text/",
    "evavo-particles/",
    "evavo-models/",
    "evavo-textures/",
    "evavo-generations/",
    "__pycache__/",
)
FORBIDDEN_NAMES = {
    "task_history.json",
    "task_history.json.lock",
    "ai-systems-test-results.json",
}
FORBIDDEN_SUFFIXES = (".log", ".pyc", ".pyo", ".part")


class GitSafetyError(RuntimeError):
    pass


def _git_executable() -> str:
    executable = shutil.which("git")
    if not executable:
        raise GitSafetyError("git executable was not found on PATH")
    return executable


def _run(args: Sequence[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        [_git_executable(), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if check and completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise GitSafetyError(f"git {' '.join(args)} failed: {detail or f'exit {completed.returncode}'}")
    return completed


def _lines(args: Sequence[str]) -> list[str]:
    return [line.strip() for line in _run(args).stdout.splitlines() if line.strip()]


def _assert_repository() -> None:
    actual = Path(_run(["rev-parse", "--show-toplevel"]).stdout.strip()).resolve()
    if os.path.normcase(str(actual)) != os.path.normcase(str(ROOT.resolve())):
        raise GitSafetyError(f"script root is not the active Git worktree root: {actual}")
    branch = _run(["branch", "--show-current"]).stdout.strip()
    if branch != "main":
        raise GitSafetyError(f"refusing commit/push from branch {branch!r}; checkout main first")
    remote = _run(["remote", "get-url", "origin"]).stdout.strip()
    if not remote:
        raise GitSafetyError("origin remote is not configured")


def _refresh_origin() -> tuple[int, int]:
    _run(["fetch", "--quiet", "origin", "main"])
    raw = _run(["rev-list", "--left-right", "--count", "HEAD...origin/main"]).stdout.strip().split()
    if len(raw) != 2:
        raise GitSafetyError("could not determine main/origin-main divergence")
    ahead, behind = int(raw[0]), int(raw[1])
    if behind:
        if ahead:
            raise GitSafetyError(
                f"main has diverged from origin/main (ahead {ahead}, behind {behind}); resolve it manually without force-pushing"
            )
        raise GitSafetyError(
            f"local main is behind origin/main by {behind} commit(s); update with git pull --ff-only origin main before committing"
        )
    return ahead, behind


def _status_paths() -> list[str]:
    completed = _run(["status", "--porcelain=v1", "-z", "--untracked-files=all"])
    records = completed.stdout.split("\0")
    paths: list[str] = []
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue
        if len(record) < 4:
            continue
        status = record[:2]
        path = record[3:]
        # Rename/copy records include a second NUL-separated path. The first path
        # is still safety-checked, then the destination is checked as well.
        paths.append(path.replace("\\", "/"))
        if "R" in status or "C" in status:
            if index < len(records) and records[index]:
                paths.append(records[index].replace("\\", "/"))
                index += 1
    return paths


def _forbidden_path(path: str) -> bool:
    normalized = path.strip().replace("\\", "/").lstrip("./")
    lowered = normalized.lower()
    if lowered == ".evavo/capabilities.json":
        return False
    if any(lowered.startswith(prefix.lower()) for prefix in FORBIDDEN_PREFIXES):
        return True
    if Path(lowered).name in FORBIDDEN_NAMES:
        return True
    return lowered.endswith(tuple(item.lower() for item in FORBIDDEN_SUFFIXES))


def _assert_safe_changes(paths: Iterable[str]) -> list[str]:
    unique = sorted({path for path in paths if path})
    unsafe = [path for path in unique if _forbidden_path(path)]
    if unsafe:
        raise GitSafetyError(
            "refusing generic commit because runtime/generated paths changed: " + ", ".join(unsafe[:30])
        )
    return unique


def _run_verifier(skip_verify: bool) -> None:
    if skip_verify:
        return
    command = [sys.executable, str(ROOT / "evavo.py"), "verify", "--full"]
    if os.name == "nt":
        command.append("--require-powershell")
    completed = subprocess.run(command, cwd=str(ROOT), timeout=1800)
    if completed.returncode != 0:
        raise GitSafetyError(f"authoritative EVAVO verification failed with exit {completed.returncode}")


def _stage_and_commit(message: str, paths: list[str]) -> str | None:
    if not paths:
        print("Working tree is clean; nothing to commit.")
        return None
    _run(["add", "-A", "--", "."])
    staged = _lines(["diff", "--cached", "--name-only", "--diff-filter=ACDMRTUXB"])
    _assert_safe_changes(staged)
    if not staged:
        print("No staged changes remain; nothing to commit.")
        return None
    _run(["commit", "-m", message])
    return _run(["rev-parse", "HEAD"]).stdout.strip()


def _push_and_verify(commit_sha: str) -> None:
    # A normal push will safely reject concurrent remote updates. Force variants
    # are intentionally never used here.
    _run(["push", "origin", "main:main"])
    _run(["fetch", "--quiet", "origin", "main"])
    remote_sha = _run(["rev-parse", "origin/main"]).stdout.strip()
    if remote_sha != commit_sha:
        raise GitSafetyError(f"origin/main verification mismatch: local={commit_sha} remote={remote_sha}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely verify, commit and optionally push EVAVO changes on main")
    parser.add_argument("--message", default=DEFAULT_MESSAGE, help="Commit message")
    parser.add_argument("--no-push", action="store_true", help="Create the commit but do not push it")
    parser.add_argument("--skip-verify", action="store_true", help="Skip the authoritative full verifier")
    parser.add_argument("--dry-run", action="store_true", help="Validate Git state and list changes without staging/committing")
    args = parser.parse_args()

    try:
        _assert_repository()
        ahead, _ = _refresh_origin()
        paths = _assert_safe_changes(_status_paths())
        print(f"main is {ahead} commit(s) ahead of origin/main before local changes; changed paths: {len(paths)}")
        for path in paths[:100]:
            print(f"  {path}")
        if len(paths) > 100:
            print(f"  ... {len(paths) - 100} more")
        if args.dry_run:
            return 0
        if not paths:
            return 0
        _run_verifier(args.skip_verify)
        commit_sha = _stage_and_commit(args.message.strip() or DEFAULT_MESSAGE, paths)
        if not commit_sha:
            return 0
        print(f"Created commit {commit_sha}")
        if args.no_push:
            print("Push skipped by request.")
            return 0
        _push_and_verify(commit_sha)
        print(f"Verified origin/main at {commit_sha}")
        return 0
    except (GitSafetyError, OSError, subprocess.TimeoutExpired, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
