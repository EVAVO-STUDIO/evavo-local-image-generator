"""Legacy audio-generation compatibility surface.

Audio generation is outside the verified scope of EVAVO Local Image Generator.
All methods fail explicitly without network, filesystem, or task-history side effects.
"""

from __future__ import annotations

from typing import Dict, Optional

from ._unsupported import unsupported


class AudioGenerator:
    def __init__(self, kokoro_endpoint: Optional[str] = None):
        self.endpoint = kokoro_endpoint
        self.task_type = "audio_generation"

    async def text_to_speech(self, text: str, voice: str = "default", language: str = "en") -> Dict:
        unsupported("audio/text-to-speech")

    async def generate_music(self, description: str, duration: float = 30.0, genre: Optional[str] = None) -> Dict:
        unsupported("audio/music")

    async def generate_sfx(self, description: str, duration: float = 2.0) -> Dict:
        unsupported("audio/sound-effects")


async def text_to_speech(text: str, **kwargs) -> Dict:
    return await AudioGenerator().text_to_speech(text, **kwargs)
