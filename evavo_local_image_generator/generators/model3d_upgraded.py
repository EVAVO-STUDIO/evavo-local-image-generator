"""Historical 3D compatibility wrapper with explicit unsupported behavior."""

from __future__ import annotations

from ._unsupported import unsupported


class Model3DGenerator:
    def __init__(self, endpoint: str | None = None):
        self.endpoint = endpoint

    async def generate(self, prompt: str, format: str = "obj") -> dict:
        unsupported("3d-model")
