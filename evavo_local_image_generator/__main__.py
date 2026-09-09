"""Validated package entrypoint for EVAVO MCP image generation.

Usage:
    python -m evavo_local_image_generator
    python -m evavo_local_image_generator.mcp_entry

The production entrypoint validates owner MCP filesystem authority before
starting the shared MCP server implementation.
"""

from .mcp_entry import main


if __name__ == "__main__":
    main()
