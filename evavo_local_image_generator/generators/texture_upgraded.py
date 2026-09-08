"""PBR texture generation"""

class TextureGenerator:
    def __init__(self, endpoint: str = "http://127.0.0.1:8890"):
        self.endpoint = endpoint

    async def generate(self, prompt: str, resolution: int = 2048) -> dict:
        """Generate PBR textures"""
        return {
            "status": "queued",
            "type": "texture",
            "prompt": prompt,
            "resolution": resolution,
        }
