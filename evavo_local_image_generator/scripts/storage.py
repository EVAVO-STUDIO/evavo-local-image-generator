"""Side-effect-free compatibility storage helpers.

The current EVAVO Local Image Generator does not require BeeStation or a
separate digest-bound storage service. This module is retained only so older
imports do not break. It performs no filesystem/network writes and must not be
treated as the authoritative generation history; use ``evavo_operations.TaskTracker``
for that.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class BeeStoragePath:
    """Legacy parser/formatter for historical ``bee://`` identifiers."""

    storage_type: str
    base_path: str
    subpath: str = ""

    def to_uri(self) -> str:
        suffix = f"/{self.subpath}" if self.subpath else ""
        return f"bee://{self.storage_type}/{self.base_path}{suffix}"

    @classmethod
    def from_uri(cls, uri: str) -> "BeeStoragePath":
        if not isinstance(uri, str) or not uri.startswith("bee://"):
            raise ValueError(f"Invalid bee:// URI: {uri}")
        parts = uri[6:].split("/", 2)
        if len(parts) < 2 or not parts[0] or not parts[1]:
            raise ValueError(f"Incomplete bee:// URI: {uri}")
        return cls(parts[0], parts[1], parts[2] if len(parts) > 2 else "")


class BeeStorageClient:
    """Legacy in-memory compatibility shim; no persistence or file transfer."""

    def __init__(self, base_uri: str = "bee://primary/EVAVO/ImageGeneration"):
        self.base_uri = base_uri.rstrip("/")
        self.base_path = BeeStoragePath.from_uri(self.base_uri)
        self.digest_cache: Dict[str, str] = {}
        self.records: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def compute_digest(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def resolve_uri(self, relative_path: str) -> str:
        value = str(relative_path).strip("/")
        return self.base_uri if not value else f"{self.base_uri}/{value}"

    def get_outputs_path(self) -> str:
        return self.resolve_uri("outputs")

    def get_models_path(self) -> str:
        return "bee://primary/EVAVO/AI/Models"

    def get_workflows_path(self) -> str:
        return self.resolve_uri("workflows")

    def get_project_path(self, project_name: str) -> str:
        return f"bee://primary/Projects/{str(project_name).strip('/')}"

    def record_generation(self, generation_data: Dict[str, Any]) -> None:
        """Keep legacy metadata in memory only; do not write hidden manifests."""
        task_id = str(generation_data.get("task_id") or generation_data.get("backend_task_id") or "unknown")
        self.records[task_id] = dict(generation_data)

    def save_file(self, content: bytes, filename: str) -> str:
        """Compatibility digest cache only; does not write ``content`` anywhere."""
        digest = self.compute_digest(content)
        self.digest_cache[str(filename)] = digest
        return digest

    def verify_digest(self, filename: str, expected_digest: str) -> bool:
        return self.digest_cache.get(str(filename)) == expected_digest


_storage_client: Optional[BeeStorageClient] = None


def get_storage_client() -> BeeStorageClient:
    """Return one process-local compatibility client without environment coupling."""
    global _storage_client
    if _storage_client is None:
        _storage_client = BeeStorageClient()
    return _storage_client
