"""
Entry point for running evavo-local-image-generator as a module.

Usage:
    python -m evavo_local_image_generator
    python -m evavo_local_image_generator.mcp_server
"""

import sys
from .mcp_server import main

if __name__ == "__main__":
    main()
