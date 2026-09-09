"""Offline tests for EVAVO release evidence creation and verification."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _module():
    path = ROOT / "release-evidence.py"
    source = path.read_text(encoding="utf-8-sig")
    compile(source, str(path), "exec", dont_inherit=True)
    spec = importlib.util.spec_from_file_location("evavo_release_evidence", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load release evidence module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReleaseEvidenceTests(unittest.TestCase):
    def _fixture(self, root: Path) -> None:
        (root / "gate").mkdir(parents=True)
        (root / "hero").mkdir(parents=True)
        (root / "gate" / "release-gate.json").write_text(
            json.dumps({"ok": True, "schemaVersion": 5, "failures": []}),
            encoding="utf-8",
        )
        (root / "hero" / "report.html").write_text("<html>review</html>", encoding="utf-8")
        (root / "hero" / "image.png").write_bytes(b"\x89PNG\r\n\x1a\nfixture")

    def test_create_and_verify_round_trip(self):
        module = _module()
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self._fixture(root)
            created = module.create_manifest(root)
            self.assertEqual(created["file_count"], 3)
            self.assertEqual(len(created["evidence_set_sha256"]), 64)
            verified = module.verify_manifest(root / "release-manifest.json")
            self.assertTrue(verified["ok"], verified)
            self.assertEqual(verified["checked_files"], 3)

    def test_modified_file_is_rejected(self):
        module = _module()
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self._fixture(root)
            module.create_manifest(root)
            (root / "hero" / "report.html").write_text("changed", encoding="utf-8")
            result = module.verify_manifest(root / "release-manifest.json")
            self.assertFalse(result["ok"])
            self.assertTrue(any("sha256 mismatch" in item for item in result["errors"]))

    def test_extra_file_is_rejected(self):
        module = _module()
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self._fixture(root)
            module.create_manifest(root)
            (root / "unreviewed.txt").write_text("extra", encoding="utf-8")
            result = module.verify_manifest(root / "release-manifest.json")
            self.assertFalse(result["ok"])
            self.assertTrue(any("unmanifested files" in item for item in result["errors"]))

    def test_manifest_records_json_status_without_trusting_it_as_quality(self):
        module = _module()
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self._fixture(root)
            created = module.create_manifest(root)
            gate = next(item for item in created["files"] if item["path"] == "gate/release-gate.json")
            self.assertEqual(gate["json_status"]["ok"], True)
            self.assertEqual(gate["json_status"]["failure_count"], 0)
            self.assertNotIn("quality_score", created)


if __name__ == "__main__":
    unittest.main(verbosity=2)
