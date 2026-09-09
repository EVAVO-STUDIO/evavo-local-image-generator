"""Offline tests for safe batch reconciliation/resume helpers."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _module():
    path = ROOT / "batch-resume.py"
    source = path.read_text(encoding="utf-8-sig")
    compile(source, str(path), "exec", dont_inherit=True)
    spec = importlib.util.spec_from_file_location("evavo_batch_resume", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load batch-resume.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BatchResumeTests(unittest.TestCase):
    def test_backend_task_identity_distinguishes_local_failures(self):
        module = _module()
        self.assertTrue(module._known_backend_task("1b639870-544f-4e8a-9020-18a16a3b6de4"))
        self.assertFalse(module._known_backend_task("local_failed_deadbeef"))
        self.assertFalse(module._known_backend_task(None))

    def test_manifest_loader_requires_supported_schema(self):
        module = _module()
        with tempfile.TemporaryDirectory() as value:
            path = Path(value) / "bad.json"
            path.write_text(json.dumps({"schema_version": 99, "items": []}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unsupported"):
                module._load_manifest(path)

    def test_resume_store_updates_existing_manifest_without_replacing_plan(self):
        module = _module()
        with tempfile.TemporaryDirectory() as value:
            path = Path(value) / "batch.json"
            payload = {
                "schema_version": 1,
                "items": [
                    {
                        "index": 0,
                        "prompt": "fixed front-on room, soft window light",
                        "status": "queued",
                        "task_id": "task-123",
                        "result": {"status": "queued", "task_id": "task-123"},
                    }
                ],
            }
            path.write_text(json.dumps(payload), encoding="utf-8")
            store = module.ResumeManifestStore(path, payload)
            asyncio.run(
                store.record(
                    0,
                    {"status": "completed", "task_id": "task-123", "seed": 1337},
                )
            )
            asyncio.run(store.finish())
            updated = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(updated["items"][0]["prompt"], payload["items"][0]["prompt"])
            self.assertEqual(updated["items"][0]["status"], "completed")
            self.assertTrue(updated["summary"]["ok"])

    def test_source_requires_explicit_retry_for_ambiguous_work(self):
        source = (ROOT / "batch-resume.py").read_text(encoding="utf-8-sig")
        self.assertIn("--retry-failed", source)
        self.assertIn("--retry-pending", source)
        self.assertIn("--force-retry-identified", source)
        self.assertIn("never silently duplicated", source)
        self.assertIn("_known_backend_task", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
