"""Historical audio compatibility wrapper with explicit unsupported behavior."""

from __future__ import annotations

from ._unsupported import unsupported


class AudioGenerator:
    def __init__(self, kokoro_endpoint: str | None = None):
        self.kokoro_endpoint = kokoro_endpoint

    async def synthesize_tts(self, text: str, voice: str = "default") -> dict:
        unsupported("audio/text-to-speech")

    async def generate_music(self, prompt: str, duration: float = 30.0) -> dict:
        unsupported("audio/music")
