"""Historical particle compatibility wrapper with explicit unsupported behavior."""

from __future__ import annotations

from ._unsupported import unsupported


class ParticleGenerator:
    def __init__(self, endpoint: str | None = None):
        self.endpoint = endpoint

    async def generate(self, prompt: str, engine: str = "godot") -> dict:
        unsupported("particle-system")
