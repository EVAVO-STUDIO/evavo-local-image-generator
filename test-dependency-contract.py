#!/usr/bin/env python3
"""Offline dependency/install contract tests for the canonical workstation setup."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ROOT_REQUIREMENTS = ROOT / "requirements.txt"
PACKAGE_REQUIREMENTS = ROOT / "evavo_local_image_generator" / "requirements.txt"
UPDATER = ROOT / "UPDATE-AND-VERIFY-EVAVO.ps1"
README = ROOT / "README.md"


def requirement_lines(path: Path) -> list[str]:
    lines: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            lines.append(line)
    return lines


def normalized_name(requirement: str) -> str:
    match = re.match(r"^([A-Za-z0-9_.-]+)", requirement)
    return (match.group(1) if match else requirement).lower().replace("_", "-")


class DependencyContractTests(unittest.TestCase):
    def test_root_requirements_carry_full_agent_gateway_runtime(self) -> None:
        requirements = requirement_lines(ROOT_REQUIREMENTS)
        required_prefixes = (
            "mcp[cli]>=2,<3",
            "fastapi>=",
            "uvicorn[standard]>=",
            "pydantic>=2.7,<3",
            "websockets>=",
            "aiohttp>=",
        )
        for expected in required_prefixes:
            with self.subTest(expected=expected):
                self.assertTrue(any(line.startswith(expected) for line in requirements), requirements)

    def test_package_compatibility_requirements_keep_mcp_v2(self) -> None:
        requirements = requirement_lines(PACKAGE_REQUIREMENTS)
        self.assertIn("mcp[cli]>=2,<3", requirements)

    def test_no_install_surface_uses_third_party_asyncio_package(self) -> None:
        for path in (ROOT_REQUIREMENTS, PACKAGE_REQUIREMENTS):
            names = {normalized_name(line) for line in requirement_lines(path)}
            with self.subTest(path=path):
                self.assertNotIn("asyncio", names)

    def test_canonical_updater_installs_root_requirements_not_package_subset(self) -> None:
        source = UPDATER.read_text(encoding="utf-8")
        self.assertIn('pip install -r (Join-Path $PSScriptRoot "requirements.txt")', source)
        self.assertNotIn('evavo_local_image_generator\\requirements.txt', source)

    def test_readme_keeps_one_command_workstation_setup_authoritative(self) -> None:
        source = README.read_text(encoding="utf-8")
        self.assertIn(".\\UPDATE-AND-VERIFY-EVAVO.ps1", source)
        self.assertIn("git pull --ff-only origin main", source)
        self.assertNotIn("pip install asyncio", source.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
