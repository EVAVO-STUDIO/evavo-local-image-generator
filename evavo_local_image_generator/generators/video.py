"""Legacy video-generation compatibility surface.

Video generation is outside the verified scope of EVAVO Local Image Generator.
All methods fail explicitly without network, filesystem, or task-history side effects.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from ._unsupported import unsupported


class VideoGenerator:
    def __init__(self, comfyui_endpoint: Optional[str] = None):
        self.endpoint = comfyui_endpoint
        self.task_type = "video_generation"

    async def generate_video(
        self,
        prompt: str,
        duration: float = 5.0,
        fps: int = 24,
        negative_prompt: Optional[str] = None,
    ) -> Dict:
        unsupported("video")

    async def interpolate_frames(self, frame_paths: List[str], interpolation_factor: int = 2) -> Dict:
        unsupported("video/frame-interpolation")


async def generate_video(prompt: str, **kwargs) -> Dict:
    return await VideoGenerator().generate_video(prompt, **kwargs)
