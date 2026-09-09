#!/usr/bin/env python3
"""Historical execute-generation filename routed to canonical EVAVO image stack."""

from legacy_image_cli import compatibility_main


if __name__ == "__main__":
    raise SystemExit(
        compatibility_main(
            default_project="execute-generation",
            description="Run explicit real EVAVO native image generation",
        )
    )
