#!/usr/bin/env python3
"""Static safety gate for EVAVO Git/commit/push helper scripts."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPT_SUFFIXES = {".py", ".ps1", ".bat", ".cmd", ".sh"}
NAME_TOKENS = ("git", "commit", "push")

# Match executable behavior, not explanatory comments. These operations are too
# destructive for an autonomous compatibility helper in this repository.
DANGEROUS = (
    re.compile(r"\bgit\s+push\b[^\n]*(?:--force(?:-with-lease)?|\s-f(?:\s|$))", re.I),
    re.compile(r"\bgit\s+reset\s+--hard\b", re.I),
    re.compile(r"\bgit\s+clean\s+-[^\n]*f", re.I),
    re.compile(r"\bgit\s+init\b", re.I),
    re.compile(r"(?:remove-item|rmdir|rm\s+-rf|shutil\.rmtree)[^\n]*(?:\\|/)\.git(?:\b|\\|/)", re.I),
    re.compile(r"(?:remove-item|del|rm\s+-f|unlink|os\.remove)[^\n]*\.git[^\n]*\.lock", re.I),
    re.compile(r"shell\s*=\s*true", re.I),
)


def active_source(path: Path) -> str:
    lines: list[str] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = raw.strip()
        lower = stripped.lower()
        if not stripped:
            continue
        if stripped.startswith("#") or stripped.startswith("::") or lower.startswith("rem "):
            continue
        lines.append(raw)
    return "\n".join(lines)


def git_helpers() -> list[Path]:
    result: list[Path] = []
    for path in ROOT.iterdir():
        if not path.is_file() or path.suffix.lower() not in SCRIPT_SUFFIXES:
            continue
        lower = path.name.lower()
        if any(token in lower for token in NAME_TOKENS):
            result.append(path)
    # The authoritative helper must always be part of the contract even though
    # a future rename could otherwise fall outside the filename heuristic.
    safe = ROOT / "safe_git_main.py"
    if safe.is_file() and safe not in result:
        result.append(safe)
    return sorted(result)


class GitMaintenanceSafetyTests(unittest.TestCase):
    def test_safe_main_helper_exists(self) -> None:
        self.assertTrue((ROOT / "safe_git_main.py").is_file())

    def test_git_helpers_contain_no_destructive_autonomous_operations(self) -> None:
        helpers = git_helpers()
        self.assertTrue(helpers, "no Git helper scripts discovered")
        failures: list[str] = []
        for path in helpers:
            source = active_source(path)
            for pattern in DANGEROUS:
                if pattern.search(source):
                    failures.append(f"{path.name}: {pattern.pattern}")
        self.assertEqual(failures, [], "destructive Git helper behavior found: " + " | ".join(failures))

    def test_safe_helper_is_main_only_and_normal_push_only(self) -> None:
        source = (ROOT / "safe_git_main.py").read_text(encoding="utf-8")
        self.assertIn('branch != "main"', source)
        self.assertIn('["push", "origin", "main"]', source)
        self.assertIn('["fetch", "origin", "main"]', source)
        self.assertIn("merge-base", source)
        self.assertNotIn("--force", source)
        self.assertNotIn("reset --hard", source)
        self.assertNotIn("clean -fd", source)
        self.assertNotIn("shell=True", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
