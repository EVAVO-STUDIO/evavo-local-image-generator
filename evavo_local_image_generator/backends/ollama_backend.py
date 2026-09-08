"""Minimal Ollama backend integration."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Optional


class OllamaBackend:
    def __init__(self, endpoint: Optional[str] = None):
        self.endpoint = (endpoint or "http://127.0.0.1:11434").rstrip("/")

    def health_check(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.endpoint}/api/tags", timeout=3.0) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return isinstance(payload, dict)
        except (OSError, urllib.error.URLError, json.JSONDecodeError, TimeoutError):
            return False

    def __repr__(self) -> str:
        return f"OllamaBackend(endpoint={self.endpoint!r})"
