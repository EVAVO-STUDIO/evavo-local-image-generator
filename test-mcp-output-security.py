#!/usr/bin/env python3
"""Offline security tests for MCP workflow/output file boundaries."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from evavo_local_image_generator import mcp_server

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"EVAVO-test-png"


class McpOutputSecurityTests(unittest.TestCase):
    def test_valid_png_under_default_output_root_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "outputs"
            root.mkdir()
            image = root / "valid.png"
            image.write_bytes(PNG_BYTES)
            with mock.patch.dict(os.environ, {"EVAVO_GENERATION_OUTPUT_DIR": str(root)}, clear=False):
                validated = mcp_server._validated_output_image(str(image))
            self.assertEqual(validated, image.resolve())

    def test_fake_png_extension_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "outputs"
            root.mkdir()
            image = root / "fake.png"
            image.write_bytes(b"not really an image")
            with mock.patch.dict(os.environ, {"EVAVO_GENERATION_OUTPUT_DIR": str(root)}, clear=False):
                with self.assertRaises(ValueError) as context:
                    mcp_server._validated_output_image(str(image))
            self.assertIn("does not match", str(context.exception))

    def test_final_symlink_swap_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "outputs"
            root.mkdir()
            target = base / "secret.png"
            target.write_bytes(PNG_BYTES)
            link = root / "generated.png"
            try:
                link.symlink_to(target)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"symlinks unavailable: {exc}")
            with mock.patch.dict(os.environ, {"EVAVO_GENERATION_OUTPUT_DIR": str(root)}, clear=False):
                with self.assertRaises(PermissionError):
                    mcp_server._validated_output_image(str(link))

    def test_parent_symlink_redirection_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "outputs"
            root.mkdir()
            outside = base / "outside"
            outside.mkdir()
            target = outside / "generated.png"
            target.write_bytes(PNG_BYTES)
            redirected = root / "redirected"
            try:
                redirected.symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"directory symlinks unavailable: {exc}")
            with mock.patch.dict(os.environ, {"EVAVO_GENERATION_OUTPUT_DIR": str(root)}, clear=False):
                with self.assertRaises(PermissionError):
                    mcp_server._validated_output_image(str(redirected / "generated.png"))

    def test_external_output_directory_requires_owner_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            default_root = base / "default"
            extra_root = base / "project-output"
            default_root.mkdir()
            extra_root.mkdir()
            env = {"EVAVO_GENERATION_OUTPUT_DIR": str(default_root), "EVAVO_MCP_OUTPUT_ROOTS": ""}
            with mock.patch.dict(os.environ, env, clear=False):
                with self.assertRaises(PermissionError):
                    mcp_server._validated_output_dir(str(extra_root))
            with mock.patch.dict(
                os.environ,
                {"EVAVO_GENERATION_OUTPUT_DIR": str(default_root), "EVAVO_MCP_OUTPUT_ROOTS": str(extra_root)},
                clear=False,
            ):
                self.assertEqual(mcp_server._validated_output_dir(str(extra_root)), extra_root.resolve())

    def test_owner_default_workflow_is_allowed_without_generic_path_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workflow = Path(temp) / "owner.json"
            workflow.write_text("{}\n", encoding="utf-8")
            with mock.patch.dict(
                os.environ,
                {
                    "EVAVO_COMFYUI_WORKFLOW": str(workflow),
                    "EVAVO_MCP_ALLOW_WORKFLOW_PATHS": "0",
                    "EVAVO_MCP_WORKFLOW_ROOT": "",
                },
                clear=False,
            ):
                self.assertEqual(mcp_server._validated_workflow_path(str(workflow)), str(workflow.resolve()))

    def test_tool_workflow_path_requires_owner_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "workflows"
            root.mkdir()
            inside = root / "inside.json"
            outside = base / "outside.json"
            inside.write_text("{}\n", encoding="utf-8")
            outside.write_text("{}\n", encoding="utf-8")
            with mock.patch.dict(
                os.environ,
                {
                    "EVAVO_COMFYUI_WORKFLOW": "",
                    "EVAVO_MCP_ALLOW_WORKFLOW_PATHS": "1",
                    "EVAVO_MCP_WORKFLOW_ROOT": str(root),
                },
                clear=False,
            ):
                self.assertEqual(mcp_server._validated_workflow_path(str(inside)), str(inside.resolve()))
                with self.assertRaises(PermissionError):
                    mcp_server._validated_workflow_path(str(outside))


if __name__ == "__main__":
    unittest.main(verbosity=2)
