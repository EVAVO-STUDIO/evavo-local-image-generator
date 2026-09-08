"""Minimal Kokoro FastAPI backend integration."""

from __future__ import annotations

import urllib.error
import urllib.request
from typing import Optional


class KokoroBackend:
    def __init__(self, endpoint: Optional[str] = None):
        self.endpoint = (endpoint or "http://127.0.0.1:8000").rstrip("/")

    def health_check(self) -> bool:
        for path in ("/health", "/docs", "/"):
            try:
                with urllib.request.urlopen(f"{self.endpoint}{path}", timeout=3.0) as response:
                    if 200 <= getattr(response, "status", 200) < 500:
                        return True
            except (OSError, urllib.error.URLError, TimeoutError):
                continue
        return False

    def __repr__(self) -> str:
        return f"KokoroBackend(endpoint={self.endpoint!r})"
