#!/usr/bin/env python3
"""Historical demo filename routed to explicit real EVAVO image generation.

The old demo wrote fake PNG/MP4 bytes and announced production readiness. This
compatibility entry point now uses the same canonical runtime as every other
image-generation interface and never fabricates output files.
"""

from legacy_image_cli import compatibility_main


if __name__ == "__main__":
    raise SystemExit(
        compatibility_main(
            default_project="autonomous-demo",
            description="Run an explicit real EVAVO native image-generation demo",
            repair_first=True,
        )
    )
