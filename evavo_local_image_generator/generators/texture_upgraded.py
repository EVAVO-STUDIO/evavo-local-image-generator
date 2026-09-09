"""Historical PBR-texture compatibility wrapper with explicit unsupported behavior."""

from __future__ import annotations

from ._unsupported import unsupported


class TextureGenerator:
    def __init__(self, endpoint: str | None = None):
        self.endpoint = endpoint

    async def generate(self, prompt: str, resolution: int = 2048) -> dict:
        unsupported("pbr-texture")
