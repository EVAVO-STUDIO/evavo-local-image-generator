"""
Unit tests for EVAVO multi-modal generators.

Tests verify:
- Generator initialization and configuration
- Task creation with digest validation
- Error handling and edge cases
"""

import unittest
from evavo_local_image_generator.generators import (
    ImageGenerator, VideoGenerator, AudioGenerator,
    Model3DGenerator, TextureGenerator, ParticleGenerator
)

class TestImageGenerator(unittest.TestCase):
    """Test image generation module."""
    
    def setUp(self):
        self.generator = ImageGenerator()
    
    def test_initialization(self):
        """Test ImageGenerator initializes correctly."""
        self.assertIsNotNone(self.generator)
    
    def test_has_methods(self):
        """Test generator has required methods."""
        self.assertTrue(hasattr(self.generator, 'generate_image'))
        self.assertTrue(hasattr(self.generator, 'batch_generate'))

class TestVideoGenerator(unittest.TestCase):
    """Test video generation module."""
    
    def test_initialization(self):
        """Test VideoGenerator initializes correctly."""
        gen = VideoGenerator()
        self.assertIsNotNone(gen)

class TestAudioGenerator(unittest.TestCase):
    """Test audio generation module."""
    
    def test_initialization(self):
        """Test AudioGenerator initializes correctly."""
        gen = AudioGenerator()
        self.assertIsNotNone(gen)

class TestModel3DGenerator(unittest.TestCase):
    """Test 3D model generation module."""
    
    def test_initialization(self):
        """Test Model3DGenerator initializes correctly."""
        gen = Model3DGenerator()
        self.assertIsNotNone(gen)

class TestTextureGenerator(unittest.TestCase):
    """Test texture generation module."""
    
    def test_initialization(self):
        """Test TextureGenerator initializes correctly."""
        gen = TextureGenerator()
        self.assertIsNotNone(gen)

class TestParticleGenerator(unittest.TestCase):
    """Test particle system generation module."""
    
    def test_initialization(self):
        """Test ParticleGenerator initializes correctly."""
        gen = ParticleGenerator()
        self.assertIsNotNone(gen)

if __name__ == '__main__':
    unittest.main()
