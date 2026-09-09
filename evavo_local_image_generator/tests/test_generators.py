"""Package-level tests for current EVAVO package/MCP compatibility contracts."""

from __future__ import annotations

import unittest
from pathlib import Path

from evavo_local_image_generator import mcp_server
from evavo_local_image_generator.storage import BeeStorageClient, resolve_to_windows_path

ROOT = Path(__file__).resolve().parents[2]


class StorageCompatibilityTests(unittest.TestCase):
    def test_storage_client_digest_and_verification_are_memory_only(self) -> None:
        client = BeeStorageClient()
        data = b"test data"
        digest = client.compute_digest(data)
        self.assertEqual(len(digest), 64)
        saved = client.save_file(data, "fixture.bin")
        self.assertEqual(saved, digest)
        self.assertTrue(client.verify_digest("fixture.bin", digest))
        self.assertFalse(client.verify_digest("missing.bin", digest))

    def test_legacy_bee_uri_does_not_manufacture_unc_path(self) -> None:
        self.assertIsNone(resolve_to_windows_path("bee://primary/EVAVO/ImageGeneration"))

    def test_script_storage_helper_has_no_hidden_manifest_writes(self) -> None:
        source = (ROOT / "evavo_local_image_generator" / "scripts" / "storage.py").read_text(encoding="utf-8")
        self.assertNotIn("Path.home()", source)
        self.assertNotIn("manifest.json", source)
        self.assertNotIn("EVAVO_LOCAL_IMAGE_GENERATOR_STORAGE", source)
        self.assertNotIn("mkdir(", source)
        self.assertNotIn("open(", source)

    def test_legacy_image_api_uses_shared_task_tracker_not_storage_manifest(self) -> None:
        source = (ROOT / "evavo_local_image_generator" / "scripts" / "generate.py").read_text(encoding="utf-8")
        self.assertIn("TaskTracker", source)
        self.assertIn("backend.queue_image", source)
        self.assertIn("backend.wait_and_download", source)
        self.assertNotIn("get_storage_client", source)
        self.assertNotIn("storage_uri", source)
        self.assertNotIn("EVAVO_LOCAL_IMAGE_GENERATOR_STORAGE", source)


class MCPV2ContractTests(unittest.IsolatedAsyncioTestCase):
    def test_current_mcp_server_surface_is_present(self) -> None:
        self.assertIsNotNone(mcp_server.mcp)
        self.assertTrue(callable(mcp_server.generate_image))
        self.assertTrue(callable(mcp_server.generate_batch))
        self.assertTrue(callable(mcp_server.workflow_preflight))
        self.assertTrue(callable(mcp_server.read_output_image))
        self.assertFalse(hasattr(mcp_server, "EvavoLocalImageGeneratorMCPServer"))

    async def test_invalid_prompt_fails_without_touching_backend(self) -> None:
        result = await mcp_server._generate_image_impl("   ", auto_start=False)
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "INVALID_PROMPT")


if __name__ == "__main__":
    unittest.main(verbosity=2)
