"""Legacy texture-generation compatibility surface.

Dedicated PBR texture generation is outside the verified scope of EVAVO Local
Image Generator. All methods fail explicitly without network, filesystem, or
task-history side effects.
"""

from __future__ import annotations

from typing import Dict

from ._unsupported import unsupported


class TextureGenerator:
    def __init__(self):
        self.task_type = "texture_generation"

    async def generate_texture(
        self,
        description: str,
        resolution: int = 2048,
        texture_type: str = "diffuse",
    ) -> Dict:
        unsupported("pbr-texture")

    async def generate_pbr_set(self, description: str, resolution: int = 2048) -> Dict:
        unsupported("pbr-texture-set")


async def generate_texture(description: str, **kwargs) -> Dict:
    return await TextureGenerator().generate_texture(description, **kwargs)
