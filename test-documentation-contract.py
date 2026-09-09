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
    "AGENT-RECOVERY.md",
    "AUTOMATION-GUIDE.md",
    "AUTONOMOUS-AUTOMATION.md",
    "AUTONOMOUS_SETUP.md",
    "COMPLETE-AUTOMATION-GUIDE.md",
    "DEPLOYMENT-CHECKLIST.md",
    "DEPLOYMENT-ACTIVE.md",
    "DEPLOYMENT_GUIDE.md",
    "FINAL-INSTRUCTIONS.md",
    "GATEWAY-INTEGRATION-GUIDE.md",
    "GATEWAY-AUX-PROVIDERS.md",
    "PROVIDER-INTEGRATION-GUIDE.md",
    "OPERATIONS-GUIDE.md",
    "CHATGPT-TUNNEL.md",
    "QUICK-REFERENCE.md",
    "PROJECT_SUMMARY.md",
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

    def test_gateway_docs_preserve_owned_vs_delegated_boundary(self) -> None:
        combined = "\n".join(
            (ROOT / name).read_text(encoding="utf-8", errors="replace").lower()
            for name in ("GATEWAY-INTEGRATION-GUIDE.md", "GATEWAY-AUX-PROVIDERS.md", "PROVIDER-INTEGRATION-GUIDE.md")
        )
        self.assertIn("native comfyui", combined)
        self.assertIn("owned", combined)
        self.assertIn("delegat", combined)
        self.assertIn("fail", combined)
        self.assertIn("/services", combined)
        self.assertIn("/generate/video", combined)
        self.assertIn("/generate/audio", combined)
        self.assertIn("/generate/3d", combined)
        self.assertIn("loopback", combined)
        self.assertNotIn("these routes return `501`", combined)

    def test_gateway_docs_do_not_claim_delegated_media_is_mcp_owned(self) -> None:
        source = (ROOT / "GATEWAY-INTEGRATION-GUIDE.md").read_text(encoding="utf-8", errors="replace").lower()
        self.assertIn("mcp", source)
        self.assertIn("image", source)
        self.assertIn("not added to the mcp", source)

    def test_gateway_runbook_documents_request_and_state_safety(self) -> None:
        source = (ROOT / "GATEWAY-INTEGRATION-GUIDE.md").read_text(encoding="utf-8", errors="replace").lower()
        self.assertIn("evavo_gateway_max_request_bytes", source)
        self.assertIn("chunked", source)
        self.assertIn("evavo_gateway_max_project_chars", source)
        self.assertIn("evavo_gateway_allow_request_workflow_paths", source)
        self.assertIn("denied by default", source)
        self.assertIn("tasks.json.lock", source)
        self.assertIn("interprocess", source)
        self.assertIn("gateway_task_state_corrupt", source)
        self.assertIn("leaves the original file untouched", source)

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
