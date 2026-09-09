#!/usr/bin/env python3
"""Static safety gate for EVAVO Git/commit/push helper scripts."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPT_SUFFIXES = {".py", ".ps1", ".bat", ".cmd", ".sh"}
NAME_TOKENS = ("git", "commit", "push")
AUTHORITATIVE = ROOT / "safe_main_git.py"
COMPATIBILITY = ROOT / "safe_git_main.py"

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
        if not stripped or stripped.startswith("#") or stripped.startswith("::") or lower.startswith("rem "):
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
    for required in (AUTHORITATIVE, COMPATIBILITY):
        if required.is_file() and required not in result:
            result.append(required)
    return sorted(result)


class GitMaintenanceSafetyTests(unittest.TestCase):
    def test_single_authoritative_helper_and_compatibility_adapter_exist(self) -> None:
        self.assertTrue(AUTHORITATIVE.is_file())
        self.assertTrue(COMPATIBILITY.is_file())
        compatibility = COMPATIBILITY.read_text(encoding="utf-8")
        self.assertIn("import safe_main_git", compatibility)
        self.assertIn("safe_main_git.main()", compatibility)
        self.assertNotIn('run(["add", "-A"]', compatibility)
        self.assertNotIn('subprocess.run(\n            ["git"', compatibility)

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

    def test_authoritative_helper_is_main_origin_and_verifier_guarded(self) -> None:
        source = AUTHORITATIVE.read_text(encoding="utf-8")
        self.assertIn('branch != "main"', source)
        self.assertIn("EXPECTED_ORIGIN_RE", source)
        self.assertIn('rev-list", "--left-right", "--count", "HEAD...origin/main"', source)
        self.assertIn('push", "origin", "main:main"', source)
        self.assertIn('"verify", "--full"', source)
        self.assertIn("_assert_safe_changes", source)
        self.assertIn(".evavo/", source)
        self.assertNotIn("push --force", source)
        self.assertNotIn("reset --hard", source)
        self.assertNotIn("clean -fd", source)
        self.assertNotIn("shell=True", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
