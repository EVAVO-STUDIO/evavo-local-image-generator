#!/usr/bin/env python3
"""Cross-platform compatibility runner for the canonical EVAVO image stack."""

from legacy_image_cli import compatibility_main


if __name__ == "__main__":
    raise SystemExit(
        compatibility_main(
            default_project="linux-generation",
            description="Run explicit EVAVO native image generation without hardcoded mounted paths",
        )
    )
