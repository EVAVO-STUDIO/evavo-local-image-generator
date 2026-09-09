#!/usr/bin/env python3
"""Offline contract tests for current-vs-historical EVAVO documentation."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CURRENT_DOCS = (
    "README.md",
    "CLAUDE.md",
    "AGENT-INTEGRATION.md",
    "AUTOMATION-GUIDE.md",
    "AUTONOMOUS-AUTOMATION.md",
    "AUTONOMOUS_SETUP.md",
    "COMPLETE-AUTOMATION-GUIDE.md",
    "DEPLOYMENT-CHECKLIST.md",
    "DEPLOYMENT-ACTIVE.md",
    "DEPLOYMENT_GUIDE.md",
    "FINAL-INSTRUCTIONS.md",
    "GATEWAY-INTEGRATION-GUIDE.md",
    "OPERATIONS-GUIDE.md",
    "CHATGPT-TUNNEL.md",
    "QUICK-REFERENCE.md",
)
HISTORICAL_DOCS = (
    "BEESTATION-UPGRADE-COMPLETE.md",
    "CLAUDE-UPGRADE-COMPLETE.md",
    "GENERATION-COMPLETE.txt",
)
RETIRED_ACTIVE_GUIDANCE = (
    "KOKORO_ENDPOINT=",
    "MODEL3D_ENDPOINT=",
    "TEXTURE_ENDPOINT=",
    "PARTICLE_ENDPOINT=",
    "EVAVO_LOCAL_IMAGE_GENERATOR_STORAGE=bee://",
    "taskkill /IM python.exe",
    "taskkill /F /IM python.exe",
)


class DocumentationContractTests(unittest.TestCase):
    def test_current_docs_exist(self) -> None:
        missing = [name for name in CURRENT_DOCS if not (ROOT / name).is_file()]
        self.assertEqual(missing, [])

    def test_current_docs_do_not_restore_retired_operating_variables(self) -> None:
        failures: list[str] = []
        for name in CURRENT_DOCS:
            source = (ROOT / name).read_text(encoding="utf-8", errors="replace")
            for pattern in RETIRED_ACTIVE_GUIDANCE:
                if pattern in source:
                    failures.append(f"{name}: {pattern}")
        self.assertEqual(failures, [], "retired current guidance found: " + " | ".join(failures))

    def test_primary_agent_docs_describe_current_transport_boundary(self) -> None:
        for name in ("README.md", "CLAUDE.md", "AGENT-INTEGRATION.md", "QUICK-REFERENCE.md"):
            source = (ROOT / name).read_text(encoding="utf-8", errors="replace").lower()
            with self.subTest(document=name):
                self.assertIn("native comfyui", source)
                self.assertIn("claude", source)
                self.assertIn("stdio", source)
                self.assertIn("chatgpt", source)
                self.assertIn("secure mcp tunnel", source)

    def test_gateway_docs_are_explicitly_image_only_for_production(self) -> None:
        source = (ROOT / "GATEWAY-INTEGRATION-GUIDE.md").read_text(encoding="utf-8", errors="replace").lower()
        self.assertIn("native-image", source)
        self.assertIn("501", source)
        self.assertIn("/generate/video", source)
        self.assertIn("/generate/audio", source)
        self.assertIn("/generate/3d", source)
        self.assertIn("loopback", source)

    def test_historical_reports_are_visibly_superseded(self) -> None:
        for name in HISTORICAL_DOCS:
            path = ROOT / name
            self.assertTrue(path.is_file(), name)
            prefix = path.read_text(encoding="utf-8", errors="replace")[:1200].upper()
            with self.subTest(document=name):
                self.assertIn("HISTORICAL", prefix)
                self.assertIn("SUPERSEDED", prefix)


if __name__ == "__main__":
    unittest.main(verbosity=2)
