"""Legacy 3D-generation compatibility surface.

3D generation is outside the verified scope of EVAVO Local Image Generator.
All methods fail explicitly without network, filesystem, or task-history side effects.
"""

from __future__ import annotations

from typing import Dict, Literal, Optional

from ._unsupported import unsupported


class Model3DGenerator:
    def __init__(self):
        self.task_type = "3d_model_generation"

    async def generate_model(
        self,
        prompt: str,
        format: Literal["gltf", "obj", "usd", "glb"] = "gltf",
        negative_prompt: Optional[str] = None,
    ) -> Dict:
        unsupported("3d-model")

    async def refine_model(self, model_path: str, iterations: int = 10) -> Dict:
        unsupported("3d-model/refinement")


async def generate_model(prompt: str, **kwargs) -> Dict:
    return await Model3DGenerator().generate_model(prompt, **kwargs)
