"""
Backend service integrations for EVAVO multi-modal generation.

Supported backends:
- ComfyUI: Local image generation (port 8188)
- Ollama: Local LLM inference (port 11434)
- Kokoro: Text-to-speech service (port 8000)
- FFmpeg: Video encoding and processing
- Blender: 3D model generation and rendering
"""

from .comfyui_backend import ComfyUIBackend
from .ollama_backend import OllamaBackend
from .kokoro_backend import KokoroBackend

__all__ = ['ComfyUIBackend', 'OllamaBackend', 'KokoroBackend']
