#!/usr/bin/env python3
"""Offline regression tests for EVAVO Git maintenance safety."""

from __future__ import annotations

import unittest
from pathlib import Path

import safe_main_git

ROOT = Path(__file__).resolve().parent

GIT_COMPAT_FILES = (
    "AUTO-COMMIT-AND-PUSH.py",
    "COMMIT-UPGRADE.ps1",
    "COMMIT_AND_PUSH.ps1",
    "PUSH-UPGRADE-TO-MAIN.ps1",
    "COMPLETE_EVAVO_GIT_COMMIT.ps1",
    "create_github_repo.ps1",
    "DO-THIS-TO-COMMIT.txt",
)


class SafeMainGitTests(unittest.TestCase):
    def test_runtime_and_generated_paths_are_rejected(self) -> None:
        for path in (
            ".git/index.lock",
            "./.git/index.lock",
            ".git.backup/HEAD",
            ".evavo/operations-service.json",
            ".evavo/chatgpt-tunnel.json",
            ".evavo/outputs/test.png",
            ".evavo/logs/service.log",
            "evavo-images/image.png",
            "evavo-videos/demo.mp4",
            "task_history.json",
            "task_history.json.lock",
            "__pycache__/x.pyc",
            "service.log",
        ):
            with self.subTest(path=path):
                self.assertTrue(safe_main_git._forbidden_path(path))

    def test_capability_manifest_and_normal_source_are_allowed(self) -> None:
        self.assertFalse(safe_main_git._forbidden_path(".evavo/capabilities.json"))
        self.assertFalse(safe_main_git._forbidden_path("./.evavo/capabilities.json"))
        self.assertFalse(safe_main_git._forbidden_path("evavo.py"))
        self.assertFalse(safe_main_git._forbidden_path("README.md"))

    def test_expected_origin_identity_accepts_https_and_ssh_only_for_this_repo(self) -> None:
        accepted = (
            "https://github.com/EVAVO-STUDIO/evavo-local-image-generator.git",
            "https://github.com/EVAVO-STUDIO/evavo-local-image-generator",
            "git@github.com:EVAVO-STUDIO/evavo-local-image-generator.git",
            "ssh://git@github.com/EVAVO-STUDIO/evavo-local-image-generator.git",
        )
        for remote in accepted:
            with self.subTest(remote=remote):
                self.assertIsNotNone(safe_main_git.EXPECTED_ORIGIN_RE.search(remote))
        for remote in (
            "https://github.com/someone/evavo-local-image-generator.git",
            "https://github.com/EVAVO-STUDIO/another-repo.git",
        ):
            with self.subTest(remote=remote):
                self.assertIsNone(safe_main_git.EXPECTED_ORIGIN_RE.search(remote))

    def test_helper_has_no_destructive_git_repair_commands(self) -> None:
        source = (ROOT / "safe_main_git.py").read_text(encoding="utf-8").lower()
        forbidden = (
            "git init",
            "--force",
            "push --force",
            "remove-item .git",
            "rmtree(root / '.git')",
        )
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_helper_requires_main_and_origin_divergence_check(self) -> None:
        source = (ROOT / "safe_main_git.py").read_text(encoding="utf-8")
        self.assertIn('branch != "main"', source)
        self.assertIn('remote", "get-url", "origin"', source)
        self.assertIn("EXPECTED_ORIGIN_RE", source)
        self.assertIn('rev-list", "--left-right", "--count", "HEAD...origin/main"', source)
        self.assertIn('push", "origin", "main:main"', source)
        self.assertIn('rev-parse", "origin/main"', source)

    def test_historical_git_entry_points_delegate_or_validate_read_only(self) -> None:
        expected = {
            "AUTO-COMMIT-AND-PUSH.py": "safe_main_git",
            "COMMIT-UPGRADE.ps1": "safe_main_git.py",
            "COMMIT_AND_PUSH.ps1": "safe_main_git.py",
            "PUSH-UPGRADE-TO-MAIN.ps1": "safe_main_git.py",
            "COMPLETE_EVAVO_GIT_COMMIT.ps1": "safe_main_git.py",
            "create_github_repo.ps1": "remote get-url origin",
            "DO-THIS-TO-COMMIT.txt": "safe_main_git.py",
        }
        for name, marker in expected.items():
            source = (ROOT / name).read_text(encoding="utf-8")
            with self.subTest(name=name):
                self.assertIn(marker, source)

    def test_historical_git_entry_points_do_not_restore_old_mutation_paths(self) -> None:
        forbidden_active = (
            "Remove-Item \".git\\index.lock\"",
            "Remove-Item -Path .\\.git",
            "git init --initial-branch=main",
            "git config user.name",
            "git config user.email",
            "tar -xzf evavo-upgrade-commit.tar.gz",
            "Expand-Archive -Path evavo-upgrade-commit.tar.gz",
            "gh repo create",
            "--public --source=. --remote=origin --push",
            "Complete automation for all 7 AI modalities",
            "ComfyUI, Ollama, Kokoro",
        )
        for name in GIT_COMPAT_FILES:
            source = (ROOT / name).read_text(encoding="utf-8")
            for token in forbidden_active:
                with self.subTest(name=name, token=token):
                    self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
