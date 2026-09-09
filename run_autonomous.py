#!/usr/bin/env python3
"""Historical autonomous filename routed to the canonical EVAVO image stack."""

from legacy_image_cli import compatibility_main


if __name__ == "__main__":
    raise SystemExit(
        compatibility_main(
            default_project="autonomous",
            description="Repair/start native ComfyUI and run explicit EVAVO image generation",
            repair_first=True,
        )
    )
