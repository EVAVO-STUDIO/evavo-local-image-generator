"""Package-level tests for current EVAVO storage and MCP v2 integration."""

from __future__ import annotations

import unittest

from evavo_local_image_generator import mcp_server
from evavo_local_image_generator.storage import BeeStorageClient


class StorageTests(unittest.TestCase):
    def test_storage_client_digest_and_verification(self) -> None:
        client = BeeStorageClient()
        data = b"test data"
        digest = client.compute_digest(data)
        self.assertEqual(len(digest), 64)
        saved = client.save_file(data, "fixture.bin")
        self.assertEqual(saved, digest)
        self.assertTrue(client.verify_digest("fixture.bin", digest))
        self.assertFalse(client.verify_digest("missing.bin", digest))


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
