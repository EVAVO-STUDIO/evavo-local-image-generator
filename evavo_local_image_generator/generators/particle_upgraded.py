"""Particle system generation"""

class ParticleGenerator:
    def __init__(self, endpoint: str = "http://127.0.0.1:8891"):
        self.endpoint = endpoint

    async def generate(self, prompt: str, engine: str = "godot") -> dict:
        """Generate particle system"""
        return {
            "status": "queued",
            "type": "particle",
            "prompt": prompt,
            "engine": engine,
        }
