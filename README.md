# EVAVO Local Image Generator

Multi-modal AI generation bridge for the EVAVO platform. Provides unified interface for image, video, audio, text, particle, 3D model, and PBR texture generation using local ComfyUI, Ollama, and Kokoro FastAPI backends.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ evavo-local-image-generator (This repo)                     │
│ ├─ MCP Server (evavo_local_image_generator.mcp_server)      │
│ ├─ Generation (evavo_local_image_generator.scripts.generate)│
│ ├─ Storage Integration (scripts.storage)                    │
│ └─ Workflows (scripts.workflows)                            │
└─────────────────────────────────────────────────────────────┘
          ↓                              ↓                      ↓
┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────┐
│ evavo-local-storage  │  │ evavo-local-compute  │  │  evavo-storage   │
│ (BeeStation access   │  │ (Digest-bound tasks) │  │ (Immutable milestones)
│  via bee:// URIs)    │  │                      │  │                  │
└──────────────────────┘  └──────────────────────┘  └──────────────────┘
          ↓
   //beestation/shares (Synology NAS)
   ├── EVAVO/ImageGeneration/
   │   ├── outputs/
   │   ├── workflows/
   │   └── models/
   ├── AI/Models/
   └── Projects/
```

## Features

- **Multi-Modal Generation**: Images, video, audio, text, particles, 3D models, PBR textures
- **Local Inference**: ComfyUI, Ollama, Kokoro FastAPI on Windows workstation
- **BeeStation Integration**: Network storage via bee:// URI abstraction
- **Digest-Bound Execution**: Secure task validation through evavo-local-compute
- **Immutable Milestones**: Version control via evavo-storage handoff
- **MCP Protocol**: Model Context Protocol for Claude integration

## Storage Architecture

All file operations use **bee:// URIs** managed by evavo-local-storage. Never access Windows paths directly.

### Storage Paths

```
bee://primary/EVAVO/ImageGeneration/          - Primary image generation directory
  ├── outputs/                                 - Generated images and metadata
  ├── workflows/                               - ComfyUI workflow definitions
  └── models/                                  - Local model checkpoints

bee://primary/EVAVO/AI/Models/                 - Shared AI model storage
  ├── diffusion/                               - Stable Diffusion checkpoints
  ├── upscalers/                               - Super-resolution models
  └── lora/                                    - LoRA fine-tuning weights

bee://primary/Projects/<project-name>/        - Project-specific outputs
```

## Installation

```bash
# Clone repository
git clone https://github.com/evavo/evavo-local-image-generator.git
cd evavo-local-image-generator

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Usage

### As MCP Server

Configure in your Claude Code or MCP client:

```json
{
  "mcpServers": {
    "evavo-local-image-generator": {
      "command": "./.venv/Scripts/python.exe",
      "args": ["-m", "evavo_local_image_generator.mcp_server"],
      "env": {
        "EVAVO_LOCAL_IMAGE_GENERATOR_MODE": "production",
        "EVAVO_LOCAL_IMAGE_GENERATOR_STORAGE": "bee://primary/EVAVO/ImageGeneration",
        "EVAVO_COMFYUI_ENDPOINT": "http://127.0.0.1:8188"
      }
    }
  }
}
```

### Programmatic Usage

```python
from evavo_local_image_generator.scripts.generate import generate_images
import asyncio

# Generate batch of images
prompts = [
    "a serene mountain landscape at sunset",
    "a futuristic city skyline at night",
    "a cozy cabin in the forest"
]

results = asyncio.run(generate_images(
    prompts=prompts,
    output_project="landscapes",
    steps=20,
    width=768,
    height=512
))

for result in results:
    print(f"Generated: {result['task_id']}")
    print(f"Storage URI: {result['storage_uri']}")
```

## API Reference

### Tools

#### `generate_image`
Generate a single image from a text prompt.

**Parameters:**
- `prompt` (string, required): Text prompt for generation
- `negative_prompt` (string): Features to avoid
- `width` (integer, default 512): Output width in pixels
- `height` (integer, default 512): Output height in pixels
- `steps` (integer, default 20): Inference steps
- `cfg_scale` (float, default 7.5): Guidance scale
- `project_name` (string): Optional project context

**Returns:**
```json
{
  "task_id": "abc123def456",
  "digest": "sha256-hash",
  "storage_uri": "bee://primary/EVAVO/ImageGeneration/outputs",
  "status": "queued"
}
```

#### `batch_generate_images`
Generate multiple images efficiently.

**Parameters:**
- `prompts` (array of strings, required): List of prompts
- `project_name` (string): Project for organizing outputs
- (other parameters same as `generate_image`)

#### `get_storage_paths`
Get bee:// URIs for storage locations.

**Parameters:**
- `location_type` (string, required): outputs, models, workflows, or projects
- `project_name` (string): For projects location

#### `get_generation_status`
Check status of generation tasks.

**Parameters:**
- `task_id` (string): Task ID to check

## Digest-Bound Task Manifest

See `evavo-repository-task-manifest.json` for complete task definitions including:
- Image generation via ComfyUI
- Batch processing
- Video generation (planning)
- Workflow execution
- Texture generation (planning)
- 3D model generation (planning)
- Audio/music generation (planning)

Each task includes:
- Script entry points
- Parameter schemas
- Storage paths (bee:// URIs)
- Resource requirements
- Digest validation fields

## Integration with EVAVO Infrastructure

### evavo-local-storage (0.31.0+)
Provides bee:// URI resolution and BeeStation SMB/CIFS access.

**Never** assume hosted Claude can see Windows paths. Always use:
```python
from evavo_local_image_generator.scripts.storage import get_storage_client

client = get_storage_client()
outputs_uri = client.get_outputs_path()  # "bee://primary/EVAVO/ImageGeneration/outputs"
```

### evavo-local-compute
Executes generation tasks with digest-bound validation. Tasks record their digest in the manifest for secure execution across the network.

### evavo-storage
Upon completion, outputs are handed off to evavo-storage for immutable versioning and archival.

## Backend Services

Ensure these services are running on the workstation:

### ComfyUI
- **Port**: 8188
- **Health Check**: `curl http://127.0.0.1:8188/status`
- **Start Command**: See evavo-local-storage bootstrap

### Ollama (Optional)
- **Port**: 11434
- **Models**: Qwen3.5, Mistral, etc. (12GB VRAM workstation)

### Kokoro FastAPI (Optional)
- **Port**: 8000
- **Purpose**: Text-to-speech

## Testing

```bash
# Run unit tests
python -m pytest tests/

# Test MCP server
python -m evavo_local_image_generator.mcp_server

# Test generation
python -m evavo_local_image_generator.scripts.generate
```

## Configuration

Environment variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `EVAVO_LOCAL_IMAGE_GENERATOR_MODE` | development | Operation mode (development/production) |
| `EVAVO_LOCAL_IMAGE_GENERATOR_STORAGE` | bee://primary/EVAVO/ImageGeneration | Base storage URI |
| `EVAVO_COMFYUI_ENDPOINT` | http://127.0.0.1:8188 | ComfyUI API endpoint |
| `EVAVO_OLLAMA_ENDPOINT` | http://127.0.0.1:11434 | Ollama API endpoint |
| `EVAVO_TTS_ENDPOINT` | http://127.0.0.1:8000 | Kokoro FastAPI endpoint |

## File Organization

```
evavo-local-image-generator/
├── evavo_local_image_generator/              # Python package
│   ├── __init__.py                           # Package initialization
│   ├── mcp_server.py                         # MCP protocol implementation
│   ├── scripts/
│   │   ├── __init__.py
│   │   ├── storage.py                        # BeeStation storage client
│   │   ├── generate.py                       # Generation orchestration
│   │   ├── workflows.py                      # ComfyUI workflow execution
│   │   └── batch.py                          # Batch processing
│   ├── workflows/                            # ComfyUI workflow files
│   │   ├── stable_diffusion_basic.json
│   │   └── ...
│   └── tests/
│       ├── __init__.py
│       ├── test_generation.py
│       └── test_storage.py
├── evavo-repository-task-manifest.json       # Digest-bound task definitions
├── .mcp.json                                 # MCP server configuration
├── CLAUDE.md                                 # Operating notes for Claude
├── requirements.txt                          # Python dependencies
├── README.md                                 # This file
└── .git/                                     # Version control
```

## Key Constraints

1. **Never assume hosted Claude sees Windows paths** - Use bee:// URIs exclusively
2. **No intermediate staging on C: drive** - All operations via BeeStation
3. **Digest-bound tasks only** - Execute through evavo-local-compute with validation
4. **Immutable milestones** - Hand off canonical outputs via evavo-storage
5. **No raw UNC paths** - Never use //beestation/shares directly

## Contributing

1. Create feature branch from main
2. Implement changes following the module structure
3. Add digest-bound task definition to manifest if adding new capability
4. Test with local ComfyUI, Ollama, and Kokoro services
5. Commit with proper attribution
6. Submit pull request

## License

Part of the EVAVO Platform. See LICENSE.

## Support

For issues and questions, refer to:
- evavo-local-storage documentation for BeeStation access
- evavo-local-compute documentation for digest-bound execution
- evavo-storage documentation for immutable handoff

---

Built for the EVAVO Platform's unified multi-modal AI generation infrastructure.
