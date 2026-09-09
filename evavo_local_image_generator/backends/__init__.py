"""Backend adapters for EVAVO Local Image Generator.

Production generation in this repository is backed by :class:`ComfyUIBackend`.
`OllamaBackend` and `KokoroBackend` remain importable only for source
compatibility with older callers; they are not dependencies of the verified
image runtime and are not exposed by the MCP server.
"""

from .comfyui_backend import ComfyUIBackend
from .ollama_backend import OllamaBackend
from .kokoro_backend import KokoroBackend

__all__ = ["ComfyUIBackend", "OllamaBackend", "KokoroBackend"]
