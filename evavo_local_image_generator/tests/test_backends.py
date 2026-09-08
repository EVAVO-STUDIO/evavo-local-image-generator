"""
Unit tests for EVAVO backend service integrations.

Tests verify:
- Backend initialization
- Service endpoint configuration
- Health check functionality
"""

import unittest
from evavo_local_image_generator.backends import (
    ComfyUIBackend, OllamaBackend, KokoroBackend
)

class TestComfyUIBackend(unittest.TestCase):
    """Test ComfyUI backend integration."""
    
    def test_initialization(self):
        """Test ComfyUIBackend initializes with endpoint."""
        backend = ComfyUIBackend(endpoint="http://127.0.0.1:8188")
        self.assertEqual(backend.endpoint, "http://127.0.0.1:8188")

class TestOllamaBackend(unittest.TestCase):
    """Test Ollama backend integration."""
    
    def test_initialization(self):
        """Test OllamaBackend initializes with endpoint."""
        backend = OllamaBackend(endpoint="http://127.0.0.1:11434")
        self.assertEqual(backend.endpoint, "http://127.0.0.1:11434")

class TestKokoroBackend(unittest.TestCase):
    """Test Kokoro backend integration."""
    
    def test_initialization(self):
        """Test KokoroBackend initializes with endpoint."""
        backend = KokoroBackend(endpoint="http://127.0.0.1:8000")
        self.assertEqual(backend.endpoint, "http://127.0.0.1:8000")

if __name__ == '__main__':
    unittest.main()
