#!/usr/bin/env python3
"""Historical generation filename routed to the canonical EVAVO image stack."""

from legacy_image_cli import compatibility_main


if __name__ == "__main__":
    raise SystemExit(
        compatibility_main(
            default_project="run-generation",
            description="Repair EVAVO if needed and run explicit native image generation",
            repair_first=True,
        )
    )
