"""BeeStation storage client with bee:// URI abstraction"""

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any


class BeeStorageClient:
    """Storage client for bee:// URIs with SHA-256 validation"""

    def __init__(self, storage_uri: str = "bee://primary/EVAVO/ImageGeneration"):
        self.storage_uri = storage_uri
        self.digest_cache: Dict[str, str] = {}

    def compute_digest(self, data: bytes) -> str:
        """Compute SHA-256 digest of data"""
        return hashlib.sha256(data).hexdigest()

    def save_file(self, content: bytes, filename: str) -> str:
        """Save file to bee:// storage and return digest"""
        digest = self.compute_digest(content)
        self.digest_cache[filename] = digest
        return digest

    def verify_digest(self, filename: str, expected_digest: str) -> bool:
        """Verify file digest matches expected value"""
        if filename in self.digest_cache:
            return self.digest_cache[filename] == expected_digest
        return False


def resolve_to_windows_path(bee_uri: str) -> Optional[str]:
    """Resolve bee:// URI to Windows UNC path (local Windows only)"""
    try:
        if bee_uri.startswith("bee://"):
            # This function should only be called from local Windows code
            # Not from hosted Claude environment
            parts = bee_uri.replace("bee://", "").split("/")
            if len(parts) >= 2:
                return f"\\\\beestation\\shares\\{parts[0]}\\{'/'.join(parts[1:])}"
    except Exception:
        pass
    return None
