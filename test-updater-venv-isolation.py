#!/usr/bin/env python3
"""Static safety/order tests for isolated canonical Windows setup."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UPDATER = ROOT / "UPDATE-AND-VERIFY-EVAVO.ps1"


class UpdaterVenvIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = UPDATER.read_text(encoding="utf-8")

    def test_powershell_does_not_contain_python_elif_keyword(self) -> None:
        self.assertNotIn("\nelif (", self.source)
        self.assertIn("\nelseif (", self.source)

    def test_repo_local_venv_is_the_runtime_python(self) -> None:
        self.assertIn('$venvPython = Join-Path $PSScriptRoot ".venv\\Scripts\\python.exe"', self.source)
        self.assertIn('& $bootstrapPython -m venv (Join-Path $PSScriptRoot ".venv")', self.source)
        self.assertIn('$python = (Resolve-Path $venvPython).Path', self.source)
        self.assertIn('Using isolated EVAVO Python: $python', self.source)

    def test_structural_verification_happens_before_venv_or_pip_mutation(self) -> None:
        structural = self.source.index('(Join-Path $PSScriptRoot "verify-evavo.py") --require-powershell')
        create_venv = self.source.index('-m venv (Join-Path $PSScriptRoot ".venv")')
        pip_install = self.source.index('-m pip install -r (Join-Path $PSScriptRoot "requirements.txt")')
        full_verify = self.source.index('verify --full --require-powershell')
        self.assertLess(structural, create_venv)
        self.assertLess(create_venv, pip_install)
        self.assertLess(pip_install, full_verify)

    def test_pip_install_uses_only_isolated_runtime_variable(self) -> None:
        pip_line = '& $python -m pip install -r (Join-Path $PSScriptRoot "requirements.txt")'
        self.assertIn(pip_line, self.source)
        self.assertNotIn('& $bootstrapPython -m pip install', self.source)
        self.assertNotIn('& $pythonCommand.Source -m pip install', self.source)

    def test_new_venv_cannot_skip_dependencies(self) -> None:
        self.assertIn('$venvCreated = $true', self.source)
        self.assertIn('if ($SkipDependencies -and $venvCreated)', self.source)
        self.assertIn('-SkipDependencies cannot be used when .venv had to be created', self.source)

    def test_all_post_install_runtime_proofs_use_venv_python(self) -> None:
        required = (
            '& $python (Join-Path $PSScriptRoot "evavo.py") verify --full --require-powershell',
            '& $python @backendDoctorArgs',
            '& $python (Join-Path $PSScriptRoot "recover-comfyui.py") --json',
            '& $python (Join-Path $PSScriptRoot "evavo.py") bootstrap --skip-pull --skip-verify',
            '& $python (Join-Path $PSScriptRoot "real-generation-smoke.py") --json',
            '& $python @finalDoctorArgs',
            '& $python (Join-Path $PSScriptRoot "evavo.py") status',
        )
        for snippet in required:
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, self.source)

    def test_origin_and_clean_tree_checks_still_precede_pull_and_environment_mutation(self) -> None:
        origin = self.source.index('git remote get-url origin')
        branch = self.source.index('git branch --show-current')
        dirty = self.source.index('git status --porcelain')
        pull = self.source.index('git pull --ff-only origin main')
        structural = self.source.index('Running pre-dependency structural verification')
        self.assertLess(origin, branch)
        self.assertLess(branch, dirty)
        self.assertLess(dirty, pull)
        self.assertLess(pull, structural)


if __name__ == "__main__":
    unittest.main(verbosity=2)
