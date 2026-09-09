"""Backend adapters for EVAVO Local Image Generator.

`ComfyUIBackend` is the quality-first production adapter. The original
hardened transport implementation remains available as
`LegacyComfyUIBackend` for low-level compatibility and regression tests.

Ollama and Kokoro remain optional provider clients; neither is imported by the
image-only MCP server.
"""

from .comfyui_backend import ComfyUIBackend as LegacyComfyUIBackend
from .quality_comfyui_backend import QualityComfyUIBackend
from .ollama_backend import OllamaBackend
from .kokoro_backend import KokoroBackend

ComfyUIBackend = QualityComfyUIBackend

__all__ = [
    "ComfyUIBackend",
    "QualityComfyUIBackend",
    "LegacyComfyUIBackend",
    "OllamaBackend",
    "KokoroBackend",
]
