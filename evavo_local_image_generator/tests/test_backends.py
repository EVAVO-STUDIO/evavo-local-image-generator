"""Offline package tests for the current backend contract."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from evavo_local_image_generator.backends import ComfyUIBackend, KokoroBackend, OllamaBackend
from evavo_local_image_generator.backends.comfyui_backend import MODEL_LOADER_INPUTS

ROOT = Path(__file__).resolve().parents[2]


class ComfyUIBackendTests(unittest.TestCase):
    def test_explicit_endpoint_initialization(self) -> None:
        backend = ComfyUIBackend(endpoint="http://127.0.0.1:8188")
        self.assertEqual(backend.endpoint, "http://127.0.0.1:8188")

    def test_default_endpoint_is_loopback(self) -> None:
        env = os.environ.copy()
        env.pop("COMFYUI_ENDPOINT", None)
        env.pop("EVAVO_COMFYUI_ENDPOINT", None)
        with patch.dict(os.environ, env, clear=True):
            backend = ComfyUIBackend()
        self.assertEqual(backend.endpoint, "http://127.0.0.1:8188")

    def test_model_inventory_covers_current_loader_categories(self) -> None:
        expected = {
            "checkpoints",
            "loras",
            "vae",
            "controlnet",
            "diffusion_models",
            "text_encoders",
            "clip_vision",
            "upscale_models",
        }
        self.assertEqual(set(MODEL_LOADER_INPUTS), expected)

    def test_mcp_server_does_not_import_legacy_non_image_backends(self) -> None:
        source = (ROOT / "evavo_local_image_generator" / "mcp_server.py").read_text(encoding="utf-8")
        self.assertNotIn("OllamaBackend", source)
        self.assertNotIn("KokoroBackend", source)


class LegacyBackendCompatibilityTests(unittest.TestCase):
    def test_legacy_helpers_remain_importable_without_becoming_dependencies(self) -> None:
        ollama = OllamaBackend(endpoint="http://127.0.0.1:11434")
        kokoro = KokoroBackend(endpoint="http://127.0.0.1:8880")
        self.assertEqual(ollama.endpoint, "http://127.0.0.1:11434")
        self.assertEqual(kokoro.endpoint, "http://127.0.0.1:8880")


if __name__ == "__main__":
    unittest.main(verbosity=2)
