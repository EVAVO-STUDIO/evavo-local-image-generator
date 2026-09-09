"""Shared explicit failure contract for unsupported legacy modalities."""

from __future__ import annotations

from typing import NoReturn


class UnsupportedGenerationError(NotImplementedError):
    """Raised when a retired/non-image modality is called in this repository."""

    def __init__(self, modality: str):
        self.modality = modality
        super().__init__(
            f"{modality} generation is not implemented by EVAVO Local Image Generator; "
            "use the dedicated EVAVO repository for that modality"
        )


def unsupported(modality: str) -> NoReturn:
    raise UnsupportedGenerationError(modality)
