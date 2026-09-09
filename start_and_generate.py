#!/usr/bin/env python3
"""Historical start-and-generate filename routed to canonical EVAVO lifecycle."""

from legacy_image_cli import compatibility_main


if __name__ == "__main__":
    raise SystemExit(
        compatibility_main(
            default_project="start-and-generate",
            description="Repair/start native ComfyUI and run explicit EVAVO image generation",
            repair_first=True,
        )
    )
