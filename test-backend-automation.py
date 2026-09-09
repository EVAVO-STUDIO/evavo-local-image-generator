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

    def test_missing_checkpoint_loader_is_empty_inventory_but_connection_errors_propagate(self) -> None:
        backend = ComfyUIBackend("http://127.0.0.1:18199")
        with patch.object(backend, "node_input_choices", side_effect=RuntimeError("COMFYUI_HTTP_ERROR:404:unknown node")):
            self.assertEqual(backend.checkpoints(), [])
        with patch.object(backend, "node_input_choices", side_effect=RuntimeError("COMFYUI_CONNECTION_ERROR:offline")):
            with self.assertRaisesRegex(RuntimeError, "COMFYUI_CONNECTION_ERROR"):
                backend.checkpoints()

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

    def test_workflow_preflight_accepts_valid_literal_choices_and_connections(self) -> None:
        backend = ComfyUIBackend("http://127.0.0.1:18199")
        info = {
            "UNETLoader": {"input": {"required": {"unet_name": [["available-unet.safetensors"], {}]}}},
            "KSampler": {"input": {"required": {"model": ["MODEL", {}]}}},
        }
        workflow = {
            "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "available-unet.safetensors"}},
            "2": {"class_type": "KSampler", "inputs": {"model": ["1", 0]}},
        }
        with patch.object(backend, "object_info", return_value=info):
            result = backend.preflight_workflow(workflow)
        self.assertTrue(result["ok"])
        self.assertEqual(result["node_classes"], ["KSampler", "UNETLoader"])
        self.assertEqual(result["invalid_choices"], [])

    def test_workflow_preflight_rejects_missing_node_class(self) -> None:
        backend = ComfyUIBackend("http://127.0.0.1:18199")
        workflow = {"7": {"class_type": "MissingCustomNode", "inputs": {}}}
        with patch.object(backend, "object_info", return_value={}):
            with self.assertRaises(RuntimeError) as context:
                backend.preflight_workflow(workflow)
        message = str(context.exception)
        self.assertIn("COMFYUI_WORKFLOW_PREFLIGHT_FAILED", message)
        self.assertIn("MissingCustomNode", message)
        self.assertIn('"missing_nodes"', message)

    def test_workflow_preflight_rejects_missing_required_input(self) -> None:
        backend = ComfyUIBackend("http://127.0.0.1:18199")
        info = {"CLIPLoader": {"input": {"required": {"clip_name": [["clip.safetensors"], {}]}}}}
        workflow = {"3": {"class_type": "CLIPLoader", "inputs": {}}}
        with patch.object(backend, "object_info", return_value=info):
            with self.assertRaises(RuntimeError) as context:
                backend.preflight_workflow(workflow)
        message = str(context.exception)
        self.assertIn('"missing_inputs"', message)
        self.assertIn("clip_name", message)

    def test_workflow_preflight_rejects_unavailable_literal_model_choice(self) -> None:
        backend = ComfyUIBackend("http://127.0.0.1:18199")
        info = {"UNETLoader": {"input": {"required": {"unet_name": [["available.safetensors"], {}]}}}}
        workflow = {"1": {"class_type": "UNETLoader", "inputs": {"unet_name": "missing.safetensors"}}}
        with patch.object(backend, "object_info", return_value=info):
            with self.assertRaises(RuntimeError) as context:
                backend.preflight_workflow(workflow)
        message = str(context.exception)
        self.assertIn('"invalid_choices"', message)
        self.assertIn("missing.safetensors", message)
        self.assertIn("available.safetensors", message)

    def test_custom_queue_runs_preflight_before_prompt_submission(self) -> None:
        backend = ComfyUIBackend("http://127.0.0.1:18199")
        with tempfile.TemporaryDirectory() as directory:
            workflow = Path(directory) / "custom.json"
            workflow.write_text(json.dumps({"1": {"class_type": "CustomNode", "inputs": {}}}), encoding="utf-8")
            with (
                patch.object(backend, "checkpoints", return_value=[]),
                patch.object(backend, "preflight_workflow", side_effect=RuntimeError("preflight blocked")) as preflight,
                patch.object(backend, "_request") as request,
            ):
                with self.assertRaisesRegex(RuntimeError, "preflight blocked"):
                    backend.queue_image("test", workflow_path=str(workflow))
            preflight.assert_called_once()
            request.assert_not_called()

    def test_custom_queue_can_explicitly_disable_preflight(self) -> None:
        backend = ComfyUIBackend("http://127.0.0.1:18199")
        with tempfile.TemporaryDirectory() as directory:
            workflow = Path(directory) / "custom.json"
            workflow.write_text(json.dumps({"1": {"class_type": "CustomNode", "inputs": {}}}), encoding="utf-8")
            with (
                patch.dict(os.environ, {"EVAVO_PREFLIGHT_CUSTOM_WORKFLOW": "0"}, clear=False),
                patch.object(backend, "checkpoints", return_value=[]),
                patch.object(backend, "preflight_workflow") as preflight,
                patch.object(backend, "_request", return_value={"prompt_id": "prompt-123", "node_errors": {}}) as request,
            ):
                queued = backend.queue_image("test", workflow_path=str(workflow))
            preflight.assert_not_called()
            request.assert_called_once()
            self.assertEqual(queued["task_id"], "prompt-123")

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
