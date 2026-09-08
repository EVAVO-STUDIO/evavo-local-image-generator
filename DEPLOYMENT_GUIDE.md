# EVAVO Local Image Generator - Deployment Guide

## Project Status

### Completed Components ✓
- **Core Package Structure**: Properly organized Python module (evavo_local_image_generator)
- **MCP Server**: Full MCP protocol implementation with STDIO handler
- **Digest-Bound Tasks**: SHA-256 hash validation framework for secure execution
- **Image Generation**: Text-to-image via ComfyUI backend (implemented)
- **BeeStation Storage**: bee:// URI abstraction for network storage
- **Backend Adapters**: Service adapters for ComfyUI, Ollama, Kokoro
- **Test Infrastructure**: Unit test framework and health checks
- **Documentation**: Comprehensive README, CLAUDE.md, task manifest
- **Git Repository**: Properly initialized with 2 commits, ready for remotes

### Framework Ready Components 🔄
- **Video Generation**: Framework ready, workflow implementation pending
- **Audio Generation**: Framework ready, TTS and music synthesis pending
- **3D Model Generation**: Framework ready, synthesis engine pending
- **Texture Generation**: Framework ready, algorithm pending
- **Particle Systems**: Framework ready, physics engine pending

## Prerequisites

### Local Services Required
- **ComfyUI**: Running on `http://127.0.0.1:8188`
- **Ollama**: Running on `http://127.0.0.1:11434`
- **Kokoro**: Text-to-speech service on `http://127.0.0.1:8000`

### Python Environment
- Python 3.8+
- Virtual environment (.venv) configured
- Dependencies installed: `pip install -r requirements.txt`

### Storage
- **BeeStation**: Synology NAS with EVAVO storage configuration
- **bee:// URIs**: Configured for logical storage path abstraction

## Installation & Setup

```bash
# Navigate to repository
cd C:\Gitrepos\evavo-local-image-generator

# Activate virtual environment
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux

# Verify package installation
python -m evavo_local_image_generator --help
```

## Running Tests

```bash
# Run all tests
python -m pytest evavo_local_image_generator/tests/

# Run specific test module
python -m pytest evavo_local_image_generator/tests/test_generators.py

# Run health check
python -m evavo_local_image_generator.tests.health_check
```

## MCP Server Integration

### Configuration
The MCP server is configured in `.mcp.json`:
```json
{
  "mcpServers": {
    "evavo-local-image-generator": {
      "command": "./.venv/Scripts/python.exe",
      "args": ["-m", "evavo_local_image_generator.mcp_server"],
      "env": {
        "EVAVO_LOCAL_IMAGE_GENERATOR_MODE": "production",
        "EVAVO_LOCAL_IMAGE_GENERATOR_STORAGE": "bee://primary/EVAVO/ImageGeneration",
        "EVAVO_COMFYUI_ENDPOINT": "http://127.0.0.1:8188",
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
```

### Starting the Server
```bash
python -m evavo_local_image_generator.mcp_server
```

## API Usage

### Image Generation (Implemented)
```python
from evavo_local_image_generator.scripts.generate import ImageGenerator

generator = ImageGenerator()
result = await generator.generate_image(
    prompt="A serene mountain landscape at sunset",
    negative_prompt="blurry, low quality"
)
```

### Video Generation (Framework Ready)
```python
from evavo_local_image_generator.generators import VideoGenerator

generator = VideoGenerator()
result = await generator.generate_video(
    prompt="A spinning galaxy",
    duration=5.0,
    fps=24
)
```

### Audio Generation (Framework Ready)
```python
from evavo_local_image_generator.generators import AudioGenerator

generator = AudioGenerator()
result = await generator.text_to_speech(
    text="Hello, EVAVO system",
    voice="default"
)
```

## Next Steps

1. **Remote Configuration**: Configure git remote and push to repository
2. **Implement Video Workflows**: Create ComfyUI workflows for video generation
3. **TTS Integration**: Complete Kokoro text-to-speech implementation
4. **3D Asset Generation**: Integrate 3D model generation engine
5. **PBR Texture System**: Implement texture generation algorithm
6. **Particle Physics**: Add particle system simulation
7. **Integration Tests**: Create end-to-end testing suite
8. **CI/CD Pipeline**: Set up automated testing and deployment

## Troubleshooting

### ComfyUI Not Responding
```bash
# Check service health
python -c "from evavo_local_image_generator.tests.health_check import print_health_report; print_health_report()"
```

### Virtual Environment Issues
```bash
# Recreate virtual environment
rm -rf .venv
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
```

### Index Lock Issues (Git)
The mounted Windows folder may have persistent git index locks. Workaround:
```bash
# Use git commands with fresh operations
git status  # Should eventually clear
```

## Architecture Constraints

1. **Never use Windows paths directly**: Always use bee:// URI abstraction
2. **Digest-bound execution**: All task execution requires SHA-256 hash validation
3. **Immutable storage**: Use evavo-storage for canonical artifact versioning
4. **Service abstraction**: Backend access only through adapter classes

## Support & Documentation

- **README.md**: Complete API reference and integration guide
- **CLAUDE.md**: Operating notes and infrastructure patterns
- **evavo-repository-task-manifest.json**: Digest-bound task definitions
- **health_check.py**: Service availability validation
