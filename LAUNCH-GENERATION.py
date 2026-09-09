#!/usr/bin/env python3
"""Historical launch-generation filename routed to canonical EVAVO image stack."""

from legacy_image_cli import compatibility_main


if __name__ == "__main__":
    raise SystemExit(
        compatibility_main(
            default_project="launch-generation",
            description="Repair/start native ComfyUI and run explicit EVAVO image generation",
            repair_first=True,
        )
    )
