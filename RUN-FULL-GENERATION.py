#!/usr/bin/env python3
"""Historical full-generation filename routed to the canonical EVAVO image stack."""

from legacy_image_cli import compatibility_main


if __name__ == "__main__":
    raise SystemExit(
        compatibility_main(
            default_project="full-generation",
            description="Verify/repair EVAVO and optionally run explicit native image generation",
            verify_first=True,
            repair_first=True,
        )
    )
