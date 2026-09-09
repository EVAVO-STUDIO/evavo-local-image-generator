#!/usr/bin/env python3
"""Offline unit tests for EVAVO backend/model automation and MCP file boundaries."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evavo_local_image_generator.backends import ComfyUIBackend
from evavo_local_image_generator import mcp_server


class BackendAutomationTests(unittest.TestCase):
    def test_missing_checkpoint_retries_after_configured_repair(self) -> None:
        backend = ComfyUIBackend("http://127.0.0.1:18199")
        with (
            patch.object(backend, "checkpoints", side_effect=[[], ["repaired.safetensors"]]) as checkpoints,
            patch.object(backend, "_provision_configured_checkpoint", return_value=True) as provision,
        ):
            chosen = backend.choose_checkpoint()
        self.assertEqual(chosen, "repaired.safetensors")
        self.assertEqual(checkpoints.call_count, 2)
        provision.assert_called_once_with()

    def test_checkpoint_repair_is_disabled_without_flag(self) -> None:
        backend = ComfyUIBackend("http://127.0.0.1:18199")
        with patch.dict(
            os.environ,
            {"EVAVO_AUTO_PROVISION_CHECKPOINT": "0", "EVAVO_CHECKPOINT_FILE": "C:/models/model.safetensors"},
            clear=False,
        ):
            self.assertFalse(backend._provision_configured_checkpoint())

    def test_checkpoint_repair_requires_owner_configured_source(self) -> None:
        backend = ComfyUIBackend("http://127.0.0.1:18199")
        env = os.environ.copy()
        env.pop("EVAVO_CHECKPOINT_FILE", None)
        env.pop("EVAVO_CHECKPOINT_URL", None)
        env["EVAVO_AUTO_PROVISION_CHECKPOINT"] = "1"
        with patch.dict(os.environ, env, clear=True):
            self.assertFalse(backend._provision_configured_checkpoint())

    def test_custom_workflow_does_not_trigger_checkpoint_provisioning(self) -> None:
        backend = ComfyUIBackend("http://127.0.0.1:18199")
        with tempfile.TemporaryDirectory() as directory:
            workflow = Path(directory) / "custom.json"
            workflow.write_text(
                json.dumps({"1": {"class_type": "CustomNode", "inputs": {"text": "{{prompt}}", "seed": "{{seed}}"}}}),
                encoding="utf-8",
            )
            with (
                patch.object(backend, "checkpoints", return_value=[]),
                patch.object(backend, "_provision_configured_checkpoint") as provision,
            ):
                rendered = backend.build_txt2img_workflow("custom prompt", workflow_path=str(workflow))
            provision.assert_not_called()
            self.assertEqual(rendered["1"]["inputs"]["text"], "custom prompt")
            self.assertIsInstance(rendered["1"]["inputs"]["seed"], int)

    def test_custom_workflow_supports_uppercase_and_lowercase_placeholders(self) -> None:
        backend = ComfyUIBackend("http://127.0.0.1:18199")
        with tempfile.TemporaryDirectory() as directory:
            workflow = Path(directory) / "aliases.json"
            workflow.write_text(
                json.dumps(
                    {
                        "1": {
                            "class_type": "CustomNode",
                            "inputs": {
                                "upper_prompt": "{{PROMPT}}",
                                "lower_prompt": "{{prompt}}",
                                "negative": "{{NEGATIVE_PROMPT}}",
                                "width": "{{WIDTH}}",
                                "height": "{{height}}",
                                "steps": "{{STEPS}}",
                                "cfg": "{{CFG}}",
                                "cfg_scale": "{{CFG_SCALE}}",
                                "seed": "{{SEED}}",
                                "checkpoint": "{{CHECKPOINT}}",
                                "prefix": "{{FILENAME_PREFIX}}",
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            with patch.object(backend, "checkpoints", return_value=["test.safetensors"]):
                rendered = backend.build_txt2img_workflow(
                    "alias prompt",
                    negative_prompt="alias negative",
                    width=768,
                    height=512,
                    steps=17,
                    cfg_scale=5.5,
                    seed=12345,
                    checkpoint="test.safetensors",
                    filename_prefix="EVAVO/aliases",
                    workflow_path=str(workflow),
                )
            inputs = rendered["1"]["inputs"]
            self.assertEqual(inputs["upper_prompt"], "alias prompt")
            self.assertEqual(inputs["lower_prompt"], "alias prompt")
            self.assertEqual(inputs["negative"], "alias negative")
            self.assertEqual(inputs["width"], 768)
            self.assertEqual(inputs["height"], 512)
            self.assertEqual(inputs["steps"], 17)
            self.assertEqual(inputs["cfg"], 5.5)
            self.assertEqual(inputs["cfg_scale"], 5.5)
            self.assertEqual(inputs["seed"], 12345)
            self.assertEqual(inputs["checkpoint"], "test.safetensors")
            self.assertEqual(inputs["prefix"], "EVAVO/aliases")

    def test_output_image_rejects_unrecorded_file_outside_output_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output_root = root / "allowed"
            output_root.mkdir()
            outside = root / "outside.png"
            outside.write_bytes(b"not-empty")
            with (
                patch.object(mcp_server, "_output_root", return_value=output_root.resolve()),
                patch.object(mcp_server, "_recorded_output_paths", return_value=set()),
            ):
                with self.assertRaises(PermissionError):
                    mcp_server._validated_output_image(str(outside))

    def test_output_image_allows_file_inside_output_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_root = Path(directory) / "allowed"
            output_root.mkdir()
            image = output_root / "generated.png"
            image.write_bytes(b"not-empty")
            with (
                patch.object(mcp_server, "_output_root", return_value=output_root.resolve()),
                patch.object(mcp_server, "_recorded_output_paths", return_value=set()),
            ):
                self.assertEqual(mcp_server._validated_output_image(str(image)), image.resolve())

    def test_output_image_allows_recorded_custom_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output_root = root / "allowed"
            output_root.mkdir()
            recorded = root / "custom-output.webp"
            recorded.write_bytes(b"not-empty")
            with (
                patch.object(mcp_server, "_output_root", return_value=output_root.resolve()),
                patch.object(mcp_server, "_recorded_output_paths", return_value={recorded.resolve()}),
            ):
                self.assertEqual(mcp_server._validated_output_image(str(recorded)), recorded.resolve())

    def test_output_image_rejects_unsupported_extension(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_root = Path(directory)
            file = output_root / "generated.txt"
            file.write_text("not an image", encoding="utf-8")
            with patch.object(mcp_server, "_output_root", return_value=output_root.resolve()):
                with self.assertRaises(ValueError):
                    mcp_server._validated_output_image(str(file))


if __name__ == "__main__":
    unittest.main(verbosity=2)
