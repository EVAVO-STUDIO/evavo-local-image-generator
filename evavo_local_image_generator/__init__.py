"""
EVAVO Local Image Generator - Multi-modal AI generation bridge to BeeStation.

This module provides MCP server integration for image, video, audio, text,
particle, 3D model, and PBR texture generation using local ComfyUI, Ollama,
and Kokoro FastAPI backends.

Architecture:
- evavo-local-storage: BeeStation access via bee:// URIs
- evavo-local-compute: Digest-bound task execution and validation
- evavo-storage: Immutable milestone handoff and version control
- ComfyUI: Local inference engine (http://127.0.0.1:8188)
- Ollama: Local LLM backend (http://127.0.0.1:11434)
- Kokoro FastAPI: TTS service (http://127.0.0.1:8000)
"""

__version__ = "0.1.0"
__author__ = "EVAVO Platform"

from .mcp_server import EvavoLocalImageGeneratorMCPServer

__all__ = ["EvavoLocalImageGeneratorMCPServer"]
