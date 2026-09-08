"""
Multi-modal generation modules for EVAVO system.

Each generator implements the digest-bound task execution framework
for a specific generation type.

Generators:
- ImageGenerator: Text-to-image via ComfyUI
- VideoGenerator: Video generation and animation
- AudioGenerator: Audio synthesis and text-to-speech
- Model3DGenerator: 3D model and asset generation
- TextureGenerator: PBR texture generation
- ParticleGenerator: Particle system generation
"""

from evavo_local_image_generator.scripts.generate import ImageGenerator
from evavo_local_image_generator.generators.video import VideoGenerator
from evavo_local_image_generator.generators.audio import AudioGenerator
from evavo_local_image_generator.generators.model_3d import Model3DGenerator
from evavo_local_image_generator.generators.texture import TextureGenerator
from evavo_local_image_generator.generators.particles import ParticleGenerator

__all__ = [
    'ImageGenerator',
    'VideoGenerator', 
    'AudioGenerator',
    'Model3DGenerator',
    'TextureGenerator',
    'ParticleGenerator',
]
