"""
BeeStation storage integration via evavo-local-storage bee:// URIs.

This module handles all interaction with BeeStation network storage through
the bee:// URI abstraction layer managed by evavo-local-storage. Never access
Windows paths directly; use bee:// URIs to ensure proper SMB/CIFS handling
and digest-bound task security.
"""

import os
import json
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime


@dataclass
class BeeStoragePath:
    """Represents a bee:// URI path component."""
    storage_type: str  # primary, backup, etc.
    base_path: str    # EVAVO/ImageGeneration, EVAVO/AI/Models, etc.
    subpath: str      # outputs, workflows, etc.
    
    def to_uri(self) -> str:
        """Convert to bee:// URI format."""
        return f"bee://{self.storage_type}/{self.base_path}/{self.subpath}"
    
    @classmethod
    def from_uri(cls, uri: str) -> "BeeStoragePath":
        """Parse bee:// URI into components."""
        if not uri.startswith("bee://"):
            raise ValueError(f"Invalid bee:// URI: {uri}")
        
        parts = uri[6:].split("/", 2)
        if len(parts) < 2:
            raise ValueError(f"Incomplete bee:// URI: {uri}")
        
        storage_type = parts[0]
        base_path = parts[1]
        subpath = parts[2] if len(parts) > 2 else ""
        
        return cls(storage_type, base_path, subpath)


class BeeStorageClient:
    """
    Client for interacting with BeeStation via evavo-local-storage.
    
    This is a placeholder that interfaces with evavo-local-storage APIs
    to handle actual file operations. In production, this would call the
    evavo-local-storage service APIs.
    """
    
    def __init__(self, base_uri: str = "bee://primary/EVAVO/ImageGeneration"):
        """Initialize storage client with base URI."""
        self.base_uri = base_uri
        self.base_path = BeeStoragePath.from_uri(base_uri)
        self._session_id = self._generate_session_id()
        self._manifest_path = Path.home() / ".evavo" / "local-image-generator" / "manifest.json"
        self._ensure_manifest_dir()
    
    def _generate_session_id(self) -> str:
        """Generate unique session ID for digest-bound operations."""
        timestamp = datetime.utcnow().isoformat()
        return hashlib.sha256(timestamp.encode()).hexdigest()[:16]
    
    def _ensure_manifest_dir(self) -> None:
        """Ensure manifest directory exists."""
        self._manifest_path.parent.mkdir(parents=True, exist_ok=True)
    
    def resolve_uri(self, relative_path: str) -> str:
        """
        Resolve a relative path within the base storage location.
        
        Args:
            relative_path: Path relative to storage base (e.g., "outputs/image_001.png")
            
        Returns:
            Full bee:// URI
        """
        return f"{self.base_uri}/{relative_path}"
    
    def get_outputs_path(self) -> str:
        """Get the outputs directory URI."""
        return self.resolve_uri("outputs")
    
    def get_models_path(self) -> str:
        """Get the AI models directory URI."""
        return "bee://primary/EVAVO/AI/Models"
    
    def get_workflows_path(self) -> str:
        """Get the workflows directory URI."""
        return self.resolve_uri("workflows")
    
    def record_generation(self, generation_data: Dict[str, Any]) -> None:
        """
        Record a generation task in the manifest for digest-bound validation.
        
        Args:
            generation_data: Generation parameters and results
        """
        manifest = self._load_manifest()
        
        task_id = generation_data.get("task_id", self._session_id)
        manifest["tasks"][task_id] = {
            "timestamp": datetime.utcnow().isoformat(),
            "data": generation_data,
            "digest": self._compute_digest(generation_data)
        }
        
        self._save_manifest(manifest)
    
    def _load_manifest(self) -> Dict[str, Any]:
        """Load or initialize the manifest."""
        if self._manifest_path.exists():
            with open(self._manifest_path, 'r') as f:
                return json.load(f)
        
        return {
            "version": "1.0",
            "created": datetime.utcnow().isoformat(),
            "session_id": self._session_id,
            "tasks": {}
        }
    
    def _save_manifest(self, manifest: Dict[str, Any]) -> None:
        """Save manifest to disk."""
        with open(self._manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)
    
    def _compute_digest(self, data: Dict[str, Any]) -> str:
        """Compute SHA-256 digest of data for validation."""
        data_str = json.dumps(data, sort_keys=True)
        return hashlib.sha256(data_str.encode()).hexdigest()
    
    def get_project_path(self, project_name: str) -> str:
        """Get the path for a named project."""
        return f"bee://primary/Projects/{project_name}"


# Global storage client instance
_storage_client: Optional[BeeStorageClient] = None


def get_storage_client() -> BeeStorageClient:
    """Get or create the global storage client."""
    global _storage_client
    if _storage_client is None:
        storage_uri = os.getenv(
            "EVAVO_LOCAL_IMAGE_GENERATOR_STORAGE",
            "bee://primary/EVAVO/ImageGeneration"
        )
        _storage_client = BeeStorageClient(storage_uri)
    return _storage_client
