"""Offline regressions for EVAVO speech technical diagnostics."""

from __future__ import annotations

import math
import struct
import tempfile
import unittest
import wave
from pathlib import Path

from evavo_local_image_generator.audio_quality import speech_quality_checks, wav_diagnostics


class AudioQualityTests(unittest.TestCase):
    def _write_wav(self, path: Path, *, duration: float = 2.0, sample_rate: int = 24000, amplitude: float = 0.2, lead: float = 0.1, tail: float = 0.1) -> None:
        frames = int(duration * sample_rate)
        lead_frames = int(lead * sample_rate)
        tail_frames = int(tail * sample_rate)
        values = []
        for index in range(frames):
            if index < lead_frames or index >= frames - tail_frames:
                value = 0.0
            else:
                value = amplitude * math.sin(2.0 * math.pi * 220.0 * index / sample_rate)
            values.append(int(max(-1.0, min(1.0, value)) * 32767))
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(sample_rate)
            handle.writeframes(b"".join(struct.pack("<h", value) for value in values))

    def test_good_speech_fixture_passes_conservative_qc(self):
        with tempfile.TemporaryDirectory() as value:
            path = Path(value) / "speech.wav"
            self._write_wav(path, duration=10.0, lead=0.2, tail=0.3)
            metrics = wav_diagnostics(path, word_count=30)
            checks = speech_quality_checks(metrics)
            self.assertTrue(checks["ok"], checks)
            self.assertEqual(metrics["sample_rate_hz"], 24000)
            self.assertEqual(metrics["bit_depth"], 16)
            self.assertAlmostEqual(metrics["effective_wpm"], 180.0, places=1)
            self.assertLess(metrics["clipping_pct"], 0.1)
            self.assertLess(metrics["leading_silence_s"], 1.5)
            self.assertLess(metrics["trailing_silence_s"], 2.0)

    def test_truncated_audio_fails(self):
        with tempfile.TemporaryDirectory() as value:
            path = Path(value) / "short.wav"
            self._write_wav(path, duration=0.2, lead=0.0, tail=0.0)
            checks = speech_quality_checks(wav_diagnostics(path, word_count=20))
            self.assertFalse(checks["ok"])
            self.assertTrue(any("duration" in item for item in checks["errors"]))

    def test_implausible_wpm_fails(self):
        with tempfile.TemporaryDirectory() as value:
            path = Path(value) / "fast.wav"
            self._write_wav(path, duration=1.0, lead=0.0, tail=0.0)
            checks = speech_quality_checks(wav_diagnostics(path, word_count=20))
            self.assertFalse(checks["ok"])
            self.assertTrue(any("speaking rate" in item for item in checks["errors"]))

    def test_excess_silence_is_warning_not_fake_failure(self):
        with tempfile.TemporaryDirectory() as value:
            path = Path(value) / "silence.wav"
            self._write_wav(path, duration=8.0, lead=2.0, tail=2.2)
            metrics = wav_diagnostics(path, word_count=20)
            checks = speech_quality_checks(metrics)
            self.assertTrue(checks["ok"], checks)
            self.assertGreaterEqual(checks["warning_count"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
