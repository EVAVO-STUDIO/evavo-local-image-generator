"""Offline contract tests for the Kokoro gateway fallback integration."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def _load_provider_module():
    path = ROOT / "kokoro-provider.py"
    spec = importlib.util.spec_from_file_location("evavo_kokoro_provider_adapter", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class KokoroGatewayProviderContractTests(unittest.TestCase):
    def test_provider_accepts_gateway_prompt_as_speech_text(self):
        module = _load_provider_module()
        self.assertEqual(module._speech_text({"prompt": "  High quality local speech.  "}), "High quality local speech.")

    def test_explicit_text_takes_priority_over_prompt(self):
        module = _load_provider_module()
        self.assertEqual(module._speech_text({"text": "spoken", "prompt": "fallback"}), "spoken")

    def test_nested_options_are_supported_for_voice_and_speed(self):
        module = _load_provider_module()
        request = {"prompt": "test", "options": {"voice": "af_heart", "speed": 0.98}}
        self.assertEqual(module._nested(request, "voice"), "af_heart")
        self.assertEqual(module._nested(request, "speed"), 0.98)

    def test_gateway_prefers_audio_studio_before_kokoro_fallback(self):
        source = (ROOT / "START-GATEWAY.ps1").read_text(encoding="utf-8-sig")
        audio_studio = source.index("Audio Studio provider:")
        kokoro = source.index("Kokoro speech provider fallback:")
        self.assertLess(audio_studio, kokoro)

    def test_gateway_kokoro_autodiscovery_is_loopback_only(self):
        source = (ROOT / "START-GATEWAY.ps1").read_text(encoding="utf-8-sig")
        self.assertIn('@("127.0.0.1", "localhost", "::1")', source)
        self.assertIn('/v1/audio/voices', source)
        self.assertIn('EVAVO_AUDIO_PROVIDER_ARGV', source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
