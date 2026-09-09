"""Legacy particle-generation compatibility surface.

Particle generation is outside the verified scope of EVAVO Local Image Generator.
All methods fail explicitly without network, filesystem, or task-history side effects.
"""

from __future__ import annotations

from typing import Dict

from ._unsupported import unsupported


class ParticleGenerator:
    def __init__(self):
        self.task_type = "particle_generation"

    async def generate_particle_system(
        self,
        description: str,
        particle_count: int = 10000,
        duration: float = 5.0,
    ) -> Dict:
        unsupported("particle-system")


async def generate_particles(description: str, **kwargs) -> Dict:
    return await ParticleGenerator().generate_particle_system(description, **kwargs)
