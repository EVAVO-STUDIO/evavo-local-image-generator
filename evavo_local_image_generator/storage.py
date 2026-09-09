"""Legacy in-memory storage compatibility helpers.

Current EVAVO image generation stores real downloaded outputs at explicit local
paths and records them through ``evavo_operations.TaskTracker``. This module is
retained only for older imports. It does not connect to BeeStation, write files,
or resolve historical ``bee://`` identifiers into live UNC paths.
"""

from __future__ import annotations

import hashlib
from typing import Dict, Optional


class BeeStorageClient:
    """Historical in-memory digest cache; not a production storage backend."""

    def __init__(self, storage_uri: str = "bee://primary/EVAVO/ImageGeneration"):
        self.storage_uri = str(storage_uri)
        self.digest_cache: Dict[str, str] = {}

    @staticmethod
    def compute_digest(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def save_file(self, content: bytes, filename: str) -> str:
        """Cache only the digest; ``content`` is deliberately not persisted."""
        digest = self.compute_digest(content)
        self.digest_cache[str(filename)] = digest
        return digest

    def verify_digest(self, filename: str, expected_digest: str) -> bool:
        return self.digest_cache.get(str(filename)) == expected_digest


def resolve_to_windows_path(bee_uri: str) -> Optional[str]:
    """Historical API retained without manufacturing a live storage path."""
    return None
