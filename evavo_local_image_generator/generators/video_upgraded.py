"""Historical video compatibility wrapper with explicit unsupported behavior."""

from __future__ import annotations

from ._unsupported import unsupported


class VideoGenerator:
    def __init__(self, endpoint: str | None = None):
        self.endpoint = endpoint

    async def generate(self, prompt: str, duration: float = 10.0, fps: int = 24) -> dict:
        unsupported("video")
