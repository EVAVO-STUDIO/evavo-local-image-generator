"""EVAVO Local Image Generator package.

The verified generation backend is native ComfyUI. `BeeStorageClient` remains
available for backwards compatibility with older package callers but is not
required by the current MCP/CLI image pipeline.
"""

__version__ = "1.1.0"

from .backends import ComfyUIBackend
from .storage import BeeStorageClient

__all__ = ["ComfyUIBackend", "BeeStorageClient", "__version__"]
