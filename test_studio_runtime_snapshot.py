"""Offline tests for read-only sibling Studio runtime attestation helpers."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _module():
    path = ROOT / "studio-runtime-snapshot.py"
    source = path.read_text(encoding="utf-8-sig")
    compile(source, str(path), "exec", dont_inherit=True)
    spec = importlib.util.spec_from_file_location("evavo_studio_runtime_snapshot", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load Studio runtime snapshot")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class StudioRuntimeSnapshotTests(unittest.TestCase):
    def test_file_receipt_is_sha256_and_read_only(self):
        module = _module()
        with tempfile.TemporaryDirectory() as value:
            path = Path(value) / "package.json"
            path.write_text('{"name":"fixture"}', encoding="utf-8")
            before = path.read_bytes()
            receipt = module._file_receipt(path)
            self.assertEqual(len(receipt["sha256"]), 64)
            self.assertEqual(receipt["bytes"], len(before))
            self.assertEqual(path.read_bytes(), before)

    def test_worker_endpoint_policy_is_loopback_only(self):
        module = _module()
        self.assertTrue(module._loopback_http("http://127.0.0.1:4314"))
        self.assertTrue(module._loopback_http("http://localhost:4314"))
        self.assertFalse(module._loopback_http("https://127.0.0.1:4314"))
        self.assertFalse(module._loopback_http("http://192.168.1.50:4314"))
        self.assertFalse(module._loopback_http("http://127.0.0.1:4314?token=x"))

    def test_json_parser_handles_clean_and_wrapped_json(self):
        module = _module()
        clean = module._json_from_command({"stdout": '{"ok":true}'})
        wrapped = module._json_from_command({"stdout": 'prefix\n{"passes":true}\nsuffix'})
        self.assertEqual(clean, {"ok": True})
        self.assertEqual(wrapped, {"passes": True})

    def test_full_gate_requests_all_sibling_runtime_receipts(self):
        source = (ROOT / "RUN-PRODUCTION-QUALITY.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("kokoro-runtime-attestation", source)
        self.assertIn("3d-runtime-attestation", source)
        self.assertIn("atmosphere-runtime-attestation", source)
        self.assertIn("studio-runtime-snapshot.py", source)
        self.assertIn("kokoro-runtime-snapshot.py", source)
        self.assertIn("runtimeEvidence", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
