#!/usr/bin/env python3
"""Offline safety tests for EVAVO ComfyUI provisioning."""

from __future__ import annotations

import hashlib
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from evavo_local_image_generator import comfyui_runtime

ROOT = Path(__file__).resolve().parent
PROVISIONER = ROOT / "provision-comfyui.py"


def load_provisioner():
    spec = importlib.util.spec_from_file_location("evavo_provision_comfyui", PROVISIONER)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load provision-comfyui.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProvisioningSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_provisioner()

    def test_checkpoint_name_rejects_traversal_and_unknown_extension(self) -> None:
        with self.assertRaises(RuntimeError):
            self.module.validate_model_name("../evil.safetensors")
        with self.assertRaises(RuntimeError):
            self.module.validate_model_name("model.exe")
        self.assertEqual(self.module.validate_model_name("model.safetensors"), "model.safetensors")

    def test_local_checkpoint_copy_sha_and_idempotency(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.safetensors"
            source.write_bytes(b"EVAVO deterministic checkpoint fixture")
            expected = hashlib.sha256(source.read_bytes()).hexdigest()
            destination = root / "ComfyUI" / "models" / "checkpoints"

            installed = self.module.install_local_checkpoint(
                source,
                destination,
                expected_sha256=expected,
                name="test-model.safetensors",
            )
            self.assertEqual(installed["status"], "copied")
            target = Path(installed["path"])
            self.assertTrue(target.is_file())
            self.assertEqual(target.read_bytes(), source.read_bytes())
            self.assertEqual(installed["sha256"], expected)

            repeated = self.module.install_local_checkpoint(
                source,
                destination,
                expected_sha256=expected,
                name="test-model.safetensors",
            )
            self.assertEqual(repeated["status"], "already_present")
            self.assertEqual(repeated["sha256"], expected)

    def test_portable_root_resolves_and_receives_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "ComfyUI_windows_portable"
            app_root = root / "ComfyUI"
            app_root.mkdir(parents=True)
            (app_root / "main.py").write_text("# portable fixture\n", encoding="utf-8")
            source = Path(directory) / "portable-source.safetensors"
            source.write_bytes(b"portable model fixture")
            expected = hashlib.sha256(source.read_bytes()).hexdigest()

            resolved = self.module.resolve_app_root(root)
            self.assertEqual(resolved, app_root.resolve())
            args = SimpleNamespace(
                checkpoint_file=str(source),
                checkpoint_url=None,
                checkpoint_sha256=expected,
                checkpoint_name="portable-model.safetensors",
                allow_http_checkpoint=False,
            )
            installed = self.module.provision_checkpoint(resolved, args)
            self.assertIsNotNone(installed)
            assert installed is not None
            target = Path(installed["path"])
            self.assertEqual(target.parent, app_root.resolve() / "models" / "checkpoints")
            self.assertTrue(target.is_file())
            self.assertEqual(installed["sha256"], expected)

    def test_source_root_resolves_directly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "ComfyUI"
            root.mkdir()
            (root / "main.py").write_text("# source fixture\n", encoding="utf-8")
            self.assertEqual(self.module.resolve_app_root(root), root.resolve())

    def test_local_checkpoint_hash_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.safetensors"
            source.write_bytes(b"not the expected model")
            destination = root / "models" / "checkpoints"
            with self.assertRaises(RuntimeError) as context:
                self.module.install_local_checkpoint(
                    source,
                    destination,
                    expected_sha256="0" * 64,
                    name=None,
                )
            self.assertIn("CHECKPOINT_SHA256_MISMATCH", str(context.exception))
            self.assertFalse((destination / source.name).exists())

    def test_existing_different_destination_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.safetensors"
            source.write_bytes(b"new")
            destination = root / "models" / "checkpoints"
            destination.mkdir(parents=True)
            existing = destination / "shared.safetensors"
            existing.write_bytes(b"existing")
            with self.assertRaises(RuntimeError) as context:
                self.module.install_local_checkpoint(source, destination, expected_sha256=None, name="shared.safetensors")
            self.assertIn("CHECKPOINT_DESTINATION_CONFLICT", str(context.exception))
            self.assertEqual(existing.read_bytes(), b"existing")

    def test_checkpoint_url_requires_https_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(RuntimeError) as context:
                self.module.download_checkpoint(
                    "http://example.invalid/model.safetensors",
                    Path(directory),
                    expected_sha256=None,
                    name=None,
                    allow_http=False,
                )
            self.assertIn("CHECKPOINT_URL_SCHEME", str(context.exception))

    def test_existing_non_comfy_target_is_rejected_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "occupied"
            target.mkdir()
            marker = target / "keep.txt"
            marker.write_text("keep", encoding="utf-8")
            with self.assertRaises(RuntimeError) as context:
                self.module.ensure_checkout(target, "https://example.invalid/ComfyUI.git", update=False)
            self.assertIn("COMFYUI_TARGET_CONFLICT", str(context.exception))
            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")

    def test_shared_model_config_only_emits_existing_supported_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "shared-models"
            for relative in (
                "models/checkpoints",
                "models/loras",
                "vae",
                "models/controlnet",
                "custom_nodes",
                "ignored-folder",
            ):
                (root / relative).mkdir(parents=True, exist_ok=True)
            destination = Path(directory) / "extra-model-paths.yaml"
            written = comfyui_runtime.write_extra_model_paths_config([root], destination)
            self.assertEqual(written, destination.resolve())
            text = destination.read_text(encoding="utf-8")
            self.assertIn("evavo_shared_1:", text)
            self.assertIn(root.resolve().as_posix(), text)
            self.assertIn('checkpoints: "models/checkpoints"', text)
            self.assertIn('loras: "models/loras"', text)
            self.assertIn('vae: "vae"', text)
            self.assertIn('controlnet: "models/controlnet"', text)
            self.assertIn('custom_nodes: "custom_nodes"', text)
            self.assertNotIn("ignored-folder", text)

    def test_shared_model_config_supports_multiple_existing_paths_for_one_category(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "shared-models"
            (root / "models" / "text_encoders").mkdir(parents=True)
            (root / "models" / "clip").mkdir(parents=True)
            text = comfyui_runtime.render_extra_model_paths_yaml([root])
            self.assertIn("text_encoders: |", text)
            self.assertIn("models/text_encoders", text)
            self.assertIn("models/clip", text)

    def test_shared_model_config_rejects_empty_supported_layout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "empty-library"
            root.mkdir()
            with self.assertRaises(RuntimeError) as context:
                comfyui_runtime.render_extra_model_paths_yaml([root])
            self.assertIn("SHARED_MODEL_ROOT_EMPTY", str(context.exception))

    def test_shared_model_environment_rejects_missing_root(self) -> None:
        missing = str((Path(tempfile.gettempdir()) / "evavo-definitely-missing-model-root").resolve())
        with patch.dict(os.environ, {"EVAVO_SHARED_MODEL_ROOTS": missing}, clear=False):
            with self.assertRaises(RuntimeError) as context:
                comfyui_runtime.configured_shared_model_roots()
            self.assertIn("SHARED_MODEL_ROOT_NOT_FOUND", str(context.exception))

    def test_shared_model_configuration_hash_changes_with_effective_layout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "shared-models"
            (root / "models" / "checkpoints").mkdir(parents=True)
            with patch.dict(os.environ, {"EVAVO_SHARED_MODEL_ROOTS": str(root), "EVAVO_COMFYUI_MODEL_ROOTS": ""}, clear=False):
                first = comfyui_runtime.shared_model_configuration()
                (root / "models" / "loras").mkdir(parents=True)
                second = comfyui_runtime.shared_model_configuration()
            self.assertTrue(first["sha256"])
            self.assertTrue(second["sha256"])
            self.assertNotEqual(first["sha256"], second["sha256"])
            self.assertNotEqual(first["yaml"], second["yaml"])

    def test_process_identity_path_matching_rejects_unrelated_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            expected = Path(directory) / "ComfyUI" / "main.py"
            expected.parent.mkdir(parents=True)
            expected.write_text("# fixture\n", encoding="utf-8")
            matching = f'python "{expected}" --listen 127.0.0.1 --port 8188'
            unrelated = f'python "{Path(directory) / "other" / "main.py"}" --port 8188'
            self.assertTrue(comfyui_runtime._command_contains_path(matching, expected))
            self.assertFalse(comfyui_runtime._command_contains_path(unrelated, expected))

    def test_native_state_identity_uses_recorded_main_py(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            main_py = Path(directory) / "main.py"
            main_py.write_text("# fixture\n", encoding="utf-8")
            state = {"pid": 424242, "install": {"main_py": str(main_py)}}
            with patch.object(comfyui_runtime, "_process_command_line", return_value=f'python "{main_py}" --port 8188'):
                self.assertTrue(comfyui_runtime._native_state_identity_matches(state))
            with patch.object(comfyui_runtime, "_process_command_line", return_value="python unrelated.py"):
                self.assertFalse(comfyui_runtime._native_state_identity_matches(state))

    def test_comfyui_command_includes_evavo_extra_model_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            python = root / "python.exe"
            main_py = root / "main.py"
            config = root / "extra.yaml"
            install = comfyui_runtime.ComfyUIInstall(root=root, python=python, main_py=main_py, portable=False)
            command = install.command(extra_model_config=config)
            self.assertIn("--extra-model-paths-config", command)
            index = command.index("--extra-model-paths-config")
            self.assertEqual(command[index + 1], str(config))


if __name__ == "__main__":
    unittest.main(verbosity=2)
