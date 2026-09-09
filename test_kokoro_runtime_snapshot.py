"""Offline tests for Kokoro runtime evidence tooling."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _module():
    path = ROOT / "kokoro-runtime-snapshot.py"
    source = path.read_text(encoding="utf-8-sig")
    compile(source, str(path), "exec", dont_inherit=True)
    spec = importlib.util.spec_from_file_location("evavo_kokoro_runtime_snapshot", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load Kokoro runtime snapshot")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class KokoroRuntimeSnapshotTests(unittest.TestCase):
    def test_important_file_attestation_hashes_known_runtime_files(self):
        module = _module()
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            starter = root / "start-gpu.ps1"
            starter.write_text("Write-Host 'Kokoro'\n", encoding="utf-8")
            files = module._important_files(root)
            self.assertEqual(len(files), 1)
            self.assertEqual(Path(files[0]["path"]).name, "start-gpu.ps1")
            self.assertEqual(len(files[0]["sha256"]), 64)
            self.assertGreater(files[0]["bytes"], 0)

    def test_non_git_directory_is_reported_without_mutation(self):
        module = _module()
        with tempfile.TemporaryDirectory() as value:
            result = module._git_snapshot(Path(value))
            self.assertFalse(result["available"])

    def test_voice_comparison_requires_runtime_attestation_by_default(self):
        source = (ROOT / "RUN-KOKORO-VOICE-COMPARISON.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("kokoro-runtime-snapshot.py", source)
        self.assertIn("--require-complete", source)
        self.assertIn("AllowPartialRuntimeEvidence", source)
        self.assertIn("runtime-evidence.json", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
