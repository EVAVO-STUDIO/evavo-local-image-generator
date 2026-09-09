#!/usr/bin/env python3
"""Offline safety tests for EVAVO ComfyUI provisioning."""

from __future__ import annotations

import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
