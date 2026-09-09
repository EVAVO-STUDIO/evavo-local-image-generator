"""Offline tests ensuring non-image compatibility APIs never fake success."""

from __future__ import annotations

import asyncio
import unittest

from evavo_local_image_generator.generators._unsupported import UnsupportedGenerationError
from evavo_local_image_generator.generators.audio import AudioGenerator as AudioGeneratorBase
from evavo_local_image_generator.generators.audio_upgraded import AudioGenerator as AudioGeneratorUpgraded
from evavo_local_image_generator.generators.model_3d import Model3DGenerator as Model3DGeneratorBase
from evavo_local_image_generator.generators.model3d_upgraded import Model3DGenerator as Model3DGeneratorUpgraded
from evavo_local_image_generator.generators.particles import ParticleGenerator as ParticleGeneratorBase
from evavo_local_image_generator.generators.particle_upgraded import ParticleGenerator as ParticleGeneratorUpgraded
from evavo_local_image_generator.generators.texture import TextureGenerator as TextureGeneratorBase
from evavo_local_image_generator.generators.texture_upgraded import TextureGenerator as TextureGeneratorUpgraded
from evavo_local_image_generator.generators.video import VideoGenerator as VideoGeneratorBase
from evavo_local_image_generator.generators.video_upgraded import VideoGenerator as VideoGeneratorUpgraded


class UnsupportedModalityTests(unittest.TestCase):
    def assert_unsupported(self, awaitable, modality_fragment: str) -> None:
        with self.assertRaises(UnsupportedGenerationError) as caught:
            asyncio.run(awaitable)
        self.assertIn(modality_fragment, str(caught.exception))
        self.assertIn("dedicated EVAVO repository", str(caught.exception))

    def test_audio_base_and_upgraded_are_explicitly_unsupported(self) -> None:
        self.assert_unsupported(AudioGeneratorBase().text_to_speech("hello"), "audio")
        self.assert_unsupported(AudioGeneratorBase().generate_music("ambient"), "audio")
        self.assert_unsupported(AudioGeneratorBase().generate_sfx("impact"), "audio")
        self.assert_unsupported(AudioGeneratorUpgraded().synthesize_tts("hello"), "audio")
        self.assert_unsupported(AudioGeneratorUpgraded().generate_music("ambient"), "audio")

    def test_video_base_and_upgraded_are_explicitly_unsupported(self) -> None:
        self.assert_unsupported(VideoGeneratorBase().generate_video("scene"), "video")
        self.assert_unsupported(VideoGeneratorBase().interpolate_frames(["a.png", "b.png"]), "video")
        self.assert_unsupported(VideoGeneratorUpgraded().generate("scene"), "video")

    def test_3d_base_and_upgraded_are_explicitly_unsupported(self) -> None:
        self.assert_unsupported(Model3DGeneratorBase().generate_model("chair"), "3d-model")
        self.assert_unsupported(Model3DGeneratorBase().refine_model("chair.glb"), "3d-model")
        self.assert_unsupported(Model3DGeneratorUpgraded().generate("chair"), "3d-model")

    def test_particle_base_and_upgraded_are_explicitly_unsupported(self) -> None:
        self.assert_unsupported(ParticleGeneratorBase().generate_particle_system("sparks"), "particle-system")
        self.assert_unsupported(ParticleGeneratorUpgraded().generate("sparks"), "particle-system")

    def test_texture_base_and_upgraded_are_explicitly_unsupported(self) -> None:
        self.assert_unsupported(TextureGeneratorBase().generate_texture("stone"), "pbr-texture")
        self.assert_unsupported(TextureGeneratorBase().generate_pbr_set("stone"), "pbr-texture")
        self.assert_unsupported(TextureGeneratorUpgraded().generate("stone"), "pbr-texture")

    def test_no_compatibility_generator_contains_fake_queued_result(self) -> None:
        import inspect

        modules = (
            AudioGeneratorBase,
            AudioGeneratorUpgraded,
            VideoGeneratorBase,
            VideoGeneratorUpgraded,
            Model3DGeneratorBase,
            Model3DGeneratorUpgraded,
            ParticleGeneratorBase,
            ParticleGeneratorUpgraded,
            TextureGeneratorBase,
            TextureGeneratorUpgraded,
        )
        for cls in modules:
            source = inspect.getsource(cls)
            with self.subTest(cls=cls.__name__, module=cls.__module__):
                self.assertNotIn('"status": "queued"', source)
                self.assertNotIn("'status': 'queued'", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
